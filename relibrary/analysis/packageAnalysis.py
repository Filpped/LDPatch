"""
软件包匹配类型分析模块
分析不同匹配类型(match_type)的分布情况和std_match类型中homepage差异情况
"""

import os
import json
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from collections import defaultdict, Counter
from pathlib import Path
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from adjustText import adjust_text # 导入 adjustText
import itertools
from upsetplot import plot
# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 设置全局字体
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman']
plt.rcParams['font.style'] = 'italic'
plt.rcParams['axes.unicode_minus'] = False  

# 设置全局字体以支持中文显示
try:
    plt.rcParams['font.sans-serif'] = ['SimHei']  
    logging.info("成功设置字体为 SimHei")
except Exception as e:
    logging.warning(f"设置 SimHei 字体失败: {e}. 尝试 Microsoft YaHei...")
    try:
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
        logging.info("成功设置字体为 Microsoft YaHei")
    except Exception as e2:
        logging.error(f"设置 Microsoft YaHei 字体也失败: {e2}. 中文可能无法正常显示。")


plt.style.use('seaborn-v0_8-paper')
sns.set_context("paper")


COLORS = ["#4878D0", "#EE854A", "#6ACC64", "#D65F5F", "#956CB4", "#8C613C", "#DC7EC0", "#82C6E2"]
MATCH_TYPE_COLORS = {
    "exact_match": "#4878D0",    
    "std_match": "#6ACC64",      
}

HOMEPAGE_DETAIL_COLORS = {
    "identical": "#4878D0",         
    "different": "#EE854A",         
    "partially_missing": "#FFC107", 
    "completely_missing": "#CCCCCC"  
}

custom_cmap = LinearSegmentedColormap.from_list("custom",
                                              ["#4878D0", "#6ACC64"], 
                                              N=100)

class PackageAnalyzer:
    """软件包数据分析类"""
    
    def __init__(self, data_dir="data/packages"):
        """
        初始化分析器
        
        Args:
            data_dir: 数据目录
        """
        self.data_dir = data_dir
        self.regular_data = None     # 同源软件包数据
        self.version_data = None     # 同源同版本软件包数据
        self.output_dir = os.path.join(data_dir, "analysis_output")
        
        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
        
    def load_data(self):
        """加载两份JSON数据"""
        regular_file = os.path.join(self.data_dir, "package_analysis.json")
        version_file = os.path.join(self.data_dir, "package_analysis_withVersion.json")
        
        logging.info(f"加载同源数据: {regular_file}")
        with open(regular_file, 'r', encoding='utf-8') as f:
            self.regular_data = json.load(f)
            
        logging.info(f"加载同源同版本数据: {version_file}")
        with open(version_file, 'r', encoding='utf-8') as f:
            self.version_data = json.load(f)
        
        logging.info("数据加载完成")
    
    def extract_comparison_groups(self, data):
        """
        提取比较组(如两两比较、多发行版比较)
        
        Args:
            data: JSON数据
            
        Returns:
            dict: 比较组数据
        """
        comparison_groups = {}
        
        for key, value in data.items():
            if key.endswith("_common") and isinstance(value, dict):
                comparison_groups[key] = value
        
        return comparison_groups
    
    def analyze_match_types(self, data):
        """
        分析不同match_type的分布
        
        Args:
            data: 比较组数据
            
        Returns:
            dict: 每个比较组中不同match_type的计数
        """
        comparison_groups = self.extract_comparison_groups(data)
        match_type_stats = {}
        
        for group_name, packages in comparison_groups.items():
            match_types = Counter()
            total_packages = 0
            
            for pkg_name, pkg_data in packages.items():
                if "match_info" in pkg_data and "match_type" in pkg_data["match_info"]:
                    match_type = pkg_data["match_info"]["match_type"]
                    match_types[match_type] += 1
                    total_packages += 1
            
            if total_packages > 0:
                match_type_stats[group_name] = {
                    "counts": dict(match_types),
                    "total": total_packages
                }
        
        return match_type_stats
    
    def _normalize_homepage(self, url):
        """标准化 homepage URL，处理空值和 '未知'"""
        if not url or str(url).strip().lower() == '未知':
            return None
        return str(url).strip().lower().rstrip('/')

    def _compare_homepage_projects(self, url1, url2):
        """
        比较两个URL是否可能指向同一项目
        包含提取项目名部分的逻辑
        
        Args:
            url1, url2: 两个URL字符串 (假设已通过 _normalize_homepage 处理，不为 None)
            
        Returns:
            bool: 是否可能指向同一项目
        """
        
        # 完全相同
        if url1 == url2:
            return True
            
        # 提取域名 (简单提取，不含 www)
        def get_domain(url):
            url = url.replace('http://', '').replace('https://', '')
            domain_parts = url.split('/')[0].split('.')
            # 移除 www
            if domain_parts[0] == 'www':
                domain_parts = domain_parts[1:]
            return '.'.join(domain_parts)
            
        domain1 = get_domain(url1)
        domain2 = get_domain(url2)
        
        # 域名相同 (例如 pypi.org 和 pypi.python.org 应该不同)
        if domain1 == domain2:
            # 对于 GitHub 等托管平台，域名相同还不够，需要比较项目路径
            if 'github.com' in domain1:
                 path1 = url1.split(domain1)[-1].strip('/')
                 path2 = url2.split(domain2)[-1].strip('/')
                 # 简单比较路径前两部分 (user/repo)
                 parts1 = path1.split('/')[:2]
                 parts2 = path2.split('/')[:2]
                 if len(parts1) == 2 and len(parts2) == 2 and parts1 == parts2:
                     return True
                 # 如果路径不符或不完整，即使域名相同也认为不同
                 # return False 
            else:
                # 对于非代码托管平台，如果域名相同，倾向于认为是相似的
                 return True 
                 
        # 提取最后一部分作为项目名
        def get_project(url):
            # 移除协议和查询参数/片段
            url_cleaned = url.split('?')[0].split('#')[0]
            url_cleaned = url_cleaned.replace('http://', '').replace('https://', '').rstrip('/')
            parts = url_cleaned.split('/')
            # 从后往前找第一个非空部分
            for i in range(len(parts)-1, 0, -1):
                if parts[i]:
                    # 进一步处理可能的版本号或 .git 后缀
                    part_cleaned = parts[i].replace('.git','')
                    # 可以添加更多基于常见模式的清理规则
                    return part_cleaned
            return None # 如果无法提取项目名
            
        project1 = get_project(url1)
        project2 = get_project(url2)
        
        # 只有当两个项目名都成功提取且相同时，才认为相同
        return project1 is not None and project1 == project2

    def analyze_homepage_details(self, data, match_type_filter):
        """
        通用函数：分析指定 match_type 包中 homepage 字段的详细情况
        
        Args:
            data: JSON 数据
            match_type_filter: 'exact_match' 或 'std_match'
            
        Returns:
            dict: 每个比较组中符合 match_type 的包的 homepage 详细分类统计
        """
        comparison_groups = self.extract_comparison_groups(data)
        homepage_detail_stats = {}
        
        for group_name, packages in comparison_groups.items():
            if not packages: continue # 跳过空的分组
            
            # 从第一个包确定发行版键名和数量
            first_pkg_data = next(iter(packages.values()))
            distro_keys = [k for k in first_pkg_data.keys() if k != 'match_info']
            num_distros = len(distro_keys)
            
            # 只处理 2, 3, 4 个发行版的比较组
            if num_distros < 2 or num_distros > 4:
                logging.debug(f"Skipping group {group_name}: Unsupported number of distributions ({num_distros}) for detailed homepage analysis.")
                continue
                
            logging.debug(f"Analyzing group {group_name} ({num_distros} distros: {distro_keys}) for {match_type_filter} homepage details.")
            
            counts = Counter()
            total_matched_packages = 0

            for pkg_name, pkg_data in packages.items():
                # 检查是否为目标 match_type
                is_target_match = False
                match_info = pkg_data.get('match_info', {})
                if isinstance(match_info, dict):
                    if match_info.get("match_type") == match_type_filter:
                        is_target_match = True
                elif isinstance(match_info, list): # 兼容旧格式
                     if any(m.get("type") == match_type_filter for m in match_info):
                         is_target_match = True 
                          
                if is_target_match:
                    total_matched_packages += 1
                    
                    # 提取并标准化所有发行版的 homepage
                    homepages_raw = [pkg_data.get(dk, {}).get("homepage", None) for dk in distro_keys]
                    homepages_norm = [self._normalize_homepage(hp) for hp in homepages_raw]
                    num_missing = sum(1 for hp in homepages_norm if hp is None)

                    category = "unknown" # Default category
                    if num_missing == num_distros:
                        category = "completely_missing"
                    elif num_missing > 0:
                        category = "partially_missing" # 只要有1个缺少就算
                    else: # num_missing == 0，所有都有 homepage
                        # 检查所有 homepage 是否相同
                        first_hp = homepages_norm[0]
                        all_identical = True
                        for hp in homepages_norm[1:]:
                            # 使用 _compare_homepage_projects 进行两两比较
                            if not self._compare_homepage_projects(first_hp, hp):
                                all_identical = False
                                break # 只要有一对不同，就不是全部相同
                        
                        if all_identical:
                            category = "identical" # 所有都有且相同
                        else:
                            category = "different" # 所有都有但不同
                            
                    counts[category] += 1
                    if category == "unknown":
                         logging.warning(f"({match_type_filter}) 无法分类 Homepage 状态: pkg={pkg_name}, group={group_name}, homepages={homepages_raw}")
                         
            if total_matched_packages > 0:
                homepage_detail_stats[group_name] = {
                    "counts": dict(counts),
                    "total": total_matched_packages
                }
        
        return homepage_detail_stats

    def plot_homepage_details_distribution(self, data_type, match_type_filter):
        """
        通用函数：绘制指定 match_type 包中 homepage 详细分布图 
        Args:
            data_type: 'regular' 或 'version'
            match_type_filter: 'exact_match' 或 'std_match'
        """
        data = self.regular_data if data_type == "regular" else self.version_data
        # 调用通用的分析函数
        homepage_detail_stats = self.analyze_homepage_details(data, match_type_filter)
        
        log_prefix = match_type_filter.replace('_',' ').title()
        if not homepage_detail_stats:
            logging.warning(f"没有找到足够的 {match_type_filter} 数据进行详细 homepage 分析")
            return

        selected_groups = sorted(
            homepage_detail_stats.keys(),
            # 可以根据需要添加排序逻辑，例如按 total 数量
            key=lambda x: (len(x.split('_')), homepage_detail_stats[x]["total"]),
            reverse=True
        ) 
        if not selected_groups:
             logging.warning(f"没有有效的比较组用于绘制 {log_prefix} Homepage 详细分布图")
             return

        # 绘制堆叠柱状图
        fig, ax = plt.subplots(figsize=(max(12, len(selected_groups)*0.8), 8))

        df_data = []
        categories = ["identical", "different", "partially_missing", "completely_missing", "unknown"]
        for group_name in selected_groups:
            stats = homepage_detail_stats[group_name]
            
            try:
                parts = group_name.split("_common")[0].split('_')
                if len(parts) >= 2 and "all" not in parts:
                    name_part = group_name.split("_common")[0]
                    last_underscore_idx = name_part.rfind('_')
                    distro1 = name_part[:last_underscore_idx]
                    distro2 = name_part[last_underscore_idx+1:]
                    formatted_name = f"{distro1} vs {distro2}"
                else:
                    formatted_name = group_name # 对于 all_common 等直接用
            except Exception:
                 formatted_name = group_name 
                 
            row = {"group": formatted_name, "total": stats["total"]}
            for category in categories:
                count = stats["counts"].get(category, 0)
                # 只添加有计数的 category 到 DataFrame 行
                if count > 0:
                     percentage = 100 * count / stats["total"]
                     row[category + '_perc'] = percentage
                     row[category + '_count'] = count
            df_data.append(row)
            
        df = pd.DataFrame(df_data).fillna(0) # 使用 0 填充缺失的 category 计数/百分比
        df['sort_key'] = df['group'].apply(lambda x: (0 if 'vs' in x else 1, x)) # 优先排两两比较
        df = df.sort_values('sort_key').drop('sort_key', axis=1) 

        # 绘制逻辑基本不变
        bottom = np.zeros(len(df))
        bar_width = 0.8
        plotted_categories = [] 
        for category in categories:
            perc_col = category + '_perc'
            count_col = category + '_count'
            if perc_col in df.columns and df[perc_col].sum() > 0:
                plotted_categories.append(category)
                bars = ax.bar(df["group"], df[perc_col], bottom=bottom,
                       label=category.replace('_', ' ').title(),
                       color=HOMEPAGE_DETAIL_COLORS.get(category, '#808080'), 
                       width=bar_width)
                for i, bar in enumerate(bars):
                    height = bar.get_height()
                    count = int(df.iloc[i].get(count_col, 0))
                    if count > 0 and height > 3:
                        ax.text(bar.get_x() + bar.get_width() / 2., bottom[i] + height / 2.,
                                f'{count}', ha='center', va='center',
                                color='white' if category not in ['completely_missing', 'partially_missing'] else 'black',
                                fontsize=9, weight='bold', fontname='Times New Roman', fontstyle='italic')
                bottom += df[perc_col].values

        # 设置图表属性
        match_type_display = match_type_filter.replace('_', ' ')
        title = f"{match_type_display.capitalize()} 软件包的主页(Homepage)详细分析 ({'无版本约束' if data_type == 'regular' else '有版本约束'})"
        ax.set_title(title, fontsize=14, y=1.02, fontname='Times New Roman', fontstyle='italic')
        ax.set_xlabel("比较组", fontsize=12, fontname='Times New Roman', fontstyle='italic')
        ax.set_ylabel("百分比 (%)", fontsize=12, fontname='Times New Roman', fontstyle='italic')
        ax.set_ylim(0, 100)

        tick_labels = [f"{row['group']}\n(n={int(row['total'])})" for _, row in df.iterrows()]
        ax.set_xticks(np.arange(len(df)))
        ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=9, fontname='Times New Roman', fontstyle='italic')
        # 图例只显示实际绘制的类别
        ax.legend(title="Homepage 状态", 
                  handles=[plt.Rectangle((0,0),1,1, color=HOMEPAGE_DETAIL_COLORS.get(cat, '#808080')) for cat in plotted_categories],
                  labels=[cat.replace('_', ' ').title() for cat in plotted_categories],
                  loc='lower right', prop={'family': 'Times New Roman', 'style': 'italic'})
                  
        plt.tight_layout(rect=[0.03, 0.20, 1, 0.93])

        # 保存图片
        output_file = os.path.join(self.output_dir, f"{match_type_filter}_homepage_details_{data_type}.png")
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        logging.info(f"{log_prefix} Homepage 详细分布图已保存至: {output_file}")

    def plot_match_type_distribution(self, data_type="regular"):
        """
        绘制匹配类型分布图
        
        Args:
            data_type: 'regular'或'version'，表示使用哪份数据
        """
        data = self.regular_data if data_type == "regular" else self.version_data
        match_type_stats = self.analyze_match_types(data)
        
        # 检查是否存在 source_match 数据
        has_source_match = any(stats['counts'].get('source_match', 0) > 0 
                               for stats in match_type_stats.values())
        
        # 定义要绘制的匹配类型
        match_types_to_plot = ["exact_match", "std_match"]
        if has_source_match:
             match_types_to_plot.append("source_match")
             logging.warning("检测到 source_match 数据，将包含在图表中。")
        else:
             
             global MATCH_TYPE_COLORS 
             MATCH_TYPE_COLORS = {
                 "exact_match": "#4878D0",
                 "std_match": "#6ACC64"
             }

        # 选择最有代表性的几个组进行绘制
        selected_groups = []
        
        # 选择每个比较组
        for group_name, stats in match_type_stats.items():
            if stats["total"] > 100:  # 只选择有足够包数量的组
                selected_groups.append(group_name)
        
        if not selected_groups:
            logging.warning("没有找到足够的比较组进行绘制")
            return
            
      
        n_groups = len(selected_groups)
        ncols = 4
        nrows = min(3, (n_groups + ncols - 1) // ncols)
        fig_size = (16, nrows * 4 + 1) 
        
        fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=fig_size, squeeze=False)
            
    
        def make_autopct(values):
            def my_autopct(pct):
                total = sum(values)
                val = int(round(pct*total/100.0))
                # 仅当数量大于0时显示
                return f'{val}\n({pct:.1f}%)' if val > 0 else ''
            return my_autopct

        for i, group_name in enumerate(selected_groups):
            if i >= nrows * ncols: # 如果组数超过布局限制，停止绘制
                logging.warning(f"饼图过多，仅绘制前 {nrows * ncols} 个组")
                break

            row_idx = i // ncols
            col_idx = i % ncols
            ax = axes[row_idx, col_idx] 

            stats = match_type_stats[group_name]
            labels_pie = []
            sizes_pie = []
            colors_pie = []
            
            for match_type in match_types_to_plot: # 使用筛选后的列表
                count = stats["counts"].get(match_type, 0)
                if count > 0: # 只添加数量大于0的类别
                    labels_pie.append(match_type)
                    sizes_pie.append(count)
                    colors_pie.append(MATCH_TYPE_COLORS.get(match_type, "#CCCCCC"))
            
            # 绘制饼图 - 使用自定义 autopct
            if sum(sizes_pie) > 0: # 仅当有数据时绘制
                 wedges, texts, autotexts = ax.pie(sizes_pie, labels=labels_pie, colors=colors_pie,
                           autopct=make_autopct(sizes_pie),
                           startangle=90,
                           wedgeprops={'edgecolor': 'w', 'linewidth': 1},
                           pctdistance=0.8, 
                           labeldistance=1.1) 
          
                 plt.setp(autotexts, size=8, weight="bold", color="white", fontname='Times New Roman', fontstyle='italic')
                 plt.setp(texts, size=9, fontname='Times New Roman', fontstyle='italic')

            ax.set_title(f"{group_name}\n总计: {stats['total']}个软件包", fontsize=10, fontname='Times New Roman', fontstyle='italic')

        # 隐藏未使用的子图
        for i in range(n_groups, nrows * ncols):
             row_idx = i // ncols
             col_idx = i % ncols
             axes[row_idx, col_idx].axis('off')
            
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        title = "同源软件包匹配类型分布" if data_type == "regular" else "同源同版本软件包匹配类型分布"
        fig.suptitle(title, fontsize=16, fontname='Times New Roman', fontstyle='italic')
        
        # 保存图片
        output_file = os.path.join(self.output_dir, f"match_type_pie_{data_type}.png")
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        logging.info(f"饼图已保存至: {output_file}")
        
        # 2. 绘制堆叠柱状图 - 所有比较组的match_type分布
        fig, ax = plt.subplots(figsize=(12, 8))
        
        df_data = []
        for group_name in selected_groups:
            stats = match_type_stats[group_name]
            row = {
                "group": group_name,
                "total": stats["total"]
            }
            for match_type in match_types_to_plot: 
                count = stats["counts"].get(match_type, 0)
                percentage = 100 * count / stats["total"] if stats["total"] > 0 else 0
                row[match_type + '_perc'] = percentage 
                row[match_type + '_count'] = count     
            df_data.append(row)
            
        df = pd.DataFrame(df_data)
        
        # 按总数排序
        df = df.sort_values("total", ascending=False)
        
        # 先绘制所有柱子
        bottom = np.zeros(len(df))
        bar_width = 0.8
        bars_dict = {}
        for match_type in match_types_to_plot:
            perc_col = match_type + '_perc'
            if perc_col in df.columns:
                bars = ax.bar(df["group"], df[perc_col], bottom=bottom,
                       label=match_type, color=MATCH_TYPE_COLORS.get(match_type), width=bar_width)
                bars_dict[match_type] = bars
                bottom += df[perc_col].values
        # 再添加内部数字标签 (确保只执行一次)
        for match_type in match_types_to_plot:
             perc_col = match_type + '_perc'
             count_col = match_type + '_count'
             if perc_col in df.columns and match_type in bars_dict:
                 bars = bars_dict[match_type]
                 for i, bar in enumerate(bars):
                     height = bar.get_height()
                     count = df.iloc[i][count_col]
                     bar_bottom = bar.get_y()
                     if count > 0 and height > 3:
                         ax.text(bar.get_x() + bar.get_width() / 2., bar_bottom + height / 2.,
                                 f'{count}', ha='center', va='center',
                                 color='white', fontsize=9, weight='bold', fontname='Times New Roman', fontstyle='italic')

        # 使用 adjustText 添加百分比标注
        exact_match_perc_col = 'exact_match_perc'
        texts_to_adjust = [] 
        if exact_match_perc_col in df.columns and 'exact_match' in bars_dict:
            exact_bars = bars_dict['exact_match']
            for i, bar in enumerate(exact_bars):
                x_pos = bar.get_x() + bar.get_width() / 2.0
                y_boundary = bar.get_height()

                if y_boundary > 0: # 包含 100% 的情况
                    # 添加文本对象，初始位置在柱子交界处下方一点
                    text = ax.text(x_pos, y_boundary - 2, f'{y_boundary:.1f}%', 
                                   ha='center', va='top', 
                                   fontsize=9, color='#333333', weight='bold', fontname='Times New Roman', fontstyle='italic')
                    texts_to_adjust.append(text)
        
        # 调用 adjust_text 进行智能布局
        if texts_to_adjust:
            adjust_text(texts_to_adjust, 
                        ax=ax, 
                        arrowprops=dict(arrowstyle="-", color='#555555', lw=0.8),
                        force_text=(0.2, 0.5), 
                        force_points=(0.2, 0.2) 
                       )

        # 设置图表属性
        title_bar = f"{title} - 百分比"
        ax.set_title(title_bar, fontsize=14, y=1.02, fontname='Times New Roman', fontstyle='italic')
        ax.set_xlabel("比较组", fontsize=12, fontname='Times New Roman', fontstyle='italic')
        ax.set_ylabel("百分比 (%)", fontsize=12, fontname='Times New Roman', fontstyle='italic')
        current_ylim = ax.get_ylim()

        ax.set_ylim(0, max(current_ylim[1], 108)) 
        ax.autoscale(enable=True, axis='x', tight=True)

        tick_labels = [f"{row['group']}\n(n={row['total']})" for _, row in df.iterrows()]
        ax.set_xticks(np.arange(len(df)))
        ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=9, fontname='Times New Roman', fontstyle='italic')

        # 添加图例 
        ax.legend(title="匹配类型", 
                  labels=[mt for mt in match_types_to_plot if mt + '_perc' in df.columns],
                  loc='lower right', prop={'family': 'Times New Roman', 'style': 'italic'})

        # 调整布局
        plt.tight_layout(rect=[0.03, 0.20, 1, 0.93]) # 增加下边距 (0.15 -> 0.20)

        # 保存图片
        output_file = os.path.join(self.output_dir, f"match_type_bar_{data_type}.png")
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        logging.info(f"柱状图已保存至: {output_file}")

    def plot_upset_diagram(self, data_type="regular"):
        """
        绘制展示4个发行版软件包重叠情况的UpSet图。

        Args:
            data_type: 'regular' 或 'version'，表示使用哪份数据
        """
        data = self.regular_data if data_type == "regular" else self.version_data
        if not data:
            logging.error(f"无法加载 {data_type} 数据，跳过UpSet图绘制。")
            return

        logging.info(f"--- 开始为 {data_type} 数据绘制UpSet图 ---")

        # 定义固定的数据集（不同版本下交集数量）
        regular_counts_data = {
            'ubuntu-24.04_all': 37383,
            'debian_all': 34467,
            'fedora_all': 24725,
            'openeuler-24.03_all': 6155,
            'ubuntu-24.04_debian_common': 33279,
            'ubuntu-24.04_fedora_common': 9457,
            'ubuntu-24.04_openeuler-24.03_common': 2822,
            'debian_fedora_common': 8766,
            'debian_openeuler-24.03_common': 2746,
            'fedora_openeuler-24.03_common': 4421, 
            'ubuntu-24.04_debian_fedora_common': 8637,
            'ubuntu-24.04_debian_openeuler-24.03_common': 2737,
            'ubuntu-24.04_fedora_openeuler-24.03_common': 2419,
            'debian_fedora_openeuler-24.03_common': 2367,
            'ubuntu-24.04_debian_fedora_openeuler-24.03_common': 2358
        }

        version_counts_data = {
            'ubuntu-24.04_all': 37383,
            'debian_all': 34467,
            'fedora_all': 24725,
            'openeuler-24.03_all': 6155,
            'ubuntu-24.04_debian_common': 23776,
            'ubuntu-24.04_fedora_common': 3898,
            'ubuntu-24.04_openeuler-24.03_common': 1264, 
            'debian_fedora_common': 2706,
            'debian_openeuler-24.03_common': 1013,
            'fedora_openeuler-24.03_common': 2009,
            'ubuntu-24.04_debian_fedora_common': 2495, 
            'ubuntu-24.04_debian_openeuler-24.03_common': 815,
            'ubuntu-24.04_fedora_openeuler-24.03_common': 732,
            'debian_fedora_openeuler-24.03_common': 560,
            'ubuntu-24.04_debian_fedora_openeuler-24.03_common': 539
        }

        # 根据 data_type 选择数据源
        counts = regular_counts_data if data_type == "regular" else version_counts_data

        # 固定发行版顺序
        distributions = ['ubuntu-24.04', 'debian', 'fedora', 'openeuler-24.03']

        # 使用 Counter 构建布尔组合统计
        comb_counter = Counter()

        for key, count in counts.items():
            if count <= 0:
                continue
            if key.endswith('_all'):
                distro = key.replace('_all', '')
                combo = tuple(d == distro for d in distributions)
            else:
                distros_in_key = key.replace('_common', '').split('_')
                combo = tuple(d in distros_in_key for d in distributions)

            comb_counter[combo] += count

        # 创建 Pandas Series
        index = pd.MultiIndex.from_tuples(comb_counter.keys(), names=distributions)
        upset_series = pd.Series(comb_counter.values(), index=index)
        upset_series = upset_series[upset_series > 0]

        if upset_series.empty:
            logging.warning(f"所有交集数量为0，无法绘制UpSet图 for {data_type}")
            return

        try:
            fig = plt.figure(figsize=(12, 7))
            
            def sort_key(index_tuple):
                return (sum(index_tuple), -upset_series[index_tuple])
                
            sorted_index = sorted(upset_series.index, key=sort_key)
            upset_series_sorted = upset_series.reindex(sorted_index)
            
            # 使用排序后的 Series 绘图，关闭内部排序
            plot(upset_series_sorted, fig=fig, sort_by=None, show_counts=True)
            title_suffix = "without Version Constraint" if data_type == "regular" else "with Version Constraint"
            plt.suptitle(f"Homologous Package Analysis {f'({title_suffix})' if title_suffix else ''}", fontsize=16, y=0.98, fontname='Times New Roman', fontstyle='italic')

            # 保存图片
            output_file = os.path.join(self.output_dir, f"upset_plot_{data_type}.png")
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            plt.close(fig)
            logging.info(f"UpSet图已保存至: {output_file}")

        except ImportError:
            logging.error("绘制UpSet图失败：请确保已安装 'upsetplot' 库 (pip install upsetplot)。")
        except Exception as e:
            logging.error(f"绘制UpSet图时出错: {e}")
            if 'fig' in locals() and fig:
                plt.close(fig)

        logging.info(f"--- {data_type} 数据UpSet图绘制完成 ---")



    def run_all_analysis(self):
        """运行所有分析"""
        logging.info("开始进行软件包匹配类型分析...")
        
        # 加载数据
        self.load_data()
        
        logging.info("--- 分析同源软件包 (无版本约束) ---")
        logging.info("分析匹配类型分布...")
        self.plot_match_type_distribution(data_type="regular")
        
        logging.info("分析完全匹配(exact_match)软件包的主页详细状态...")
        self.plot_homepage_details_distribution(data_type="regular", match_type_filter="exact_match") 
        
        logging.info("分析标准化匹配(std_match)软件包的主页详细状态...")
        self.plot_homepage_details_distribution(data_type="regular", match_type_filter="std_match") 
        
        logging.info("绘制软件包交集UpSet图 (无版本约束)...")
        self.plot_upset_diagram(data_type="regular")

        logging.info("--- 分析同源同版本软件包 (有版本约束) ---")
        logging.info("分析匹配类型分布...")
        self.plot_match_type_distribution(data_type="version")
        
        logging.info("分析完全匹配(exact_match)软件包的主页详细状态...")
        self.plot_homepage_details_distribution(data_type="version", match_type_filter="exact_match")
        
        logging.info("分析标准化匹配(std_match)软件包的主页详细状态...")
        self.plot_homepage_details_distribution(data_type="version", match_type_filter="std_match") 
        
        logging.info("绘制软件包交集UpSet图 (有版本约束)...")
        self.plot_upset_diagram(data_type="version")
        
        logging.info("分析完成！所有图片已保存到目录: " + self.output_dir)
        print(f"\n分析结果已保存到: {self.output_dir}")

if __name__ == "__main__":
    analyzer = PackageAnalyzer()
    analyzer.run_all_analysis() 