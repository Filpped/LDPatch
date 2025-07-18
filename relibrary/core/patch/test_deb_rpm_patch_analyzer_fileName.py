#!/usr/bin/env python3
"""
测试Debian和Fedora补丁分析器，自动对两个发行版的共同软件包进行补丁比较

功能特点：
1. 支持从Fedora的spec文件中提取补丁信息
2. 支持从Debian的debian/patches目录提取补丁信息
3. 使用哈希比对和相似度算法进行补丁匹配
4. 分析结果包括：完全相同补丁、功能相同但内容不同的补丁、各发行版独有补丁

"""

import sys
import os
import logging
import json
import argparse
import subprocess
from datetime import datetime
import hashlib
import traceback
import tempfile
import shutil
import platform


current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../.."))
sys.path.insert(0, project_root)

from relibrary.core.patch.deb_rpm_patch_analyzer_fileName import (
    find_debian_patch_dir,
    get_debian_patch_names,
    get_debian_patch_file_content,
    compare_fedora_debian_patches,
    analyze_fedora_debian_patches,
    find_srpm_file
)

from relibrary.core.patch.rpm_patch_analyzer_fileName import (
    get_patch_names,
    get_patch_file_content,
    analyze_patch,
    normalize_patch_content,
    extract_patch_features,
    calculate_patch_similarity,
    compare_patches
)

DEFAULT_COMMON_PACKAGES_FILE = "data/packages/debian_fedora_packages.json"
DEFAULT_FEDORA_SPEC_DIR = "/home/penny/rpmbuild/SPECS"
DEFAULT_DEBIAN_BASE_DIR = "/home/penny/packages_info"
DEFAULT_OUTPUT_DIR = "data/patches"
DEFAULT_OUTPUT_FILE = "deb_rpm_patch_comparison_report.json"
DEFAULT_LOG_FILE = "data/patches/deb_rpm_patches.log"
DEFAULT_FEDORA_DISTRO = "Fedora"
DEFAULT_DEBIAN_DISTRO = "Debian"

IS_WINDOWS = platform.system() == "Windows"

def check_wsl_path_exists(path, distro="Fedora"):
    """
    使用WSL命令检查路径是否存在
    
    Args:
        path: 要检查的路径
        distro: WSL发行版名称
        
    Returns:
        bool: 路径是否存在
    """
    if not path:
        return False
    path = path.replace("\\", "/")  
    cmd = f"wsl -d {distro} bash -c 'test -e \"{path}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\"'"
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',  
        errors='replace'   
    )
    return "EXISTS" in result.stdout

def normalize_path(path):
    """
    确保路径使用正确的分隔符，Windows下转换为适用于WSL的路径
    
    Args:
        path: 需要规范化的路径
        
    Returns:
        str: 规范化后的路径，使用Linux风格的正斜杠
    """
    if path:
        return path.replace("\\", "/")
    return path


def setup_logging(log_file=DEFAULT_LOG_FILE):
    """
    设置日志配置
    
    Args:
        log_file: 日志文件路径
    """

    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)
    

    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers:
            root_logger.removeHandler(handler)
    
    # 配置日志
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    console_handler = logging.StreamHandler()
    
    # 设置格式 - 包含更详细的文件和行号信息
    log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
    file_handler.setFormatter(log_format)
    console_handler.setFormatter(log_format)
    
    # 设置级别 - 设置为DEBUG以输出更多信息
    root_logger.setLevel(logging.DEBUG)
    file_handler.setLevel(logging.DEBUG)
    console_handler.setLevel(logging.INFO)  # 控制台只显示INFO及以上
    
    # 添加处理程序
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # 记录开始信息
    logging.info(f"===== 补丁分析开始于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====")
    logging.info(f"使用Fedora发行版: {DEFAULT_FEDORA_DISTRO}")
    logging.info(f"使用Debian发行版: {DEFAULT_DEBIAN_DISTRO}")
    logging.info(f"使用Debian包信息目录: {DEFAULT_DEBIAN_BASE_DIR}")
    logging.info(f"输出目录: {DEFAULT_OUTPUT_DIR}")
    logging.info(f"日志文件: {log_file}")
    
    # 测试日志是否正常工作
    logging.debug("这是一条调试消息")
    logging.info("日志系统已初始化，级别设置为DEBUG")

def load_common_packages(json_file=DEFAULT_COMMON_PACKAGES_FILE):
    """
    从JSON文件加载Fedora和Debian的共同软件包数据
    
    Args:
        json_file: 包含共同软件包数据的JSON文件路径
        
    Returns:
        dict: 共同软件包数据字典
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            package_data = json.load(f)
        
        # 查找debian_fedora_common键
        if "debian_fedora_common" in package_data:
            common_packages = package_data["debian_fedora_common"]
            logging.info(f"从{json_file}加载了{len(common_packages)}个共同软件包")
            return common_packages
        else:
            # 尝试查找其他可能的键名
            alternative_keys = [k for k in package_data.keys() if "debian" in k.lower() and "fedora" in k.lower()]
            if alternative_keys:
                common_packages = package_data[alternative_keys[0]]
                logging.info(f"使用替代键'{alternative_keys[0]}'，加载了{len(common_packages)}个共同软件包")
                return common_packages
            else:
                logging.error(f"在{json_file}中找不到debian_fedora_common键或其他适用的替代键")
                return {}
    except Exception as e:
        logging.error(f"加载共同软件包数据出错: {e}")
        return {}

def test_debian_patch_extraction(package_name, debian_base_dir=DEFAULT_DEBIAN_BASE_DIR):
    """测试Debian补丁提取功能"""
    logging.info(f"测试Debian补丁提取功能: {package_name}")
    
    # 规范化路径
    debian_base_dir = normalize_path(debian_base_dir)
    
    # 查找Debian补丁目录
    patches_dir, series_file, has_patches = find_debian_patch_dir(package_name, debian_base_dir)
    
    if not has_patches:
        logging.info(f"Debian包中没有补丁: {package_name}")
        return []
    
    # 获取补丁名列表
    patch_names = get_debian_patch_names(series_file, patches_dir)
    logging.info(f"找到 {len(patch_names)} 个Debian补丁")
    
    results = {}
    for patch_name in patch_names:
        logging.info(f"分析补丁: {patch_name}")
        
        # 获取补丁内容
        patch_content = get_debian_patch_file_content(patch_name, patches_dir)
        if not patch_content:
            logging.warning(f"无法读取补丁内容: {patch_name}")
            continue
        
        # 分析补丁
        patch_info_data = analyze_patch(patch_content)
        
        # 标准化补丁内容
        normalized_content = normalize_patch_content(patch_content)
        
        # 默认Debian补丁使用-p1级别
        strip_level = 1
        
        # 提取特征
        features = extract_patch_features(normalized_content, strip_level)
        
        # 保存结果
        results[patch_name] = {
            "info": patch_info_data,
            "features": features,
            "strip_level": strip_level
        }
    
    # 输出结果
    output_dir = DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{package_name}_debian_patches.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logging.info(f"Debian补丁分析结果已保存到: {output_file}")
    return results

def test_fedora_patch_extraction(package_name, fedora_dist=DEFAULT_FEDORA_DISTRO, spec_dir=DEFAULT_FEDORA_SPEC_DIR):
    """测试Fedora补丁提取功能"""
    logging.info(f"测试Fedora补丁提取功能: {package_name}")
    
    # 规范化路径
    spec_dir = normalize_path(spec_dir)
    
    # 构建spec文件路径
    spec_file = os.path.join(spec_dir, f"{package_name}.spec")
    spec_file = normalize_path(spec_file)
    
    # 读取spec文件
    command_cat = f"wsl -d {fedora_dist} bash -c 'cat \"{spec_file}\"'"
    result_cat = subprocess.run(
        command_cat,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    if result_cat.returncode != 0:
        logging.warning(f"读取spec文件失败: {spec_file}，尝试从fedora_sources安装SRPM")
        # 尝试从fedora_sources目录安装SRPM
        from relibrary.core.patch.deb_rpm_patch_analyzer_fileName import find_srpm_file
        
        # 使用改进的函数查找SRPM文件
        srpm_path = find_srpm_file(package_name)
        
        if srpm_path:
            # 提取文件名
            srpm_file = os.path.basename(srpm_path)
            logging.info(f"使用SRPM文件: {srpm_file}")
            
            # 安装SRPM
            srpm_dir = os.path.dirname(srpm_path)
            install_cmd = f"wsl -d {fedora_dist} bash -c 'cd \"{srpm_dir}\" && rpm -ivh {srpm_file}'"
            logging.info(f"执行安装SRPM命令: {install_cmd}")
            install_result = subprocess.run(
                install_cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if install_result.returncode == 0:
                logging.info(f"SRPM安装成功，重试读取spec文件")
                # 重新尝试读取spec文件
                fedora_result = subprocess.run(
                    command_cat,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                if fedora_result.returncode != 0:
                    logging.error(f"安装SRPM后仍无法读取Fedora spec文件: {spec_file}")
                    return None
            else:
                logging.error(f"安装SRPM失败: {install_result.stderr}")
                return None
        else:
            logging.error(f"在fedora_sources目录中未找到{package_name}的SRPM文件")
            return None
    
    spec_content = result_cat.stdout
    
    # 从spec文件中提取补丁名称和忽略级别信息
    patch_info = get_patch_info(spec_content)
    patches = list(patch_info.keys())
    logging.info(f"找到 {len(patches)} 个Fedora补丁")
    
    results = {}
    for patch_name in patches:
        logging.info(f"分析补丁: {patch_name}")
        
        # 获取补丁内容
        patch_content = get_patch_file_content(fedora_dist, patch_name)
        if not patch_content:
            logging.warning(f"无法读取补丁内容: {patch_name}")
            continue
        
        # 分析补丁
        patch_info_data = analyze_patch(patch_content)
        
        # 标准化补丁内容
        normalized_content = normalize_patch_content(patch_content)
        
        # 获取忽略路径级别
        strip_level = patch_info.get(patch_name, {}).get('strip_level', 0)
        
        # 提取特征
        features = extract_patch_features(normalized_content, strip_level)
        
        # 保存结果
        results[patch_name] = {
            "info": patch_info_data,
            "features": features,
            "strip_level": strip_level
        }
    
    # 输出结果
    output_dir = DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{package_name}_fedora_patches.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logging.info(f"Fedora补丁分析结果已保存到: {output_file}")
    return results

def test_distro_comparison(package_name, fedora_name=None, debian_name=None, fedora_spec=None, debian_base_dir=DEFAULT_DEBIAN_BASE_DIR, fedora_dist=DEFAULT_FEDORA_DISTRO, similarity_threshold=0.7):
    """测试两个发行版的补丁比较功能"""
    # 使用提供的特定发行版包名，如果未提供则使用通用包名
    fedora_package_name = fedora_name or package_name
    debian_package_name = debian_name or package_name
    
    logging.info(f"比较发行版补丁: Fedora({fedora_package_name}) vs Debian({debian_package_name})")
    
    # 规范化路径
    debian_base_dir = normalize_path(debian_base_dir)
    
    # 如果未提供Fedora spec文件路径，构建默认路径
    if not fedora_spec:
        fedora_spec = normalize_path(os.path.join(DEFAULT_FEDORA_SPEC_DIR, f"{fedora_package_name}.spec"))
    else:
        fedora_spec = normalize_path(fedora_spec)
    
    # 检查fedora_spec是否存在，如果不存在，尝试使用其他可能的目录
    if not check_wsl_path_exists(fedora_spec, fedora_dist):
        logging.warning(f"Fedora spec文件不存在: {fedora_spec}")
        
        # 尝试直接使用rpmbuild/SOURCES目录
        fedora_source_dir = normalize_path("/home/penny/rpmbuild/SOURCES")
        if check_wsl_path_exists(fedora_source_dir, fedora_dist):
            logging.info(f"使用Fedora源码目录: {fedora_source_dir}")
            fedora_patch_dir = fedora_source_dir
        else:
            # 如果SOURCES目录也不存在，则尝试创建一个临时目录
            temp_dir = tempfile.mkdtemp(prefix="fedora_patch_")
            logging.warning(f"创建临时目录作为Fedora补丁目录: {temp_dir}")
            fedora_patch_dir = normalize_path(temp_dir)
    else:
        # 使用SOURCES目录作为补丁目录，而不是spec文件所在目录
        fedora_patch_dir = normalize_path("/home/penny/rpmbuild/SOURCES")
        logging.info(f"Fedora spec文件存在，使用SOURCES目录作为补丁目录: {fedora_patch_dir}")
        
        # 确保SOURCES目录存在
        if not check_wsl_path_exists(fedora_patch_dir, fedora_dist):
            logging.warning(f"Fedora SOURCES目录不存在: {fedora_patch_dir}")
            # 如果SOURCES目录不存在，创建临时目录
            temp_dir = tempfile.mkdtemp(prefix="fedora_patch_")
            logging.warning(f"创建临时目录作为Fedora补丁目录: {temp_dir}")
            fedora_patch_dir = normalize_path(temp_dir)
    
    # 查找Debian补丁目录
    debian_patches_dir, series_file, has_debian_patches = find_debian_patch_dir(debian_package_name, debian_base_dir)
    
    if not has_debian_patches:
        logging.info(f"Debian包中没有补丁: {debian_package_name}")
        debian_patches = []
    else:
        # 获取Debian补丁名列表
        debian_patches = get_debian_patch_names(series_file, debian_patches_dir)
        logging.info(f"Debian补丁数量: {len(debian_patches)}")
    
    # 读取Fedora spec文件
    fedora_command = f"wsl -d {fedora_dist} bash -c 'cat \"{fedora_spec}\"'"
    logging.debug(f"执行命令: {fedora_command}")
    try:
        fedora_result = subprocess.run(
            fedora_command,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        if fedora_result.returncode != 0:
            logging.warning(f"读取Fedora spec文件失败: {fedora_spec}，尝试从fedora_sources安装SRPM")
            # 尝试从fedora_sources目录安装SRPM
            from relibrary.core.patch.deb_rpm_patch_analyzer_fileName import find_srpm_file
            
            # 使用改进的函数查找SRPM文件
            srpm_path = find_srpm_file(fedora_package_name)
            
            if srpm_path:
                # 提取文件名
                srpm_file = os.path.basename(srpm_path)
                logging.info(f"使用SRPM文件: {srpm_file}")
                
                # 安装SRPM
                srpm_dir = os.path.dirname(srpm_path)
                install_cmd = f"wsl -d {fedora_dist} bash -c 'cd \"{srpm_dir}\" && rpm -ivh {srpm_file}'"
                logging.info(f"执行安装SRPM命令: {install_cmd}")
                install_result = subprocess.run(
                    install_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                if install_result.returncode == 0:
                    logging.info(f"SRPM安装成功，重试读取spec文件")
                    # 重新尝试读取spec文件
                    fedora_result = subprocess.run(
                        fedora_command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace'
                    )
                    
                    if fedora_result.returncode != 0:
                        logging.error(f"安装SRPM后仍无法读取Fedora spec文件: {fedora_spec}")
                        return None
                else:
                    logging.error(f"安装SRPM失败: {install_result.stderr}")
                    return None
            else:
                logging.error(f"在fedora_sources目录中未找到{fedora_package_name}的SRPM文件")
                return None
        
        fedora_spec_content = fedora_result.stdout
        logging.info(f"成功读取Fedora spec文件: {fedora_spec}")
    except Exception as e:
        logging.error(f"读取Fedora spec文件时出错: {e}")
        return None
    
    # 从spec文件中提取补丁名称
    fedora_patches = get_patch_names(fedora_spec_content)
    logging.info(f"Fedora补丁数量: {len(fedora_patches)}")
    
    # 比较补丁
    match_result = compare_fedora_debian_patches(
        fedora_patch_dir,  # fedora_patch_dir - 使用上面确定的目录
        fedora_package_name,  # pkg_name 
        debian_patches_dir,  # debian_patch_dir
        series_file,  # debian_series_file
        threshold=similarity_threshold  # threshold
    )
    
    # 解析返回的元组值
    matched_patches_dict, unmatched_fedora, unmatched_debian, same_function_patches = match_result
    # 将完全匹配的补丁字典转换为列表格式，只记录补丁名
    common_patches = [
        {"Fedora": f_patch, "Debian": info["debian_patch"]}
        for f_patch, info in matched_patches_dict.items()
    ]
    
    # 构建结果字典
    result = {
        "common_patches": common_patches,
        "unique_fedora_patches": unmatched_fedora,
        "unique_debian_patches": unmatched_debian,
        "same_function_different_content": same_function_patches,
        "missing_patches": {"fedora": [], "debian": []}
    }
    
    # 处理特殊情况
    if not fedora_patches and not debian_patches:
        result["no_patches"] = True
        logging.info(f"软件包在两个发行版中都没有补丁: Fedora({fedora_package_name}), Debian({debian_package_name})")
        summary_info = "\n补丁比较汇总:\n两个发行版都没有补丁"
        print(summary_info)
        logging.info(summary_info)
        return result
    
    # 处理获取内容失败的情况 - 这种情况在当前实现中可能不会发生，但保留逻辑以防万一
    missing_fedora = len(result["missing_patches"]["fedora"])
    missing_debian = len(result["missing_patches"]["debian"])
    all_missing = (missing_fedora == len(fedora_patches) and fedora_patches) or \
                 (missing_debian == len(debian_patches) and debian_patches)
    
    if all_missing:
        result["all_patches_missing"] = True
        logging.warning(f"软件包的所有补丁都无法获取内容: Fedora({fedora_package_name}), Debian({debian_package_name})")
        summary_info = "\n补丁比较汇总:\n"
        summary_info += f"无法获取的补丁数量 - Fedora: {missing_fedora}, Debian: {missing_debian}"
        print(summary_info)
        logging.warning(summary_info)
        return result
    
    # 打印汇总信息
    summary_info = "\n补丁比较汇总:"
    summary_info += f"\n共同补丁数量: {len(result['common_patches'])}"
    summary_info += f"\n功能相同但内容不同的补丁数量: {len(result['same_function_different_content'])}"
    summary_info += f"\nFedora独有补丁数量: {len(result['unique_fedora_patches'])}"
    summary_info += f"\nDebian独有补丁数量: {len(result['unique_debian_patches'])}"
    
    if 'missing_patches' in result:
        fedora_missing = len(result['missing_patches']['fedora'])
        debian_missing = len(result['missing_patches']['debian'])
        if fedora_missing > 0 or debian_missing > 0:
            summary_info += f"\n缺失的补丁数量 - Fedora: {fedora_missing}, Debian: {debian_missing}"
    
    # 打印到控制台并记录到日志
    print(summary_info)
    logging.info(summary_info)
    
    return result

def test_from_common_packages(json_file=DEFAULT_COMMON_PACKAGES_FILE, output_prefix="report_", similarity_threshold=0.7, max_packages=None, custom_packages=None):
    """
    从共同软件包JSON文件批量比较补丁
    
    Args:
        json_file: 共同软件包JSON文件路径
        output_prefix: 输出文件前缀
        similarity_threshold: 相似度阈值
        max_packages: 最大处理包数量，用于调试
        custom_packages: 自定义的包字典，用于单个软件包测试
    """
    # 加载共同软件包数据
    if custom_packages:
        # 使用自定义的包字典
        common_packages = custom_packages
        logging.info(f"使用自定义的包字典，包含 {len(common_packages)} 个软件包")
    else:
        # 从文件加载
        common_packages = load_common_packages(json_file)
        if not common_packages:
            logging.error("共同软件包数据为空或无法读取")
            return
        logging.info(f"从 {json_file} 中加载了 {len(common_packages)} 个共同软件包")
    
    # 限制处理的包数量（如果指定）
    if max_packages and max_packages > 0:
        package_keys = list(common_packages.keys())[:max_packages]
        logging.info(f"限制处理前 {max_packages} 个软件包（共 {len(common_packages)} 个）")
    else:
        package_keys = common_packages.keys()
    
    # 统计数据
    stats = {
        "total_packages": len(package_keys),
        "processed_packages": 0,
        "failed_packages": 0,
        "packages_with_patches": 0,
        "packages_without_patches": 0,
        "packages_with_missing_patches": [],
        "total_patch_stats": {
            "common_patches": 0,
            "same_function_different_content": 0,
            "unique_to_fedora": 0,
            "unique_to_debian": 0
        }
    }
    
    # 保存所有软件包的比较结果
    packages_comparison = {}
    # 记录错误的包
    error_packages = []
    
    for i, package_key in enumerate(package_keys):
        package_info = common_packages[package_key]
        
        # 获取Fedora和Debian包名
        fedora_info = package_info.get("Fedora", {})
        debian_info = package_info.get("Debian", {})
        
        fedora_package_name = fedora_info.get("package_name", package_key)
        debian_package_name = debian_info.get("package_name", package_key)
        
        progress_msg = f"处理包 [{i+1}/{len(package_keys)}]: {package_key} (Fedora: {fedora_package_name}, Debian: {debian_package_name})"
        print(progress_msg)
        logging.info(progress_msg)
        
        try:
            # 构建Fedora spec文件路径
            fedora_spec = normalize_path(os.path.join(DEFAULT_FEDORA_SPEC_DIR, f"{fedora_package_name}.spec"))
            
            # 执行比较
            result = test_distro_comparison(
                package_key,
                fedora_name=fedora_package_name,
                debian_name=debian_package_name,
                fedora_spec=fedora_spec,
                similarity_threshold=similarity_threshold
            )
            
            if not result:
                error_msg = f"分析包 {package_key} 失败"
                logging.error(error_msg)
                print(error_msg)
                stats["failed_packages"] += 1
                error_packages.append({"package": package_key, "reason": "比较失败，结果为空"})
                continue
            
            # 处理结果
            if "no_patches" in result and result["no_patches"]:
                stats["packages_without_patches"] += 1
                info_msg = f"包 {package_key} 在两个发行版中都没有补丁"
                logging.info(info_msg)
                print(info_msg)
            else:
                stats["packages_with_patches"] += 1
                
                # 添加到统计信息
                stats["total_patch_stats"]["common_patches"] += len(result.get("common_patches", []))
                stats["total_patch_stats"]["same_function_different_content"] += len(result.get("same_function_different_content", []))
                stats["total_patch_stats"]["unique_to_fedora"] += len(result.get("unique_fedora_patches", []))
                stats["total_patch_stats"]["unique_to_debian"] += len(result.get("unique_debian_patches", []))
                
                # 检查是否有缺失的补丁
                if result.get("missing_patches"):
                    fedora_missing = len(result["missing_patches"].get("fedora", []))
                    debian_missing = len(result["missing_patches"].get("debian", []))
                    if fedora_missing > 0 or debian_missing > 0:
                        stats["packages_with_missing_patches"].append(package_key)
            
            # 保存比较结果
            packages_comparison[package_key] = result
            
            # 处理成功
            stats["processed_packages"] += 1
            status_msg = f"成功处理包 {package_key}"
            logging.info(status_msg)
            print(status_msg)
            
        except Exception as e:
            error_msg = f"处理包 {package_key} 时出错: {str(e)}"
            logging.error(error_msg)
            logging.error(traceback.format_exc())
            print(error_msg)
            stats["failed_packages"] += 1
            error_packages.append({"package": package_key, "reason": str(e)})
    
    # 生成摘要报告
    summary = "\n" + "="*80 + "\n"
    summary += "补丁分析摘要报告\n"
    summary += "="*80 + "\n\n"
    
    summary += f"总共分析了 {stats['total_packages']} 个包\n"
    summary += f"成功处理: {stats['processed_packages']} 个包\n"
    summary += f"处理失败: {stats['failed_packages']} 个包\n"
    summary += f"有补丁的包: {stats['packages_with_patches']} 个包\n"
    summary += f"无补丁的包: {stats['packages_without_patches']} 个包\n"
    summary += f"有缺失补丁的包: {len(stats['packages_with_missing_patches'])} 个包\n\n"
    
    summary += "补丁统计:\n"
    summary += f"完全相同的补丁: {stats['total_patch_stats']['common_patches']} 个\n"
    summary += f"功能相同但内容不同的补丁: {stats['total_patch_stats']['same_function_different_content']} 个\n"
    summary += f"Fedora特有的补丁: {stats['total_patch_stats']['unique_to_fedora']} 个\n"
    summary += f"Debian特有的补丁: {stats['total_patch_stats']['unique_to_debian']} 个\n"
    
    # 同步输出到控制台和日志
    print(summary)
    logging.info(summary)
    
    # 清理比较结果，移除冗余字段
    def clean_comparison_results(packages_comp):
        """清理比较结果中的冗余字段"""
        cleaned_results = {}
        for pkg_name, result in packages_comp.items():
            cleaned_result = {}
            
            # 复制基本字段
            for key in result:
                if key == 'missing_patches':
                    # 检查missing_patches是否都为空
                    if (not result['missing_patches'].get('fedora', []) and 
                        not result['missing_patches'].get('debian', [])):
                        # 如果都为空，则跳过此字段
                        continue
                    else:
                        # 复制missing_patches
                        cleaned_result['missing_patches'] = result['missing_patches']
                elif key in ['common_patches', 'unique_fedora_patches', 'unique_debian_patches', 
                           'same_function_different_content']:
                    # 处理补丁列表
                    cleaned_patches = []
                    for patch in result[key]:
                        # 检查common_patches的格式：是否为字典且包含debian_patch字段
                        if key == 'common_patches' and isinstance(patch, dict) and 'debian_patch' in patch:
                            # 格式化为包含fedora和debian补丁名的字典
                            fedora_patch = next(iter(patch.keys()))  # 字典的键是fedora补丁名
                            debian_patch = patch.get('debian_patch')
                            patch_info = {
                                "fedora_patch": fedora_patch,
                                "debian_patch": debian_patch
                            }
                            # 如果有相似度信息，也保留
                            if 'similarity' in patch:
                                patch_info['similarity'] = patch['similarity']
                            cleaned_patches.append(patch_info)
                        # 普通字符串格式的补丁名
                        elif isinstance(patch, str):
                            cleaned_patches.append(patch)
                        # 其他字典格式的补丁
                        else:
                            cleaned_patch = {k: v for k, v in patch.items() 
                                           if k not in ['path', 'strip_level']}
                            cleaned_patches.append(cleaned_patch)
                    cleaned_result[key] = cleaned_patches
                else:
                    # 直接复制其他字段
                    cleaned_result[key] = result[key]
            
            cleaned_results[pkg_name] = cleaned_result
        
        return cleaned_results
    
    # 清理比较结果
    cleaned_packages_comparison = clean_comparison_results(packages_comparison)
    
    # 输出总的结果文件
    final_result = {
        "packages_comparison": cleaned_packages_comparison,
        "error_packages": error_packages,
        "stats": stats
    }
    
    output_dir = DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{output_prefix}deb_rpm_patch_comparison_report.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_result, f, indent=2, ensure_ascii=False)
    
    # 记录到日志
    output_msg = f"\n已将分析结果保存到: {output_file}"
    print(output_msg)
    logging.info(output_msg)
    
    return stats

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="比较Fedora和Debian的软件包补丁")
    
    # 添加命令行参数
    parser.add_argument('--common_packages', type=str, default=DEFAULT_COMMON_PACKAGES_FILE,
                      help='共同软件包JSON文件路径')
    parser.add_argument('--output_dir', type=str, default=DEFAULT_OUTPUT_DIR,
                      help='输出目录')
    parser.add_argument('--test_single', type=str, default=None,
                      help='测试单个软件包')
    parser.add_argument('--fedora_spec', type=str, default=None,
                      help='Fedora spec文件路径（单个软件包测试时使用）')
    parser.add_argument('--log_level', type=str, default="DEBUG",
                      choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                      help='日志级别，默认为DEBUG以便调试')
    parser.add_argument('--similarity_threshold', type=float, default=0.7,
                      help='补丁相似度阈值，默认0.7')
    parser.add_argument('--max_packages', type=int, default=None,
                      help='最大处理包数量，用于调试')
    parser.add_argument('--verbose', action='store_true', 
                      help='启用详细日志输出，显示WSL执行的所有命令')
    
    # 解析参数
    args = parser.parse_args()
    
    # 设置日志
    log_dir = os.path.dirname(DEFAULT_LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    
    # 配置日志
    log_level = getattr(logging, args.log_level)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        handlers=[
            logging.FileHandler(DEFAULT_LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()  # 同时输出到控制台
        ]
    )
    
    # 记录分析开始
    logging.info(f"===== 补丁分析开始于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====")
    logging.info(f"日志级别: {args.log_level}")
    if args.verbose:
        logging.info("启用详细日志模式")
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    if args.test_single:
        # 单个软件包测试
        logging.info(f"测试单个软件包: {args.test_single}")
        
        # 加载软件包数据查找特定发行版包名
        common_packages = load_common_packages(args.common_packages)
        package_info = common_packages.get(args.test_single, {})
        
        fedora_name = package_info.get("Fedora", {}).get("package_name", args.test_single)
        debian_name = package_info.get("Debian", {}).get("package_name", args.test_single)
        
        # 构建Fedora spec文件路径
        fedora_spec = args.fedora_spec
        if not fedora_spec:
            fedora_spec = normalize_path(os.path.join(DEFAULT_FEDORA_SPEC_DIR, f"{fedora_name}.spec"))
        else:
            fedora_spec = normalize_path(fedora_spec)
        
        # 创建一个只有这个包的字典，使用test_from_common_packages处理
        single_package_dict = {args.test_single: package_info}
        
        # 使用与批处理相同的代码处理单个包
        logging.info(f"将单个包作为批处理任务处理: {args.test_single}")
        test_from_common_packages(
            json_file=None,  # 不从文件加载
            output_prefix="single_",
            similarity_threshold=args.similarity_threshold,
            max_packages=1,
            custom_packages=single_package_dict  # 传递自定义的包字典
        )
    else:
        # 批量分析
        logging.info(f"开始批量分析共同软件包，数据文件: {args.common_packages}")
        test_from_common_packages(
            json_file=args.common_packages,
            output_prefix="batch_",
            similarity_threshold=args.similarity_threshold,
            max_packages=args.max_packages
        )

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 确保异常也被记录到日志
        if not logging.getLogger().handlers:
            setup_logging(DEFAULT_LOG_FILE)
        logging.error(f"执行失败: {e}", exc_info=True)
        sys.exit(1)