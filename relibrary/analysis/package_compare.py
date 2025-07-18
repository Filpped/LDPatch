"""
软件包比较分析模块，用于比较不同发行版之间的软件包差异
"""

import os
import logging
import time
import html
from relibrary.core.package_analyzer import get_package_list, sort_packages, compare_packages, find_similar_packages
from relibrary.utils.files.file_operations import save_json, load_json, ensure_dir

# 设置日志格式
logging.basicConfig(
    filename='package_comparison.log',
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

class PackageComparer:
    """软件包比较器，用于比较不同发行版之间的软件包"""
    
    def __init__(self, distributions):
        """
        初始化软件包比较器
        
        Args:
            distributions: 要比较的发行版列表
        """
        self.distributions = distributions
        self.package_data = {}
    
    def fetch_package_data(self, force_refresh=False):
        """
        获取所有发行版的软件包数据
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            dict: 发行版到软件包数据的映射
        """
        # 缓存文件路径
        cache_dir = "data/packages"
        ensure_dir(cache_dir)
        
        result = {}
        
        for dist in self.distributions:
            cache_file = f"{cache_dir}/{dist.lower().replace('-', '_')}_packages.json"
            
            # 检查缓存
            if not force_refresh and os.path.exists(cache_file):
                logging.info(f"从缓存加载 {dist} 的软件包数据: {cache_file}")
                data = load_json(cache_file)
                if data:
                    result[dist] = data
                    continue
            
            # 获取新数据
            logging.info(f"获取 {dist} 的软件包数据...")
            data = get_package_list(dist)
            
            if data:
                # 保存到缓存
                save_json(data, cache_file)
                logging.info(f"已缓存 {dist} 的软件包数据: {cache_file}")
                result[dist] = data
            else:
                logging.error(f"无法获取 {dist} 的软件包数据")
        
        self.package_data = result
        return result
    
    def compare_all(self, output_dir="data/comparison"):
        """
        比较所有发行版之间的软件包
        
        Args:
            output_dir: 输出目录
            
        Returns:
            dict: 比较结果
        """
        if len(self.package_data) < 2:
            logging.error("需要至少两个发行版的数据才能进行比较")
            return {}
        
        ensure_dir(output_dir)
        
        # 执行所有可能的比较
        comparisons = {}
        for i, dist1 in enumerate(self.distributions):
            for j in range(i+1, len(self.distributions)):
                dist2 = self.distributions[j]
                
                if dist1 not in self.package_data or dist2 not in self.package_data:
                    continue
                
                logging.info(f"比较 {dist1} 和 {dist2} 的软件包...")
                
                comparison_key = f"{dist1}_vs_{dist2}"
                comparison_result = compare_packages(
                    self.package_data[dist1],
                    self.package_data[dist2]
                )
                
                # 保存比较结果
                output_file = f"{output_dir}/{comparison_key}.json"
                save_json(comparison_result, output_file)
                logging.info(f"比较结果已保存到: {output_file}")
                
                comparisons[comparison_key] = comparison_result
        
        return comparisons
    
    def find_similar_packages_for_unique(self, comparison_results, threshold=0.5, max_similar=5):
        """
        为独有的软件包查找相似包
        
        Args:
            comparison_results: 比较结果
            threshold: 相似度阈值
            max_similar: 每个包最多返回的相似包数量
            
        Returns:
            dict: 包含相似包信息的比较结果
        """
        enhanced_results = {}
        
        for comparison_key, comparison_data in comparison_results.items():
            dist1, dist2 = comparison_key.split("_vs_")
            
            # 为dist1中独有的包查找dist2中的相似包
            only_in_1 = comparison_data.get("only_in_1", [])
            similar_packages_1 = {}
            
            for package in only_in_1:
                if package not in self.package_data[dist1]:
                    continue
                
                pkg_info = self.package_data[dist1][package]
                description = pkg_info.get('description', '')
                
                similar = find_similar_packages(
                    package, 
                    description, 
                    self.package_data[dist2], 
                    threshold
                )
                
                if similar:
                    similar_packages_1[package] = similar[:max_similar]
            
            # 为dist2中独有的包查找dist1中的相似包
            only_in_2 = comparison_data.get("only_in_2", [])
            similar_packages_2 = {}
            
            for package in only_in_2:
                if package not in self.package_data[dist2]:
                    continue
                
                pkg_info = self.package_data[dist2][package]
                description = pkg_info.get('description', '')
                
                similar = find_similar_packages(
                    package, 
                    description, 
                    self.package_data[dist1], 
                    threshold
                )
                
                if similar:
                    similar_packages_2[package] = similar[:max_similar]
            
            # 复制原始比较结果并添加相似包信息
            enhanced_result = dict(comparison_data)
            enhanced_result["similar_packages"] = {
                dist1: similar_packages_1,
                dist2: similar_packages_2
            }
            
            enhanced_results[comparison_key] = enhanced_result
        
        return enhanced_results
    
    def generate_html_report(self, comparison_results, output_file="package_comparison.html"):
        """
        生成HTML比较报告
        
        Args:
            comparison_results: 比较结果
            output_file: 输出文件路径
            
        Returns:
            bool: 是否成功生成报告
        """
        # 准备HTML报告头部
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>软件包比较报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; }}
        h1, h2, h3 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .summary {{ background-color: #eef; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .stats {{ display: flex; justify-content: space-around; flex-wrap: wrap; }}
        .stat-item {{ text-align: center; padding: 10px; }}
        .common {{ color: green; }}
        .unique {{ color: blue; }}
        .section {{ margin-bottom: 30px; }}
        .search-box {{ margin-bottom: 15px; }}
        input[type="text"] {{ padding: 8px; width: 300px; }}
        .tabs {{ display: flex; margin-bottom: 10px; }}
        .tab {{ padding: 10px 20px; cursor: pointer; border: 1px solid #ccc; background: #f9f9f9; }}
        .tab.active {{ background: #fff; border-bottom: none; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>软件包比较报告</h1>
        <p>生成时间: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
"""
        
        # 添加比较结果
        for comparison_key, comparison_data in comparison_results.items():
            dist1, dist2 = comparison_key.split("_vs_")
            common_pkgs = comparison_data.get("common", [])
            only_in_1 = comparison_data.get("only_in_1", [])
            only_in_2 = comparison_data.get("only_in_2", [])
            
            html_content += f"""
        <div class="section">
            <h2>{dist1} vs {dist2}</h2>
            <div class="summary">
                <div class="stats">
                    <div class="stat-item">
                        <h3>公共包</h3>
                        <p class="common">{len(common_pkgs)}</p>
                    </div>
                    <div class="stat-item">
                        <h3>{dist1}独有</h3>
                        <p class="unique">{len(only_in_1)}</p>
                    </div>
                    <div class="stat-item">
                        <h3>{dist2}独有</h3>
                        <p class="unique">{len(only_in_2)}</p>
                    </div>
                </div>
            </div>
            
            <div class="search-box">
                <input type="text" id="search-{comparison_key}" placeholder="搜索软件包..." onkeyup="filterPackages('{comparison_key}')">
            </div>
            
            <div class="tabs">
                <div class="tab active" onclick="showTab('{comparison_key}', 'common')">公共包</div>
                <div class="tab" onclick="showTab('{comparison_key}', 'only1')">仅在{dist1}</div>
                <div class="tab" onclick="showTab('{comparison_key}', 'only2')">仅在{dist2}</div>
            </div>
            
            <div id="{comparison_key}-common" class="tab-content active">
                <h3>公共包 ({len(common_pkgs)})</h3>
                <table id="{comparison_key}-common-table">
                    <tr>
                        <th>软件包名</th>
                    </tr>
"""
            
            # 添加公共包列表
            for pkg in common_pkgs:
                html_content += f"                    <tr><td>{html.escape(pkg)}</td></tr>\n"
            
            html_content += f"""
                </table>
            </div>
            
            <div id="{comparison_key}-only1" class="tab-content">
                <h3>{dist1}独有包 ({len(only_in_1)})</h3>
                <table id="{comparison_key}-only1-table">
                    <tr>
                        <th>软件包名</th>
                    </tr>
"""
            
            # 添加dist1独有包列表
            for pkg in only_in_1:
                html_content += f"                    <tr><td>{html.escape(pkg)}</td></tr>\n"
            
            html_content += f"""
                </table>
            </div>
            
            <div id="{comparison_key}-only2" class="tab-content">
                <h3>{dist2}独有包 ({len(only_in_2)})</h3>
                <table id="{comparison_key}-only2-table">
                    <tr>
                        <th>软件包名</th>
                    </tr>
"""
            
            # 添加dist2独有包列表
            for pkg in only_in_2:
                html_content += f"                    <tr><td>{html.escape(pkg)}</td></tr>\n"
            
            html_content += """
                </table>
            </div>
        </div>
"""
        
        # 添加JavaScript函数和HTML结尾
        html_content += """
        <script>
            function showTab(comparisonKey, tabName) {
                // 隐藏所有内容并取消选中所有标签
                document.querySelectorAll(`[id^="${comparisonKey}-"]`).forEach(el => {
                    el.classList.remove('active');
                });
                document.querySelectorAll('.tab').forEach(el => {
                    el.classList.remove('active');
                });
                
                // 显示选中的内容并激活对应的标签
                document.getElementById(`${comparisonKey}-${tabName}`).classList.add('active');
                event.currentTarget.classList.add('active');
            }
            
            function filterPackages(comparisonKey) {
                const searchText = document.getElementById(`search-${comparisonKey}`).value.toLowerCase();
                const tables = [
                    document.getElementById(`${comparisonKey}-common-table`),
                    document.getElementById(`${comparisonKey}-only1-table`),
                    document.getElementById(`${comparisonKey}-only2-table`)
                ];
                
                tables.forEach(table => {
                    const rows = table.getElementsByTagName('tr');
                    for (let i = 1; i < rows.length; i++) {
                        const packageName = rows[i].getElementsByTagName('td')[0].innerText.toLowerCase();
                        if (packageName.includes(searchText)) {
                            rows[i].style.display = '';
                        } else {
                            rows[i].style.display = 'none';
                        }
                    }
                });
            }
        </script>
    </div>
</body>
</html>
"""
        
        # 保存HTML报告
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logging.info(f"HTML报告已保存到: {output_file}")
            return True
        except Exception as e:
            logging.error(f"生成HTML报告失败: {e}")
            return False

def compare_distribution_packages(distributions, output_dir="data/comparison", html_report=True):
    """
    比较不同发行版之间的软件包
    
    Args:
        distributions: 要比较的发行版列表
        output_dir: 输出目录
        html_report: 是否生成HTML报告
        
    Returns:
        dict: 比较结果
    """
    comparer = PackageComparer(distributions)
    
    # 获取软件包数据
    comparer.fetch_package_data()
    
    # 执行比较
    comparison_results = comparer.compare_all(output_dir)
    
    # 查找相似包
    enhanced_results = comparer.find_similar_packages_for_unique(comparison_results)
    
    # 保存增强的比较结果
    enhanced_output_file = f"{output_dir}/enhanced_comparison.json"
    save_json(enhanced_results, enhanced_output_file)
    logging.info(f"增强的比较结果已保存到: {enhanced_output_file}")
    
    # 生成HTML报告
    if html_report:
        html_output_file = f"{output_dir}/package_comparison.html"
        comparer.generate_html_report(comparison_results, html_output_file)
    
    return enhanced_results

if __name__ == "__main__":
    distributions = ['Fedora', 'openEuler-24.03']
    compare_distribution_packages(distributions) 