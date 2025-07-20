import json
from relibrary.utils.files.file_operations import load_json

def read_json_file(file_path):
    return load_json(file_path)

def calculate_patch_counts_for_package(package_data):
    common_patches = package_data.get("common_patches", [])
    unique_fedora_patches = package_data.get("unique_fedora_patches", [])
    unique_openeuler_patches = package_data.get("unique_openeuler_patches", [])
    same_content_different_names = package_data.get("same_content_different_names", [])

    fedora_patches_count = len(common_patches) + len(unique_fedora_patches) + len(same_content_different_names)
    openeuler_patches_count = len(common_patches) + len(unique_openeuler_patches) + len(same_content_different_names)

    return fedora_patches_count, openeuler_patches_count

def calculate_patch_counts_for_all_packages(data):
 
    packages_comparison = data.get("packages_comparison", {})
    results = {}
    total_fedora_patches = 0
    total_openeuler_patches = 0

    for package_name, package_data in packages_comparison.items():
        fedora_count, openeuler_count = calculate_patch_counts_for_package(package_data)
        results[package_name] = {
            "fedora_patches_count": fedora_count,
            "openeuler_patches_count": openeuler_count
        }
        total_fedora_patches += fedora_count
        total_openeuler_patches += openeuler_count

    return results, total_fedora_patches, total_openeuler_patches

def main():
    json_file_path = "patch_comparison_report_Manual.json"

    data = read_json_file(json_file_path)
    
    if not data:
        return

    results, total_fedora, total_openeuler = calculate_patch_counts_for_all_packages(data)

    for package_name, counts in results.items():
        print("-" * 30)
if __name__ == "__main__":
    main()
