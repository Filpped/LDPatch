#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json

def is_empty_or_none(data):
    """检查数据是否为空列表或None"""
    if data is None:
        return True
    if isinstance(data, list) and len(data) == 0:
        return True
    return False

def should_remove_package(pkg_data):
    """判断软件包是否应该被移除"""
    # 检查软件包的error是否为null或不存在
    if pkg_data.get("error") is not None:
        return False
    
    # 获取关键字段
    common_patches = pkg_data.get("common_patches", [])
    same_function_different_content = pkg_data.get("same_function_different_content", [])
    unique_fedora_patches = pkg_data.get("unique_fedora_patches", [])
    unique_openeuler_patches = pkg_data.get("unique_openeuler_patches", [])
    
    # 情况1：common_patches, same_function_different_content, unique_fedora_patches, unique_openeuler_patches均为空
    if (is_empty_or_none(common_patches) and 
        is_empty_or_none(same_function_different_content) and 
        is_empty_or_none(unique_fedora_patches) and 
        is_empty_or_none(unique_openeuler_patches)):
        return True
    
    # 情况2：common_patches, same_function_different_content, unique_fedora_patches均为空
    if (is_empty_or_none(common_patches) and 
        is_empty_or_none(same_function_different_content) and 
        is_empty_or_none(unique_fedora_patches)):
        return True
    
    # 情况3：common_patches, same_function_different_content, unique_openeuler_patches均为空
    if (is_empty_or_none(common_patches) and 
        is_empty_or_none(same_function_different_content) and 
        is_empty_or_none(unique_openeuler_patches)):
        return True
    
    # 情况4：same_function_different_content, unique_fedora_patches, unique_openeuler_patches均为空
    if (is_empty_or_none(same_function_different_content) and 
        is_empty_or_none(unique_fedora_patches) and 
        is_empty_or_none(unique_openeuler_patches)):
        return True
    
    return False

def main():
    # 读取important.json文件
    with open('important.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 获取packages_comparison部分
    packages_comparison = data.get('packages_comparison', {})
    
    # 创建新的packages_comparison，移除符合条件的软件包
    new_packages_comparison = {}
    removed_count = 0
    
    for pkg_name, pkg_data in packages_comparison.items():
        if should_remove_package(pkg_data):
            removed_count += 1
            continue
        new_packages_comparison[pkg_name] = pkg_data
    
    # 创建新的数据结构
    new_data = {'packages_comparison': new_packages_comparison}
    
    # 将过滤后的数据写入important_patch.json
    with open('important_patch.json', 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    
    print(f"处理完成！共删除了 {removed_count} 个软件包，结果已保存到 important_patch.json")

if __name__ == "__main__":
    main() 