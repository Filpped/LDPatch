import json
from relibrary.utils.files.file_operations import load_json

# 从JSON文件中读取数据
def read_json_file(file_path):
    """
    从JSON文件中读取数据
    
    Args:
        file_path: JSON文件路径
        
    Returns:
        dict: 加载的JSON数据，失败则返回None
    """
    return load_json(file_path)

# 计算单个软件包的补丁数量
def calculate_patch_counts_for_package(package_data):
    """
    计算单个软件包的补丁数量
    
    Args:
        package_data: 软件包补丁数据
        
    Returns:
        tuple: (fedora补丁数量, openeuler补丁数量)
    """
    common_patches = package_data.get("common_patches", [])
    unique_fedora_patches = package_data.get("unique_fedora_patches", [])
    unique_openeuler_patches = package_data.get("unique_openeuler_patches", [])
    same_content_different_names = package_data.get("same_content_different_names", [])

    # 计算补丁数量
    fedora_patches_count = len(common_patches) + len(unique_fedora_patches) + len(same_content_different_names)
    openeuler_patches_count = len(common_patches) + len(unique_openeuler_patches) + len(same_content_different_names)

    return fedora_patches_count, openeuler_patches_count

# 计算所有软件包的补丁数量和总数量
def calculate_patch_counts_for_all_packages(data):
    """
    计算所有软件包的补丁数量和总数量
    
    Args:
        data: 包含所有软件包补丁数据的字典
        
    Returns:
        tuple: (每个包的补丁数量字典, fedora总补丁数, openeuler总补丁数)
    """
    packages_comparison = data.get("packages_comparison", {})
    results = {}

    # 初始化补丁总数
    total_fedora_patches = 0
    total_openeuler_patches = 0

    # 计算每个软件包的补丁数量，并累加到总数
    for package_name, package_data in packages_comparison.items():
        fedora_count, openeuler_count = calculate_patch_counts_for_package(package_data)
        results[package_name] = {
            "fedora_patches_count": fedora_count,
            "openeuler_patches_count": openeuler_count
        }
        total_fedora_patches += fedora_count
        total_openeuler_patches += openeuler_count

    return results, total_fedora_patches, total_openeuler_patches

# 主函数
def main():
    """主函数，分析补丁总数并输出结果"""
    # JSON文件路径
    json_file_path = "patch_comparison_report_Manual.json"

    # 读取JSON文件
    data = read_json_file(json_file_path)
    
    if not data:
        print(f"无法加载文件: {json_file_path}")
        return

    # 计算所有软件包的补丁数量和总数量
    results, total_fedora, total_openeuler = calculate_patch_counts_for_all_packages(data)

    # 输出每个软件包的补丁数量
    for package_name, counts in results.items():
        print(f"软件包: {package_name}")
        print(f"  Fedora中的补丁数量: {counts['fedora_patches_count']}")
        print(f"  OpenEuler中的补丁数量: {counts['openeuler_patches_count']}")
        print("-" * 30)

    # 输出补丁总数量
    print("所有软件包的补丁总数量：")
    print(f"  Fedora中的补丁总数量: {total_fedora}")
    print(f"  OpenEuler中的补丁总数量: {total_openeuler}")

if __name__ == "__main__":
    main()
