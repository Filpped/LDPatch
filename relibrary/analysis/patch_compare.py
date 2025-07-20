import os
import logging
import json
from collections import defaultdict
from relibrary.core.patch_analyzer import get_patch_names, get_patch_file_content, analyze_patch
from relibrary.utils.files.file_operations import load_json, save_json

logging.basicConfig(
    filename='patch_comparison.log',
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

class PatchComparer:
    
    def __init__(self, distributions, source_dir="/home/XXX/rpmbuild/SOURCES"):

        self.distributions = distributions
        self.source_dir = source_dir
        self.results = {}
    
    def load_package_data(self, json_file):

        data = load_json(json_file)
        if not data:
            logging.error(f"ERROR: {json_file}")
            return {}
        return data
    
    def get_spec_content(self, distribution, package_name):
        spec_path = f"/home/XXX/rpmbuild/SPECS/{package_name}.spec"
        command = f"wsl -d {distribution} bash -c 'cat \"{spec_path}\"'"
        
        try:
            import subprocess
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                return None
        except Exception as e:
            return None
    
    def compare_patches(self, package_name):
        if len(self.distributions) < 2:
            return {}
        
        patches_by_dist = {}
        
        for dist in self.distributions:
            spec_content = self.get_spec_content(dist, package_name)
            if not spec_content:
                patches_by_dist[dist] = []
                continue
            
            patches = get_patch_names(spec_content)
            patches_by_dist[dist] = patches
        
        all_patches_info = {}
        for dist, patches in patches_by_dist.items():
            all_patches_info[dist] = {}
            for patch in patches:
                patch_content = get_patch_file_content(dist, patch, self.source_dir)
                if patch_content:
                    patch_info = analyze_patch(patch_content)
                    all_patches_info[dist][patch] = patch_info
        
        comparison_results = {}
        for i, dist1 in enumerate(self.distributions):
            for j in range(i+1, len(self.distributions)):
                dist2 = self.distributions[j]
                
                patches1 = set(patches_by_dist.get(dist1, []))
                patches2 = set(patches_by_dist.get(dist2, []))
                
                common_patches = patches1.intersection(patches2)
                only_in_dist1 = patches1 - patches2
                only_in_dist2 = patches2 - patches1
                
                comparison_key = f"{dist1}_vs_{dist2}"
                comparison_results[comparison_key] = {
                    "common_patches": list(common_patches),
                    f"only_in_{dist1}": list(only_in_dist1),
                    f"only_in_{dist2}": list(only_in_dist2),
                    "patch_details": {
                        dist1: all_patches_info.get(dist1, {}),
                        dist2: all_patches_info.get(dist2, {})
                    }
                }
        
        return comparison_results
    
    def compare_multiple_packages(self, package_list, output_file=None):
        all_results = {}
        
        for package in package_list:
            result = self.compare_patches(package)
            if result:
                all_results[package] = result
        
        if output_file:
            save_json(all_results, output_file)
        
        return all_results
    
    def generate_comparison_report(self, comparison_results, output_file):
        report = {
            "summary": {
                "total_packages": len(comparison_results),
                "distributions": self.distributions,
            },
            "details": comparison_results
        }
        
        stats = defaultdict(lambda: {"common": 0, "unique": 0})
        for package, pkg_result in comparison_results.items():
            for comparison_key, comparison_data in pkg_result.items():
                dist1, dist2 = comparison_key.split("_vs_")
                stats[comparison_key]["common"] += len(comparison_data.get("common_patches", []))
                stats[comparison_key][f"only_in_{dist1}"] = len(comparison_data.get(f"only_in_{dist1}", []))
                stats[comparison_key][f"only_in_{dist2}"] = len(comparison_data.get(f"only_in_{dist2}", []))
        
        report["summary"]["statistics"] = dict(stats)
        
        return save_json(report, output_file)

def compare_patches_between_distros(
    distributions, 
    packages_json, 
    output_file="rpm_patch_comparison_report.json", 
    source_dir="/home/XXX/rpmbuild/SOURCES"
):

    comparer = PatchComparer(distributions, source_dir)
    
    packages_data = comparer.load_package_data(packages_json)
    if not packages_data:
        return {}
    
    packages_to_compare = packages_data.get("common", [])
    if not packages_to_compare:
        return {}

    max_packages = 100
    if len(packages_to_compare) > max_packages:
        packages_to_compare = packages_to_compare[:max_packages]
    
    result = comparer.compare_multiple_packages(packages_to_compare)


    comparer.generate_comparison_report(result, output_file)
    
    return result

if __name__ == "__main__":
    distributions = ['Fedora', 'openEuler-24.03']
    packages_json = "common_packages.json"
    output_file = "patch_comparison_report.json"
    
    compare_patches_between_distros(distributions, packages_json, output_file) 