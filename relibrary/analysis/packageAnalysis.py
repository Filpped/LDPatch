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
from adjustText import adjust_text 
import itertools
from upsetplot import plot
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman']
plt.rcParams['font.style'] = 'italic'
plt.rcParams['axes.unicode_minus'] = False  

try:
    plt.rcParams['font.sans-serif'] = ['SimHei']  
except Exception as e:
    try:
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
    except Exception as e2:
        logging.error(f"ERROR")


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
    
    def __init__(self, data_dir="data/packages"):
        self.data_dir = data_dir
        self.regular_data = None   
        self.version_data = None     
        self.output_dir = os.path.join(data_dir, "analysis_output")
        
        os.makedirs(self.output_dir, exist_ok=True)
        
    def load_data(self):
        regular_file = os.path.join(self.data_dir, "package_analysis.json")
        version_file = os.path.join(self.data_dir, "package_analysis_withVersion.json")
        
        with open(regular_file, 'r', encoding='utf-8') as f:
            self.regular_data = json.load(f)
            
        with open(version_file, 'r', encoding='utf-8') as f:
            self.version_data = json.load(f)
    
    def extract_comparison_groups(self, data):
       
        comparison_groups = {}
        
        for key, value in data.items():
            if key.endswith("_common") and isinstance(value, dict):
                comparison_groups[key] = value
        
        return comparison_groups
    
    def analyze_match_types(self, data):
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
        if not url or str(url).strip().lower() == 'UNKNOWN':
            return None
        return str(url).strip().lower().rstrip('/')

    def _compare_homepage_projects(self, url1, url2):
        if url1 == url2:
            return True
            
        def get_domain(url):
            url = url.replace('http://', '').replace('https://', '')
            domain_parts = url.split('/')[0].split('.')
            if domain_parts[0] == 'www':
                domain_parts = domain_parts[1:]
            return '.'.join(domain_parts)
            
        domain1 = get_domain(url1)
        domain2 = get_domain(url2)
        
        if domain1 == domain2:
            if 'github.com' in domain1:
                 path1 = url1.split(domain1)[-1].strip('/')
                 path2 = url2.split(domain2)[-1].strip('/')
                 parts1 = path1.split('/')[:2]
                 parts2 = path2.split('/')[:2]
                 if len(parts1) == 2 and len(parts2) == 2 and parts1 == parts2:
                     return True
            else:
                 return True 
                 
        def get_project(url):
            url_cleaned = url.split('?')[0].split('#')[0]
            url_cleaned = url_cleaned.replace('http://', '').replace('https://', '').rstrip('/')
            parts = url_cleaned.split('/')
            for i in range(len(parts)-1, 0, -1):
                if parts[i]:
                    part_cleaned = parts[i].replace('.git','')
                   
                    return part_cleaned
            return None 
        project1 = get_project(url1)
        project2 = get_project(url2)
        
        return project1 is not None and project1 == project2

    def analyze_homepage_details(self, data, match_type_filter):

        comparison_groups = self.extract_comparison_groups(data)
        homepage_detail_stats = {}
        
        for group_name, packages in comparison_groups.items():
            if not packages: continue 
            first_pkg_data = next(iter(packages.values()))
            distro_keys = [k for k in first_pkg_data.keys() if k != 'match_info']
            num_distros = len(distro_keys)
            
            if num_distros < 2 or num_distros > 4:             
                continue

            counts = Counter()
            total_matched_packages = 0

            for pkg_name, pkg_data in packages.items():
                is_target_match = False
                match_info = pkg_data.get('match_info', {})
                if isinstance(match_info, dict):
                    if match_info.get("match_type") == match_type_filter:
                        is_target_match = True
                elif isinstance(match_info, list):
                     if any(m.get("type") == match_type_filter for m in match_info):
                         is_target_match = True 
                          
                if is_target_match:
                    total_matched_packages += 1
                    
                    homepages_raw = [pkg_data.get(dk, {}).get("homepage", None) for dk in distro_keys]
                    homepages_norm = [self._normalize_homepage(hp) for hp in homepages_raw]
                    num_missing = sum(1 for hp in homepages_norm if hp is None)

                    category = "unknown" 
                    if num_missing == num_distros:
                        category = "completely_missing"
                    elif num_missing > 0:
                        category = "partially_missing" 
                    else: 
                        first_hp = homepages_norm[0]
                        all_identical = True
                        for hp in homepages_norm[1:]:
                           
                            if not self._compare_homepage_projects(first_hp, hp):
                                all_identical = False
                                break 
                        
                        if all_identical:
                            category = "identical" 
                        else:
                            category = "different" 
                            
                    counts[category] += 1
                    if category == "unknown":
                         logging.warning(f"Unknown category for {pkg_name} in {group_name}")
                         
            if total_matched_packages > 0:
                homepage_detail_stats[group_name] = {
                    "counts": dict(counts),
                    "total": total_matched_packages
                }
        
        return homepage_detail_stats

    def plot_homepage_details_distribution(self, data_type, match_type_filter):
        data = self.regular_data if data_type == "regular" else self.version_data
        homepage_detail_stats = self.analyze_homepage_details(data, match_type_filter)
        
        log_prefix = match_type_filter.replace('_',' ').title()
        if not homepage_detail_stats:
            return

        selected_groups = sorted(
            homepage_detail_stats.keys(),
            key=lambda x: (len(x.split('_')), homepage_detail_stats[x]["total"]),
            reverse=True
        ) 
        if not selected_groups:
             return

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
                    formatted_name = group_name 
            except Exception:
                 formatted_name = group_name 
                 
            row = {"group": formatted_name, "total": stats["total"]}
            for category in categories:
                count = stats["counts"].get(category, 0)
                if count > 0:
                     percentage = 100 * count / stats["total"]
                     row[category + '_perc'] = percentage
                     row[category + '_count'] = count
            df_data.append(row)
            
        df = pd.DataFrame(df_data).fillna(0) 
        df['sort_key'] = df['group'].apply(lambda x: (0 if 'vs' in x else 1, x)) 
        df = df.sort_values('sort_key').drop('sort_key', axis=1) 
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

        match_type_display = match_type_filter.replace('_', ' ')
        title = f"{match_type_display.capitalize()} Homepage ({'WITHOUT VERSION CONSTRAINT' if data_type == 'regular' else 'WITH VERSION CONSTRAINT'})"
        ax.set_title(title, fontsize=14, y=1.02, fontname='Times New Roman', fontstyle='italic')
        ax.set_xlabel("COMPARE GROUP", fontsize=12, fontname='Times New Roman', fontstyle='italic')
        ax.set_ylabel("PERCENT (%)", fontsize=12, fontname='Times New Roman', fontstyle='italic')
        ax.set_ylim(0, 100)

        tick_labels = [f"{row['group']}\n(n={int(row['total'])})" for _, row in df.iterrows()]
        ax.set_xticks(np.arange(len(df)))
        ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=9, fontname='Times New Roman', fontstyle='italic')
        ax.legend(title="Homepage", 
                  handles=[plt.Rectangle((0,0),1,1, color=HOMEPAGE_DETAIL_COLORS.get(cat, '#808080')) for cat in plotted_categories],
                  labels=[cat.replace('_', ' ').title() for cat in plotted_categories],
                  loc='lower right', prop={'family': 'Times New Roman', 'style': 'italic'})
                  
        plt.tight_layout(rect=[0.03, 0.20, 1, 0.93])
        output_file = os.path.join(self.output_dir, f"{match_type_filter}_homepage_details_{data_type}.png")
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()

    def plot_match_type_distribution(self, data_type="regular"):
        data = self.regular_data if data_type == "regular" else self.version_data
        match_type_stats = self.analyze_match_types(data)
        has_source_match = any(stats['counts'].get('source_match', 0) > 0 
                               for stats in match_type_stats.values())
        match_types_to_plot = ["exact_match", "std_match"]
        if has_source_match:
             match_types_to_plot.append("source_match")
        else:
             
             global MATCH_TYPE_COLORS 
             MATCH_TYPE_COLORS = {
                 "exact_match": "#4878D0",
                 "std_match": "#6ACC64"
             }

        selected_groups = []

        for group_name, stats in match_type_stats.items():
            if stats["total"] > 100: 
                selected_groups.append(group_name)
        
        if not selected_groups:
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
                return f'{val}\n({pct:.1f}%)' if val > 0 else ''
            return my_autopct

        for i, group_name in enumerate(selected_groups):
            if i >= nrows * ncols:
                break

            row_idx = i // ncols
            col_idx = i % ncols
            ax = axes[row_idx, col_idx] 

            stats = match_type_stats[group_name]
            labels_pie = []
            sizes_pie = []
            colors_pie = []
            
            for match_type in match_types_to_plot: 
                count = stats["counts"].get(match_type, 0)
                if count > 0: 
                    labels_pie.append(match_type)
                    sizes_pie.append(count)
                    colors_pie.append(MATCH_TYPE_COLORS.get(match_type, "#CCCCCC"))

            if sum(sizes_pie) > 0: 
                 wedges, texts, autotexts = ax.pie(sizes_pie, labels=labels_pie, colors=colors_pie,
                           autopct=make_autopct(sizes_pie),
                           startangle=90,
                           wedgeprops={'edgecolor': 'w', 'linewidth': 1},
                           pctdistance=0.8, 
                           labeldistance=1.1) 
          
                 plt.setp(autotexts, size=8, weight="bold", color="white", fontname='Times New Roman', fontstyle='italic')
                 plt.setp(texts, size=9, fontname='Times New Roman', fontstyle='italic')

            ax.set_title(f"{group_name}\nTOTAL: {stats['total']}PACKAGES", fontsize=10, fontname='Times New Roman', fontstyle='italic')

        for i in range(n_groups, nrows * ncols):
             row_idx = i // ncols
             col_idx = i % ncols
             axes[row_idx, col_idx].axis('off')
            
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        title = "DISTRIBUTION OF PACKAGE MATCH TYPES" if data_type == "regular" else "DISTRIBUTION OF PACKAGE VERSION MATCH TYPES"
        fig.suptitle(title, fontsize=16, fontname='Times New Roman', fontstyle='italic')
        
        output_file = os.path.join(self.output_dir, f"match_type_pie_{data_type}.png")
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
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
        
        df = df.sort_values("total", ascending=False)
        
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

        exact_match_perc_col = 'exact_match_perc'
        texts_to_adjust = [] 
        if exact_match_perc_col in df.columns and 'exact_match' in bars_dict:
            exact_bars = bars_dict['exact_match']
            for i, bar in enumerate(exact_bars):
                x_pos = bar.get_x() + bar.get_width() / 2.0
                y_boundary = bar.get_height()

                if y_boundary > 0:
                    text = ax.text(x_pos, y_boundary - 2, f'{y_boundary:.1f}%', 
                                   ha='center', va='top', 
                                   fontsize=9, color='#333333', weight='bold', fontname='Times New Roman', fontstyle='italic')
                    texts_to_adjust.append(text)
        
        if texts_to_adjust:
            adjust_text(texts_to_adjust, 
                        ax=ax, 
                        arrowprops=dict(arrowstyle="-", color='#555555', lw=0.8),
                        force_text=(0.2, 0.5), 
                        force_points=(0.2, 0.2) 
                       )

        title_bar = f"{title} - PERCENTAGE"
        ax.set_title(title_bar, fontsize=14, y=1.02, fontname='Times New Roman', fontstyle='italic')
        ax.set_xlabel("GROUP", fontsize=12, fontname='Times New Roman', fontstyle='italic')
        ax.set_ylabel("%", fontsize=12, fontname='Times New Roman', fontstyle='italic')
        current_ylim = ax.get_ylim()

        ax.set_ylim(0, max(current_ylim[1], 108)) 
        ax.autoscale(enable=True, axis='x', tight=True)

        tick_labels = [f"{row['group']}\n(n={row['total']})" for _, row in df.iterrows()]
        ax.set_xticks(np.arange(len(df)))
        ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=9, fontname='Times New Roman', fontstyle='italic')

        ax.legend(title="TYPE", 
                  labels=[mt for mt in match_types_to_plot if mt + '_perc' in df.columns],
                  loc='lower right', prop={'family': 'Times New Roman', 'style': 'italic'})

        plt.tight_layout(rect=[0.03, 0.20, 1, 0.93])

        output_file = os.path.join(self.output_dir, f"match_type_bar_{data_type}.png")
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()

    def plot_upset_diagram(self, data_type="regular"):
 
        data = self.regular_data if data_type == "regular" else self.version_data
        if not data:
            return
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

        counts = regular_counts_data if data_type == "regular" else version_counts_data

        distributions = ['ubuntu-24.04', 'debian', 'fedora', 'openeuler-24.03']

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

        index = pd.MultiIndex.from_tuples(comb_counter.keys(), names=distributions)
        upset_series = pd.Series(comb_counter.values(), index=index)
        upset_series = upset_series[upset_series > 0]

        if upset_series.empty:
            return

        try:
            fig = plt.figure(figsize=(12, 7))
            
            def sort_key(index_tuple):
                return (sum(index_tuple), -upset_series[index_tuple])
                
            sorted_index = sorted(upset_series.index, key=sort_key)
            upset_series_sorted = upset_series.reindex(sorted_index)
            
            plot(upset_series_sorted, fig=fig, sort_by=None, show_counts=True)
            title_suffix = "without Version Constraint" if data_type == "regular" else "with Version Constraint"
            plt.suptitle(f"Homologous Package Analysis {f'({title_suffix})' if title_suffix else ''}", fontsize=16, y=0.98, fontname='Times New Roman', fontstyle='italic')

            output_file = os.path.join(self.output_dir, f"upset_plot_{data_type}.png")
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            plt.close(fig)

        except ImportError:
            logging.error("ERROR")
        except Exception as e:
            logging.error("ERROR")
            if 'fig' in locals() and fig:
                plt.close(fig)

    def run_all_analysis(self):
        self.load_data()
        self.plot_match_type_distribution(data_type="regular")
        self.plot_homepage_details_distribution(data_type="regular", match_type_filter="exact_match") 
        
        self.plot_homepage_details_distribution(data_type="regular", match_type_filter="std_match") 
        
        self.plot_upset_diagram(data_type="regular")
        self.plot_match_type_distribution(data_type="version")
        self.plot_homepage_details_distribution(data_type="version", match_type_filter="exact_match")
        
        self.plot_homepage_details_distribution(data_type="version", match_type_filter="std_match")        
        self.plot_upset_diagram(data_type="version")

if __name__ == "__main__":
    analyzer = PackageAnalyzer()
    analyzer.run_all_analysis() 