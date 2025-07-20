import os
import time
import html
from relibrary.core.package_analyzer import get_package_list, sort_packages, compare_packages, find_similar_packages
from relibrary.utils.files.file_operations import save_json, load_json, ensure_dir


class PackageComparer:
    
    def __init__(self, distributions):
        self.distributions = distributions
        self.package_data = {}
    
    def fetch_package_data(self, force_refresh=False):
        cache_dir = "data/packages"
        ensure_dir(cache_dir)
        
        result = {}
        
        for dist in self.distributions:
            cache_file = f"{cache_dir}/{dist.lower().replace('-', '_')}_packages.json"
            if not force_refresh and os.path.exists(cache_file):
                data = load_json(cache_file)
                if data:
                    result[dist] = data
                    continue
            data = get_package_list(dist)
            
            if data:
                save_json(data, cache_file)
                result[dist] = data
        
        self.package_data = result
        return result
    
    def compare_all(self, output_dir="data/comparison"):
        if len(self.package_data) < 2:
            return {}
        
        ensure_dir(output_dir)

        comparisons = {}
        for i, dist1 in enumerate(self.distributions):
            for j in range(i+1, len(self.distributions)):
                dist2 = self.distributions[j]
                
                if dist1 not in self.package_data or dist2 not in self.package_data:
                    continue
                
                comparison_key = f"{dist1}_vs_{dist2}"
                comparison_result = compare_packages(
                    self.package_data[dist1],
                    self.package_data[dist2]
                )
                
                output_file = f"{output_dir}/{comparison_key}.json"
                save_json(comparison_result, output_file)
                
                comparisons[comparison_key] = comparison_result
        
        return comparisons
    
    def find_similar_packages_for_unique(self, comparison_results, threshold=0.5, max_similar=5):
       
        enhanced_results = {}
        
        for comparison_key, comparison_data in comparison_results.items():
            dist1, dist2 = comparison_key.split("_vs_")
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
            
            enhanced_result = dict(comparison_data)
            enhanced_result["similar_packages"] = {
                dist1: similar_packages_1,
                dist2: similar_packages_2
            }
            
            enhanced_results[comparison_key] = enhanced_result
        
        return enhanced_results
    
    def generate_html_report(self, comparison_results, output_file="package_comparison.html"):
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>REPORT</title>
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
        <h1>REPORT</h1>
        <p>TIME: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
"""

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
                        <h3>COMMON</h3>
                        <p class="common">{len(common_pkgs)}</p>
                    </div>
                    <div class="stat-item">
                        <h3>{dist1}UNIQUE</h3>
                        <p class="unique">{len(only_in_1)}</p>
                    </div>
                    <div class="stat-item">
                        <h3>{dist2}UNIQUE</h3>
                        <p class="unique">{len(only_in_2)}</p>
                    </div>
                </div>
            </div>
            
            <div class="search-box">
                <input type="text" id="search-{comparison_key}" placeholder="SEARING..." onkeyup="filterPackages('{comparison_key}')">
            </div>
            
            <div class="tabs">
                <div class="tab active" onclick="showTab('{comparison_key}', 'common')">PACKAGE</div>
                <div class="tab" onclick="showTab('{comparison_key}', 'only1')">ONLY IN {dist1}</div>
                <div class="tab" onclick="showTab('{comparison_key}', 'only2')">ONLY IN {dist2}</div>
            </div>
            
            <div id="{comparison_key}-common" class="tab-content active">
                <h3>COMMON_PACKAGE ({len(common_pkgs)})</h3>
                <table id="{comparison_key}-common-table">
                    <tr>
                        <th>PACKAGE_NAME</th>
                    </tr>
"""
            for pkg in common_pkgs:
                html_content += f"                    <tr><td>{html.escape(pkg)}</td></tr>\n"
            
            html_content += f"""
                </table>
            </div>
            
            <div id="{comparison_key}-only1" class="tab-content">
                <h3>{dist1}UNIQUE ({len(only_in_1)})</h3>
                <table id="{comparison_key}-only1-table">
                    <tr>
                        <th>PACKAGE_NAME</th>
                    </tr>
"""
            for pkg in only_in_1:
                html_content += f"                    <tr><td>{html.escape(pkg)}</td></tr>\n"
            
            html_content += f"""
                </table>
            </div>
            
            <div id="{comparison_key}-only2" class="tab-content">
                <h3>{dist2}UNIQUE_PACKAGE ({len(only_in_2)})</h3>
                <table id="{comparison_key}-only2-table">
                    <tr>
                        <th>PACKAGE_NAME</th>
                    </tr>
"""
            
            for pkg in only_in_2:
                html_content += f"                    <tr><td>{html.escape(pkg)}</td></tr>\n"
            
            html_content += """
                </table>
            </div>
        </div>
"""
        
        html_content += """
        <script>
            function showTab(comparisonKey, tabName) {
                document.querySelectorAll(`[id^="${comparisonKey}-"]`).forEach(el => {
                    el.classList.remove('active');
                });
                document.querySelectorAll('.tab').forEach(el => {
                    el.classList.remove('active');
                });
                
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
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            return True
        except Exception as e:
            return False

def compare_distribution_packages(distributions, output_dir="data/comparison", html_report=True):
  
    comparer = PackageComparer(distributions)
    
    comparer.fetch_pa/ckage_data()
    
    comparison_results = comparer.compare_all(output_dir)
    
    enhanced_results = comparer.find_similar_packages_for_unique(comparison_results)
    
    enhanced_output_file = f"{output_dir}/enhanced_comparison.json"
    save_json(enhanced_results, enhanced_output_file)
    
    if html_report:
        html_output_file = f"{output_dir}/package_comparison.html"
        comparer.generate_html_report(comparison_results, html_output_file)
    
    return enhanced_results

if __name__ == "__main__":
    distributions = ['Fedora', 'openEuler-24.03']
    compare_distribution_packages(distributions) 