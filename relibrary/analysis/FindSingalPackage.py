#!/usr/bin/env python3
"""
分析各个发行版独有的软件包（不与其他发行版有同源软件包）
"""

import os
import json
import logging
import sys
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def analyze_package_exclusivity(data_file, data_type="regular"):
    """分析各发行版独有的软件包"""
    
    logging.info(f"加载数据文件: {data_file}")
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"加载数据失败: {e}")
        return
        
    # 发行版列表
    distros = ['ubuntu-24.04', 'debian', 'fedora', 'openeuler-24.03']
    
    # 显示部分JSON结构以理解数据格式
    sample_keys = list(data.keys())[:3]
    logging.info(f"数据文件包含以下键: {', '.join(sample_keys)}...")
    
    # 获取单个发行版的所有包
    all_distro_packages = {}
    for distro in distros:
        all_key = f"{distro}_all"
        if all_key in data:
            all_distro_packages[distro] = data[all_key]
            logging.info(f"{distro} 总包数: {len(all_distro_packages[distro])}")
        else:
            logging.warning(f"未找到 {all_key} 数据")
            all_distro_packages[distro] = {}
    
    # 提取所有两两发行版之间的交集数据
    intersection_data = {}
    for i, distro1 in enumerate(distros):
        for j, distro2 in enumerate(distros[i+1:], i+1):
            key = f"{distro1}_{distro2}_common"
            reversed_key = f"{distro2}_{distro1}_common"
            
            if key in data:
                intersection_data[(distro1, distro2)] = data[key]
                logging.info(f"{distro1} 与 {distro2} 共有包: {len(data[key])}")
            elif reversed_key in data:
                intersection_data[(distro1, distro2)] = data[reversed_key]
                logging.info(f"{distro1} 与 {distro2} 共有包: {len(data[reversed_key])}")
    
    # 计算独有包数量
    exclusive_packages = {}
    for distro in distros:

        all_pkg_set = set(all_distro_packages[distro].keys())
        shared_pkg_set = set()
        
        # 找出与所有其他发行版交集的包
        for other_distro in distros:
            if other_distro == distro:
                continue
                
            # 确定交集的键
            if (distro, other_distro) in intersection_data:
                shared_pkg_set.update(intersection_data[(distro, other_distro)].keys())
            elif (other_distro, distro) in intersection_data:
                shared_pkg_set.update(intersection_data[(other_distro, distro)].keys())
        
        exclusive_pkg_set = all_pkg_set - shared_pkg_set
        exclusive_packages[distro] = exclusive_pkg_set
        
        logging.info(f"{distro} 分析结果:")
        logging.info(f"  总包数: {len(all_pkg_set)}")
        logging.info(f"  共享包数: {len(shared_pkg_set)}")
        logging.info(f"  独有包数: {len(exclusive_pkg_set)}")
    
    # 输出结果
    suffix = "无版本约束" if data_type == "regular" else "有版本约束"
    print(f"\n各发行版独有软件包统计 ({suffix}):")
    print("-" * 40)
    
    for distro in distros:
        if distro in exclusive_packages:
            count = len(exclusive_packages[distro])
            total = len(all_distro_packages.get(distro, {}))
            percentage = (count / total * 100) if total > 0 else 0
            
            display_name = distro.split('-')[0].capitalize()
            if display_name == "Openeuler":
                display_name = "OpenEuler"
                
            print(f"{display_name}独有的软件包：{count}个 ({percentage:.2f}%)")
    
    if "openeuler-24.03" in all_distro_packages and "fedora" in all_distro_packages:
        # 检查OpenEuler与Fedora的交集
        shared_count = 0
        if ("openeuler-24.03", "fedora") in intersection_data:
            shared_count = len(intersection_data[("openeuler-24.03", "fedora")])
        elif ("fedora", "openeuler-24.03") in intersection_data:
            shared_count = len(intersection_data[("fedora", "openeuler-24.03")])
            
        openeuler_total = len(all_distro_packages["openeuler-24.03"])
        openeuler_excl = len(exclusive_packages["openeuler-24.03"])
        
        print("\n验证OpenEuler数据:")
        print(f"OpenEuler总包数: {openeuler_total}")
        print(f"与Fedora共有包数: {shared_count}")
        print(f"计算得独有包数: {openeuler_excl}")
        print(f"理论最大独有包数: {openeuler_total - shared_count}")
    
    return exclusive_packages

def main():
    """主函数"""
    # 查找JSON数据文件
    data_paths = [
        "./package_analysis.json",
        "./data/packages/package_analysis.json",
        "../data/packages/package_analysis.json",
        "../../data/packages/package_analysis.json",
    ]
    
    data_file = None
    
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        data_file = sys.argv[1]
    else:
        for path in data_paths:
            if os.path.exists(path):
                data_file = path
                break
    
    if not data_file:
        print("错误：未找到数据文件。请提供正确的文件路径作为命令行参数。")
        print("用法: python FindSingalPackage.py [数据文件路径]")
        return
        
    print(f"\n=== 使用数据文件: {data_file} ===")
    print(f"\n=== 分析无版本约束情况下各发行版独有的软件包 ===")
    analyze_package_exclusivity(data_file, data_type="regular")
        
    # 检查是否有版本约束数据
    version_data_file = data_file.replace("package_analysis.json", "package_analysis_withVersion.json")
    if os.path.exists(version_data_file):
        print("\n=== 分析有版本约束情况下各发行版独有的软件包 ===")
        analyze_package_exclusivity(version_data_file, data_type="version")
    else:
        print(f"\n未找到版本约束数据文件: {version_data_file}")

if __name__ == "__main__":
    main()
