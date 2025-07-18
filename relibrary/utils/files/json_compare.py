"""
JSON比较工具模块，提供JSON文件的比较功能
"""

import json
import logging
from relibrary.utils.files.file_operations import load_json, save_json

def compare_json_objects(json1, json2):
    """
    比较两个JSON对象，返回差异
    
    Args:
        json1: 第一个JSON对象
        json2: 第二个JSON对象
        
    Returns:
        dict: 差异字典
    """
    diff = {}

    # 比较json1与json2的差异
    for key in json1:
        if key not in json2:
            diff[key] = {'status': 'only_in_json1', 'value': json1[key]}
        elif json1[key] != json2[key]:
            diff[key] = {'status': 'different', 'json1_value': json1[key], 'json2_value': json2[key]}

    # 找出json2中有而json1中没有的键
    for key in json2:
        if key not in json1:
            diff[key] = {'status': 'only_in_json2', 'value': json2[key]}

    return diff

def compare_json_files(file1, file2, output_file=None):
    """
    比较两个JSON文件并返回差异
    
    Args:
        file1: 第一个JSON文件路径
        file2: 第二个JSON文件路径
        output_file: 输出文件路径，如不提供则不保存
        
    Returns:
        dict: 差异字典
    """
    logging.info(f"比较JSON文件: {file1} 和 {file2}")
    
    # 加载JSON文件
    json1 = load_json(file1)
    if json1 is None:
        logging.error(f"无法加载JSON文件: {file1}")
        return None
    
    json2 = load_json(file2)
    if json2 is None:
        logging.error(f"无法加载JSON文件: {file2}")
        return None
    
    # 比较JSON
    diff = compare_json_objects(json1, json2)
    
    # 保存差异结果（如果提供了输出文件）
    if output_file:
        save_json(diff, output_file)
        logging.info(f"差异已保存到: {output_file}")
    
    return diff

def summarize_diff(diff):
    """
    汇总比较结果，生成简洁的摘要
    
    Args:
        diff: 差异字典
        
    Returns:
        dict: 包含摘要信息的字典
    """
    summary = {
        'only_in_json1': 0,
        'only_in_json2': 0,
        'different': 0,
        'total_keys': len(diff)
    }
    
    different_keys = []
    only_in_json1_keys = []
    only_in_json2_keys = []
    
    for key, info in diff.items():
        status = info.get('status')
        if status == 'only_in_json1':
            summary['only_in_json1'] += 1
            only_in_json1_keys.append(key)
        elif status == 'only_in_json2':
            summary['only_in_json2'] += 1
            only_in_json2_keys.append(key)
        elif status == 'different':
            summary['different'] += 1
            different_keys.append(key)
    
    summary['different_keys'] = different_keys
    summary['only_in_json1_keys'] = only_in_json1_keys
    summary['only_in_json2_keys'] = only_in_json2_keys
    
    return summary

if __name__ == "__main__":
    # 使用示例
    file1 = "patch_comparison_report_v1.json"
    file2 = "patch_comparison_report_v2.json"
    output_file = "diff.json"
    
    diff = compare_json_files(file1, file2, output_file)
    if diff:
        summary = summarize_diff(diff)
        print(f"比较结果摘要:")
        print(f"  - 总键数: {summary['total_keys']}")
        print(f"  - 仅在JSON1中: {summary['only_in_json1']}")
        print(f"  - 仅在JSON2中: {summary['only_in_json2']}")
        print(f"  - 值不同: {summary['different']}")
        print(f"差异已保存到 {output_file}") 