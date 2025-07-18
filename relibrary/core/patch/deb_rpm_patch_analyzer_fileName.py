"""
补丁分析核心模块，提供Fedora和Debian补丁的解析和对比功能
"""

import re
import os
import subprocess
import logging
import platform
import requests
import json
import time
import shutil
import hashlib
import difflib
import tempfile
import math
import traceback
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set, Optional, Union
from relibrary.core.patch.rpm_patch_analyzer_fileName import generate_ngrams
from relibrary.core.patch.rpm_patch_analyzer_fileName import tokenize_code

# 导入RPM补丁分析函数
from relibrary.core.patch.rpm_patch_analyzer_fileName import (
    parse_defines, replace_macros_with_values, get_patch_info, get_patch_file_content,
    strip_patch_path, normalize_file_path, extract_patch_features,
    normalize_patch_content, calculate_patch_similarity,
    is_only_header_difference, compare_patches, get_patch_names
)

def find_debian_patch_dir(package_name, debian_base_dir=None):
    """
    查找Debian包的补丁目录和series文件
    
    Args:
        package_name: 包名称
        debian_base_dir: Debian包基础目录，默认为/home/penny/packages_info
        
    Returns:
        tuple: (补丁目录路径, series文件路径, 是否找到补丁目录)
    """
    logging.info(f"查找{package_name}的Debian补丁目录")
    
    if debian_base_dir is None:
        debian_base_dir = "/home/penny/packages_info"
    
    # 清理路径，确保没有转义问题    
    package_name = package_name.replace("\\", "/")
    debian_base_dir = debian_base_dir.replace("\\", "/")
    
    package_dir = f"{debian_base_dir}/{package_name}"
    logging.info(f"搜索目录: {package_dir}")
    
    # 改进的查找命令 - 更简单的路径处理和更好的错误控制
    find_cmd = f"wsl -d Debian -u penny sh -c \"find '{package_dir}' -type d -path '*/debian/patches' 2>/dev/null || echo 'NOT_FOUND'\""
    
    logging.info(f"执行命令: {find_cmd}")
    result = subprocess.run(
        find_cmd, 
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    # 检查命令是否成功
    if result.returncode != 0:
        logging.error(f"查找命令执行失败: {result.stderr}")
        return None, None, False
    
    output = result.stdout.strip()
    logging.info(f"查找命令原始输出: '{output}'")
        
    # 处理输出
    potential_dirs = [line for line in output.split('\n') if line.strip() and line != 'NOT_FOUND']
    logging.info(f"处理后的潜在目录列表: {potential_dirs}")
    
    if not potential_dirs:
        # 尝试不同的方式查找
        # 1. 先列出包目录下所有子目录
        list_dirs_cmd = f"wsl -d Debian -u penny sh -c \"find '{package_dir}' -type d -name debian 2>/dev/null || echo 'NOT_FOUND'\""
        dirs_result = subprocess.run(
            list_dirs_cmd, 
            shell=True, 
            capture_output=True, 
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        debian_dirs = [line for line in dirs_result.stdout.strip().split('\n') 
                      if line.strip() and line != 'NOT_FOUND']
        
        logging.info(f"找到的debian目录: {debian_dirs}")
        
        # 2. 检查每个debian目录下是否有patches目录
        for debian_dir in debian_dirs:
            check_patches_cmd = f"wsl -d Debian -u penny sh -c \"[ -d '{debian_dir}/patches' ] && echo '{debian_dir}/patches' || echo 'NOT_FOUND'\""
            check_result = subprocess.run(
                check_patches_cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if 'NOT_FOUND' not in check_result.stdout:
                patches_dir = check_result.stdout.strip()
                logging.info(f"找到patches目录: {patches_dir}")
                potential_dirs.append(patches_dir)
        
        # 3. 如果上述方法都失败，尝试查找最新版本目录
        if not potential_dirs:
            version_cmd = f"wsl -d Debian -u penny sh -c \"ls -d {package_dir}/*/ 2>/dev/null | sort -V | tail -1 || echo 'NOT_FOUND'\""
            version_result = subprocess.run(
                version_cmd, 
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            latest_dir = version_result.stdout.strip()
            logging.info(f"最新版本目录: {latest_dir}")
            
            if latest_dir and latest_dir != 'NOT_FOUND':
                check_debian_cmd = f"wsl -d Debian -u penny sh -c \"[ -d '{latest_dir}/debian/patches' ] && echo '{latest_dir}/debian/patches' || echo 'NOT_FOUND'\""
                check_debian_result = subprocess.run(
                    check_debian_cmd, 
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                if 'NOT_FOUND' not in check_debian_result.stdout:
                    patches_dir = check_debian_result.stdout.strip()
                    logging.info(f"在最新版本中找到patches目录: {patches_dir}")
                    potential_dirs.append(patches_dir)
    
    if not potential_dirs:
        logging.warning(f"未找到{package_name}的Debian补丁目录")
        return None, None, False
    
    # 使用找到的第一个目录
    patches_dir = potential_dirs[0]
    logging.info(f"使用Debian补丁目录: {patches_dir}")
    
    # 验证目录是否真的存在
    verify_cmd = f"wsl -d Debian -u penny sh -c \"[ -d '{patches_dir}' ] && echo 'EXISTS' || echo 'NOT_EXISTS'\""
    verify_result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    
    if 'EXISTS' not in verify_result.stdout:
        logging.error(f"验证失败，目录不存在: {patches_dir}")
        return None, None, False
    
    # 检查是否有series文件
    series_path = f"{patches_dir}/series"
    check_series_cmd = f"wsl -d Debian -u penny sh -c \"if [ -f '{series_path}' ]; then echo 'SERIES_EXISTS'; else echo 'NO_SERIES'; fi\""
    series_result = subprocess.run(
        check_series_cmd, 
        shell=True, 
        capture_output=True, 
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    has_series = 'SERIES_EXISTS' in series_result.stdout
    if has_series:
        logging.info(f"找到series文件: {series_path}")
        return patches_dir, series_path, True
    else:
        logging.info(f"未找到series文件，将直接搜索补丁文件")
        return patches_dir, None, True


def get_debian_patch_names(series_path, patches_dir):
    """
    获取Debian补丁文件名列表
    
    参数:
        series_path: series文件路径，如果没有则为None
        patches_dir: 补丁目录路径
    
    返回:
        补丁文件名列表
    """
    logging.info(f"从系列文件获取Debian补丁文件名: {series_path}")
    
    # 确保路径使用Linux风格的分隔符
    patches_dir = patches_dir.replace("\\", "/") if patches_dir else None
    series_path = series_path.replace("\\", "/") if series_path else None
    
    patch_names = []
    
    # 首先尝试从series文件中获取补丁名称
    if series_path:
        logging.info(f"从series文件获取补丁名称: {series_path}")
        
        # 读取series文件内容
        cat_cmd = f"wsl -d Debian -u penny sh -c \"cat '{series_path}' 2>/dev/null || echo 'ERROR'\""
        cat_result = subprocess.run(
            cat_cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        
        output = cat_result.stdout.strip()
        logging.info(f"Series文件原始输出: '{output}'")
        
        if output and output != 'ERROR':
            # 解析series文件内容
            lines = output.splitlines()
            for line in lines:
                line = line.strip()
                # 忽略注释行和空行
                if line and not line.startswith("#"):
                    patch_names.append(line)
            
            logging.info(f"从series文件找到{len(patch_names)}个补丁名称: {patch_names}")
            
            # 验证这些补丁文件确实存在
            valid_patches = []
            for patch_name in patch_names:
                patch_path = f"{patches_dir}/{patch_name}"
                check_cmd = f"wsl -d Debian -u penny sh -c \"test -f '{patch_path}' && echo 'EXISTS' || echo 'NOT_EXISTS'\""
                check_result = subprocess.run(
                    check_cmd,
                    shell=True,
                    capture_output=True,
                    text=True
                )
                
                if 'EXISTS' in check_result.stdout:
                    valid_patches.append(patch_name)
                else:
                    logging.warning(f"补丁文件不存在: {patch_path}")
            
            patch_names = valid_patches
            logging.info(f"验证后有效的补丁文件: {len(patch_names)}")
            
            if patch_names:
                return patch_names
    
    # 如果没有series文件或从series文件获取失败，则直接扫描目录
    logging.info(f"直接扫描目录获取补丁文件: {patches_dir}")
    
    if patches_dir:
        # 查找所有.patch和.diff文件
        find_cmd = f"wsl -d Debian -u penny sh -c \"find '{patches_dir}' -type f \\( -name '*.patch' -o -name '*.diff' \\) 2>/dev/null || echo 'NOT_FOUND'\""
        find_result = subprocess.run(
            find_cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        
        output = find_result.stdout.strip()
        logging.info(f"补丁搜索原始输出: '{output}'")
        
        if output and 'NOT_FOUND' not in output:
            # 处理找到的文件路径
            patch_files = [line.strip() for line in output.splitlines() if line.strip()]
            
            # 将完整路径转换为相对于patches_dir的名称
            for patch_file in patch_files:
                # 提取文件名部分（不包含目录路径）
                if patch_file.startswith(patches_dir):
                    relative_path = patch_file[len(patches_dir):].lstrip('/')
                    patch_names.append(relative_path)
                else:
                    # 如果不能正确解析路径，则使用文件名
                    file_name = os.path.basename(patch_file)
                    patch_names.append(file_name)
            
            logging.info(f"从目录扫描找到{len(patch_names)}个补丁文件: {patch_names}")
    
    # 如果仍未找到补丁文件，则尝试更广泛的搜索
    if not patch_names and patches_dir:
        logging.info("尝试更广泛的搜索，查找任何可能的补丁文件")
        
        # 扩展搜索范围，包括子目录
        wide_find_cmd = f"wsl -d Debian -u penny sh -c \"find '{patches_dir}' -type f -name '*patch*' 2>/dev/null || echo 'NOT_FOUND'\""
        wide_find_result = subprocess.run(
            wide_find_cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        
        output = wide_find_result.stdout.strip()
        logging.info(f"扩展搜索原始输出: '{output}'")
        
        if output and 'NOT_FOUND' not in output:
            patch_files = [line.strip() for line in output.splitlines() if line.strip()]
            
            # 将完整路径转换为相对于patches_dir的名称
            for patch_file in patch_files:
                if patch_file.startswith(patches_dir):
                    relative_path = patch_file[len(patches_dir):].lstrip('/')
                    patch_names.append(relative_path)
                else:
                    file_name = os.path.basename(patch_file)
                    patch_names.append(file_name)
            
            logging.info(f"从扩展搜索找到{len(patch_names)}个补丁文件: {patch_names}")
    
    return patch_names


def get_debian_patch_file_content(patch_name, patches_dir):
    """
    获取Debian补丁文件内容
    
    Args:
        patch_name: 补丁文件名
        patches_dir: 补丁目录路径
        
    Returns:
        list: 补丁文件内容的行列表，失败则返回None
    """
    if not patches_dir or not patch_name:
        return None
    
    # 确保路径使用Linux风格的分隔符
    patches_dir = patches_dir.replace("\\", "/")
    patch_name = patch_name.replace("\\", "/")
    patch_path = f"{patches_dir}/{patch_name}"

    # 检查文件是否存在并读取内容
    command_check = f"wsl -d Debian bash -c 'test -f \"{patch_path}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\"'"
    command_cat = f"wsl -d Debian bash -c 'cat \"{patch_path}\"'"
    
    try:
        result_check = subprocess.run(
            command_check,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        if result_check.returncode == 0 and "EXISTS" in result_check.stdout:
            # 文件存在，读取内容
            result_cat = subprocess.run(
                command_cat,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if result_cat.returncode == 0:
                # 直接使用splitlines()分割为行数组
                patch_content = result_cat.stdout.splitlines()
                logging.info(f"成功读取Debian补丁文件: {patch_path}，长度: {len(patch_content)}行")
                return patch_content
            else:
                logging.warning(f"读取Debian补丁文件失败: {patch_path}, 错误: {result_cat.stderr}")
                return None
        else:
            logging.warning(f"Debian补丁文件不存在: {patch_path}")
            return None
    except Exception as e:
        logging.error(f"处理Debian补丁文件时出错: {patch_path}, 错误: {e}")
        return None


def compare_fedora_debian_patches(fedora_patch_dir, pkg_name, debian_patch_dir, debian_series_file, threshold=0.7):
    """
    比较Fedora和Debian的补丁文件，找出相似的补丁

    Args:
        fedora_patch_dir: Fedora补丁目录路径
        pkg_name: 包名
        debian_patch_dir: Debian补丁目录路径
        debian_series_file: Debian系列文件路径
        threshold: 相似度阈值

    Returns:
        tuple: (完全匹配的补丁字典, Fedora特有补丁列表, Debian特有补丁列表, 功能相同但内容不同的补丁列表)
    """
    # 检查路径是否存在，如果不存在则返回空结果
    def check_wsl_path_exists(path, distro="Debian"):
        """使用WSL命令检查路径是否存在"""
        if not path:
            return False
        # 确保使用Linux风格的路径分隔符
        path = path.replace("\\", "/")
        # 使用test命令检查路径是否存在，依赖返回码
        cmd = f"wsl -d {distro} bash -c 'test -e \"{path}\"'"
        try:
            result = subprocess.run(cmd, shell=True)
            exists = (result.returncode == 0)
            logging.debug(f"检查路径是否存在: {path}, 命令: {cmd}, 返回码: {result.returncode}")
            if exists:
                logging.debug(f"路径存在: {path}")
            else:
                logging.debug(f"路径不存在: {path}")
            return exists
        except Exception as e:
            logging.error(f"检查路径是否存在时出错: {e}")
            return False

    # 检查Fedora补丁目录
    if not check_wsl_path_exists(fedora_patch_dir, "Fedora"):
        logging.error(f"Fedora补丁目录不存在: {fedora_patch_dir}")
        return {}, [], [], []

    # 检查Debian补丁目录
    if debian_patch_dir and not check_wsl_path_exists(debian_patch_dir, "Debian"):
        logging.error(f"Debian补丁目录不存在: {debian_patch_dir}")
        return {}, [], [], []

    # 获取Fedora补丁文件
    fedora_patches = []
    list_fedora_cmd = f"wsl -d Fedora bash -c 'find \"{fedora_patch_dir}\" -name \"*.patch\" -o -name \"*.diff\" -type f 2>/dev/null || echo \"NOT_FOUND\"'"
    
    try:
        fedora_result = subprocess.run(
            list_fedora_cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        if fedora_result.returncode == 0 and 'NOT_FOUND' not in fedora_result.stdout:
            for line in fedora_result.stdout.splitlines():
                if line.strip():
                    # 提取文件名
                    patch_file = os.path.basename(line.strip())
                    fedora_patches.append(patch_file)
        else:
            logging.warning(f"通过find命令在Fedora目录中未找到补丁文件: {fedora_patch_dir}")
            
            # 尝试另一种方法：使用ls检查每个已知的补丁文件
            # 假设我们已经从spec文件中提取了补丁名称，尝试直接检查这些文件
            if pkg_name:
                logging.info(f"尝试使用ls命令检查spec文件中定义的补丁文件是否存在")
                # 获取fedora补丁列表
                fedora_spec_dir = "/home/penny/rpmbuild/SPECS"
                spec_file = f"{fedora_spec_dir}/{pkg_name}.spec"
                spec_check_cmd = f"wsl -d Fedora bash -c 'if [ -f \"{spec_file}\" ]; then cat \"{spec_file}\"; else echo \"SPEC_NOT_FOUND\"; fi'"
                
                spec_result = subprocess.run(
                    spec_check_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                if spec_result.returncode == 0 and 'SPEC_NOT_FOUND' not in spec_result.stdout:
                    from relibrary.core.patch.rpm_patch_analyzer_fileName import get_patch_names
                    potential_patches = get_patch_names(spec_result.stdout)
                    logging.info(f"从spec文件中找到{len(potential_patches)}个潜在补丁")
                    
                    for patch_name in potential_patches:
                        check_cmd = f"wsl -d Fedora bash -c 'if [ -f \"{fedora_patch_dir}/{patch_name}\" ]; then echo \"PATCH_EXISTS\"; else echo \"PATCH_NOT_FOUND\"; fi'"
                        check_result = subprocess.run(
                            check_cmd,
                            shell=True,
                            capture_output=True,
                            text=True,
                            encoding='utf-8',
                            errors='replace'
                        )
                        
                        if 'PATCH_EXISTS' in check_result.stdout:
                            logging.info(f"找到补丁文件: {patch_name}")
                            fedora_patches.append(patch_name)
                        else:
                            logging.warning(f"未找到补丁文件: {patch_name}")
    except Exception as e:
        logging.error(f"获取Fedora补丁文件列表时出错: {e}")
    
    # 获取Debian补丁文件
    debian_patches = get_debian_patch_names(debian_series_file, debian_patch_dir)
    
    # 如果Debian没有补丁，直接将所有Fedora补丁标记为Fedora独有
    if not debian_patches:
        logging.warning(f"未找到Debian补丁文件: {debian_patch_dir}")
        return {}, fedora_patches, [], []

    logging.info(f"Fedora补丁数量: {len(fedora_patches)}")
    logging.info(f"Debian补丁数量: {len(debian_patches)}")
    
    # 比较补丁文件
    matched_patches = {}
    same_function_patches = []
    processed_patches = set()  # 用于记录已处理的补丁对
    
    # 定义多级阈值
    thresholds = [0.7, 0.6, 0.5]
    
    for f_patch in fedora_patches:
        f_path = os.path.join(fedora_patch_dir, f_patch)
        f_path = f_path.replace("\\", "/")
        logging.info(f"尝试读取Fedora补丁文件: {f_path}")
        
        # 获取Fedora补丁内容
        f_content = get_patch_file_content("Fedora", f_patch, fedora_patch_dir)
        
        if not f_content:
            logging.warning(f"无法读取Fedora补丁文件内容: {f_path}")
            continue
        
        logging.info(f"成功读取Fedora补丁 {f_patch}，内容长度: {len(f_content)}行")
        
        # 检查补丁内容是否过大
        if len(f_content) > 10000:
            logging.warning(f"Fedora补丁内容过大，跳过比较: {f_patch} ({len(f_content)}行)")
            continue
            
        for d_patch in debian_patches:
            # 跳过已处理的补丁对
            patch_pair = (f_patch, d_patch)
            if patch_pair in processed_patches:
                continue
                
            d_path = f"{debian_patch_dir}/{d_patch}"
            logging.info(f"尝试读取Debian补丁文件: {d_path}")
            
            # 获取Debian补丁内容
            d_content = get_debian_patch_file_content(d_patch, debian_patch_dir)
            
            if not d_content:
                logging.warning(f"无法读取Debian补丁文件内容: {d_path}")
                continue
                
            logging.info(f"成功读取Debian补丁 {d_patch}，内容长度: {len(d_content)}行")
            
            # 检查补丁内容是否过大
            if len(d_content) > 10000:
                logging.warning(f"Debian补丁内容过大，跳过比较: {d_patch} ({len(d_content)}行)")
                continue
                
            try:
                # 检查补丁内容是否有效
                if len(f_content) < 3 or len(d_content) < 3:
                    logging.warning(f"补丁内容过少，跳过比较: Fedora({len(f_content)}行) vs Debian({len(d_content)}行)")
                    continue
                
                # 计算相似度
                similarity = calculate_patch_similarity_improved(f_content, d_content)
                logging.info(f"补丁相似度: {f_patch} vs {d_patch} = {similarity:.2f}, 阈值: {threshold}")
                
                # 标记该补丁对已处理
                processed_patches.add(patch_pair)
                
                # 使用多级阈值进行匹配
                if similarity == 1.0:
                    # 完全相同的补丁
                    if f_patch not in matched_patches:
                        matched_patches[f_patch] = {
                            "debian_patch": d_patch,
                            "similarity": similarity
                        }
                        logging.info(f"找到完全匹配: Fedora补丁 {f_patch} 匹配 Debian补丁 {d_patch}")
                else:
                    # 尝试不同阈值
                    for current_threshold in thresholds:
                        if similarity >= current_threshold:
                            # 功能相同但内容不同的补丁
                            same_function_patches.append({
                                "Fedora": f_patch,
                                "Debian": d_patch,
                                "Similarity": f"{similarity:.2f}"
                            })
                            logging.info(f"找到功能相同但内容不同的补丁: Fedora补丁 {f_patch} 匹配 Debian补丁 {d_patch}，相似度: {similarity:.2f}，阈值: {current_threshold}")
                            break
            except Exception as e:
                logging.error(f"计算补丁相似度时出错: {f_patch} vs {d_patch}, 错误: {e}")
                logging.error(traceback.format_exc())
    
    # 处理same_function_patches，只保留每个Fedora补丁相似度最高的一个匹配
    func_best = {}
    for patch in same_function_patches:
        f = patch.get("Fedora")
        sim = float(patch.get("Similarity", 0))
        if f not in func_best or sim > float(func_best[f].get("Similarity", 0)):
            func_best[f] = patch
    same_function_patches = list(func_best.values())

    # 找出未匹配的补丁
    matched_fedora = list(matched_patches.keys())
    matched_debian = [info.get("debian_patch") for info in matched_patches.values()]
    same_function_fedora = [p.get("Fedora") for p in same_function_patches]
    same_function_debian = [p.get("Debian") for p in same_function_patches]
    
    unmatched_fedora = [p for p in fedora_patches if p not in matched_fedora and p not in same_function_fedora]
    unmatched_debian = [p for p in debian_patches if p not in matched_debian and p not in same_function_debian]
    
    logging.info(f"完全匹配的补丁数量: {len(matched_patches)}")
    logging.info(f"功能相同但内容不同的补丁数量: {len(same_function_patches)}")
    logging.info(f"未匹配的Fedora补丁数量: {len(unmatched_fedora)}")
    logging.info(f"未匹配的Debian补丁数量: {len(unmatched_debian)}")
    
    return matched_patches, unmatched_fedora, unmatched_debian, same_function_patches

def analyze_fedora_debian_patches(package_name, fedora_dist, debian_path, fedora_source_dir, fedora_spec_dir):
    """
    分析并比较Fedora和Debian的补丁文件
    
    Args:
        package_name: 包名称
        fedora_dist: Fedora发行版
        debian_path: Debian包路径
        fedora_source_dir: Fedora源码目录
        fedora_spec_dir: Fedora spec文件目录
    
    Returns:
        dict: 分析结果
    """
    # 确保路径使用Linux风格的分隔符
    package_name = package_name.replace("\\", "/")
    fedora_source_dir = fedora_source_dir.replace("\\", "/")
    fedora_spec_dir = fedora_spec_dir.replace("\\", "/")
    if debian_path:
        debian_path = debian_path.replace("\\", "/")
    
    logging.info(f"开始分析{package_name}的Fedora和Debian补丁")
    
    # 查找Debian补丁目录
    patches_dir, series_path, found = find_debian_patch_dir(package_name)
    if not found:
        logging.warning(f"未找到Debian补丁目录: {package_name}")
        debian_patches = []
    else:
        # 获取Debian补丁文件名列表
        debian_patches = get_debian_patch_names(series_path, patches_dir)
        logging.info(f"Debian补丁数量: {len(debian_patches)}")
    
    # 获取Fedora补丁文件名列表
    fedora_patches = get_fedora_patch_names(package_name, fedora_spec_dir)
    logging.info(f"Fedora补丁数量: {len(fedora_patches)}")
    
    # 分析结果
    result = {
        "package_name": package_name,
        "fedora_dist": fedora_dist,
        "debian_patches_dir": patches_dir,
        "debian_patches": [],
        "fedora_patches": [],
        "common_patches": [],
        "unique_debian_patches": [],
        "unique_fedora_patches": []
    }
    
    # 处理补丁内容
    if debian_patches:
        for patch_name in debian_patches:
            patch_path = f"{patches_dir}/{patch_name}"
            patch_content = get_patch_content(patch_path, is_debian=True)
            if patch_content:
                result["debian_patches"].append({
                    "name": patch_name,
                    "content": patch_content,
                    "path": patch_path
                })
    
    for patch_name in fedora_patches:
        patch_path = f"{fedora_source_dir}/{patch_name}"
        patch_content = get_patch_content(patch_path, is_debian=False)
        if patch_content:
            result["fedora_patches"].append({
                "name": patch_name,
                "content": patch_content,
                "path": patch_path
            })
    
    # 分析共同和唯一的补丁
    debian_patch_contents = [p["content"] for p in result["debian_patches"]]
    fedora_patch_contents = [p["content"] for p in result["fedora_patches"]]
    
    for i, deb_patch in enumerate(result["debian_patches"]):
        found_match = False
        for j, fed_patch in enumerate(result["fedora_patches"]):
            if deb_patch["content"] == fed_patch["content"]:
                result["common_patches"].append({
                    "debian_patch": deb_patch["name"],
                    "fedora_patch": fed_patch["name"],
                    "content": deb_patch["content"]
                })
                found_match = True
                break
        
        if not found_match:
            result["unique_debian_patches"].append(deb_patch["name"])
    
    for fed_patch in result["fedora_patches"]:
        if fed_patch["content"] not in debian_patch_contents:
            result["unique_fedora_patches"].append(fed_patch["name"])
    
    # 统计信息
    result["stats"] = {
        "total_debian_patches": len(result["debian_patches"]),
        "total_fedora_patches": len(result["fedora_patches"]),
        "common_patches": len(result["common_patches"]),
        "unique_debian_patches": len(result["unique_debian_patches"]),
        "unique_fedora_patches": len(result["unique_fedora_patches"])
    }
    
    logging.info(f"分析完成: 共有{result['stats']['common_patches']}个共同补丁, " +
                 f"{result['stats']['unique_debian_patches']}个Debian独有补丁, " +
                 f"{result['stats']['unique_fedora_patches']}个Fedora独有补丁")
    
    return result

def read_wsl_file_content(file_path):
    """
    从WSL中读取文件内容
    
    Args:
        file_path: WSL中的文件路径
    
    Returns:
        str: 文件内容，如果读取失败则返回空字符串
    """
    file_path = file_path.replace("\\", "/")  # 确保使用Linux风格的路径分隔符
    cmd = f"wsl -d Debian -u penny bash -c 'cat \"{file_path}\" 2>/dev/null || echo \"\"'"
    result = subprocess.run(
        cmd, 
        shell=True, 
        capture_output=True, 
        text=True,
        encoding='utf-8',  # 明确指定UTF-8编码
        errors='replace'   # 对无法解码的部分进行替换而不是抛出异常
    )
    return result.stdout

def get_fedora_patch_names(package_name, spec_dir):
    """
    获取Fedora补丁文件名列表
    
    Args:
        package_name: 包名称
        spec_dir: spec文件目录路径
    
    Returns:
        list: 补丁文件名列表
    """
    logging.info(f"获取{package_name}的Fedora补丁文件名")
    
    # 确保路径使用Linux风格的分隔符
    package_name = package_name.replace("\\", "/")
    spec_dir = spec_dir.replace("\\", "/") if spec_dir else None
    
    # 构建spec文件路径
    spec_file = f"{spec_dir}/{package_name}.spec"
    
    # 读取spec文件内容
    cmd = f"wsl -d Fedora bash -c 'cat \"{spec_file}\" 2>/dev/null'"
    cat_result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    if cat_result.returncode != 0 or not cat_result.stdout.strip():
        logging.warning(f"无法读取spec文件: {spec_file}")
        return []
    
    spec_content = cat_result.stdout
    
    # 使用rpm_patch_analyzer中的get_patch_names函数提取补丁名称
    patch_names = get_patch_names(spec_content)
    logging.info(f"从spec文件中找到{len(patch_names)}个补丁名称")
    
    return patch_names

def get_patch_file_content(distribution, patch_name, source_dir="/home/penny/rpmbuild/SOURCES"):
    """
    获取补丁文件内容，支持本地和远程补丁文件
    
    Args:
        distribution: 发行版名称
        patch_name: 补丁文件名
        source_dir: 源码目录路径
        
    Returns:
        list: 补丁文件内容的行列表，失败则返回None
    """
    if patch_name.startswith('http'):
        # 下载补丁文件
        logging.info(f"下载补丁文件: {patch_name}")
        try:
            response = requests.get(patch_name)
            if response.status_code == 200:
                logging.info(f"成功下载补丁文件: {patch_name}")
                return response.text.splitlines()
            else:
                logging.error(f"无法下载补丁文件: {patch_name}，状态码: {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"下载补丁文件失败: {patch_name} 错误: {e}")
            return None
    else:
        # 处理本地补丁文件
        patch_path = f"{source_dir}/{patch_name}"  # 在WSL环境中的路径
        logging.info(f"读取本地补丁文件: {patch_path}")

        # 检查文件是否存在
        command_check = f"wsl -d {distribution} bash -c 'test -e \"{patch_path}\"'"
        command_cat = f"wsl -d {distribution} bash -c 'cat \"{patch_path}\"'"

        try:
            result_check = subprocess.run(
                command_check,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            if result_check.returncode == 0:
                # 文件存在，读取内容
                logging.info(f"文件 {patch_path} 在 {distribution} 中找到，读取内容...")
                result_cat = subprocess.run(
                    command_cat,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )

                if result_cat.returncode == 0:
                    patch_content = result_cat.stdout.splitlines()
                    logging.info(f"成功读取补丁文件: {patch_path}，长度: {len(patch_content)}行")
                    return patch_content
                else:
                    logging.error(f"读取文件失败: {patch_path} 错误: {result_cat.stderr}")
                    return None
            else:
                logging.warning(f"补丁文件不存在: {patch_path}")
                return None
        except Exception as e:
            logging.error(f"处理补丁文件时出错: {patch_path} 错误: {e}")
            return None

# 添加此函数用于支持analyze_fedora_debian_patches中的调用
def get_patch_content(path, is_debian=False):
    """
    获取补丁文件内容，支持Debian和Fedora补丁文件
    
    Args:
        path: 补丁文件路径
        is_debian: 是否为Debian补丁
        
    Returns:
        list: 补丁文件内容的行列表，失败则返回None
    """
    # 确保路径使用Linux风格的分隔符
    path = path.replace("\\", "/")
    
    distribution = "Debian" if is_debian else "Fedora"
    # 检查文件是否存在
    command_check = f"wsl -d {distribution} bash -c 'test -e \"{path}\"'"
    command_cat = f"wsl -d {distribution} bash -c 'cat \"{path}\"'"

    try:
        result_check = subprocess.run(
            command_check,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        if result_check.returncode == 0:
            # 文件存在，读取内容
            logging.info(f"文件 {path} 在 {distribution} 中找到，读取内容...")
            result_cat = subprocess.run(
                command_cat,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            if result_cat.returncode == 0:
                patch_content = result_cat.stdout.splitlines()
                logging.info(f"成功读取补丁文件: {path}，长度: {len(patch_content)}行")
                return patch_content
            else:
                logging.error(f"读取文件失败: {path} 错误: {result_cat.stderr}")
                return None
        else:
            logging.warning(f"补丁文件不存在: {path}")
            return None
    except Exception as e:
        logging.error(f"处理补丁文件时出错: {path} 错误: {e}")
        return None

def normalize_patch_lines(patch_lines):
    """
    对patch的每一行做标准化处理，去除空行、注释行、多余空格，保持主要代码信息
    """
    normalized = []
    for line in patch_lines:
        line = line.strip()
        # 跳过空行或者全是注释的行
        if not line or line.startswith('#') or line.startswith('//') or line.startswith('/*') or line.startswith('*') or line.startswith('*/'):
            continue
        normalized.append(line)
    return normalized

def extract_fuzzy_paths(patch_lines):
    """
    从patch中提取文件路径，并做模糊处理（提取最后两级目录或文件名）
    """
    paths = set()
    for line in patch_lines:
        if line.startswith('+++ ') or line.startswith('--- '):
            path = line.split('\t')[0][4:]  # 去掉'+++ '或'--- '前缀
            path = path.strip()
            if path.startswith('a/') or path.startswith('b/'):
                path = path[2:]  # 去掉git格式路径前缀
            parts = path.split('/')
            if len(parts) >= 2:
                fuzzy_path = '/'.join(parts[-2:])  # 取最后两级目录/文件
            else:
                fuzzy_path = parts[-1]  # 只有文件名
            paths.add(fuzzy_path)
    return paths

def calculate_patch_similarity_improved(patch1_lines, patch2_lines):
    """
    综合考虑文件路径模糊匹配、修改内容差异、归一化后的原始内容相似度
    """
    if not patch1_lines or not patch2_lines:
        return 0.0

    # 1. 先做fuzzy路径提取
    paths1 = extract_fuzzy_paths(patch1_lines)
    paths2 = extract_fuzzy_paths(patch2_lines)

    # 计算路径的Jaccard相似度
    if paths1 or paths2:
        intersection = len(paths1 & paths2)
        union = len(paths1 | paths2)
        path_similarity = intersection / union if union else 0.0
    else:
        path_similarity = 0.0
    logging.info(f"文件路径模糊相似度: {path_similarity:.4f}")

    # 2. 提取添加行和删除行
    added_lines1 = [line[1:].strip() for line in patch1_lines if line.startswith('+') and not line.startswith('+++')]
    removed_lines1 = [line[1:].strip() for line in patch1_lines if line.startswith('-') and not line.startswith('---')]

    added_lines2 = [line[1:].strip() for line in patch2_lines if line.startswith('+') and not line.startswith('+++')]
    removed_lines2 = [line[1:].strip() for line in patch2_lines if line.startswith('-') and not line.startswith('---')]

    # 3. 使用tokenize和n-gram方法计算代码相似度
    added_tokens1 = [token for line in added_lines1 for token in tokenize_code(line)]
    removed_tokens1 = [token for line in removed_lines1 for token in tokenize_code(line)]
    added_tokens2 = [token for line in added_lines2 for token in tokenize_code(line)]
    removed_tokens2 = [token for line in removed_lines2 for token in tokenize_code(line)]

    added_ngrams1 = generate_ngrams(added_tokens1)
    removed_ngrams1 = generate_ngrams(removed_tokens1)
    added_ngrams2 = generate_ngrams(added_tokens2)
    removed_ngrams2 = generate_ngrams(removed_tokens2)

    added_jaccard = 0
    if added_ngrams1 or added_ngrams2:
        added_intersection = len(added_ngrams1.intersection(added_ngrams2))
        added_union = len(added_ngrams1.union(added_ngrams2))
        added_jaccard = added_intersection / added_union if added_union > 0 else 0

    removed_jaccard = 0
    if removed_ngrams1 or removed_ngrams2:
        removed_intersection = len(removed_ngrams1.intersection(removed_ngrams2))
        removed_union = len(removed_ngrams1.union(removed_ngrams2))
        removed_jaccard = removed_intersection / removed_union if removed_union > 0 else 0

    code_similarity = 0.5 * added_jaccard + 0.5 * removed_jaccard
    logging.info(f"代码n-gram相似度: {code_similarity:.4f}")

    # 4. 归一化patch内容后，再计算整体相似度（作为兜底）
    normalized_patch1 = normalize_patch_lines(patch1_lines)
    normalized_patch2 = normalize_patch_lines(patch2_lines)
    raw_similarity = 0.0
    if normalized_patch1 and normalized_patch2:
        raw_matcher = difflib.SequenceMatcher(None, '\n'.join(normalized_patch1), '\n'.join(normalized_patch2))
        raw_similarity = raw_matcher.ratio()
    logging.info(f"归一化后原始内容相似度: {raw_similarity:.4f}")

    # 5. 综合路径相似度和代码变更相似度
    final_similarity = 0.1 * path_similarity + 0.9 * code_similarity

    # 6. 特殊情况补救：如果代码变更低但整体归一化内容高，则采用归一化结果
    if code_similarity < 0.5 and raw_similarity > 0.8:
        final_similarity = (final_similarity + raw_similarity) / 2
        logging.info("采用归一化内容相似度进行补充调整")

    logging.info(f"最终相似度得分: {final_similarity:.4f}")
    return final_similarity

def find_srpm_file(package_name, fedora_sources_dir="/home/penny/fedora_sources"):
    """
    查找包的SRPM文件
    
    Args:
        package_name: 包名
        fedora_sources_dir: Fedora源码目录
    
    Returns:
        str: SRPM文件路径，如果未找到则返回None
    """
    logging.info(f"查找{package_name}的SRPM文件")
    
    # 确保路径使用Linux风格的分隔符
    package_name = package_name.replace("\\", "/")
    fedora_sources_dir = fedora_sources_dir.replace("\\", "/")
    
    # 检查WSL发行版状态
    check_wsl_cmd = "wsl -d Fedora echo OK"
    wsl_result = subprocess.run(
        check_wsl_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    if wsl_result.returncode != 0 or "OK" not in wsl_result.stdout:
        logging.error(f"WSL Fedora发行版可能无法访问或未正确配置: {wsl_result.stderr}")
        return None
    
    # 首先列出源码目录内容，检查包目录是否真的存在
    list_dir_cmd = f"wsl -d Fedora bash -c 'ls -la \"{fedora_sources_dir}/\" | grep -i \"{package_name}\"'"
    
    list_result = subprocess.run(
        list_dir_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    logging.debug(f"源码目录列表结果: {list_result.stdout}")
    
    # 尝试使用不区分大小写的方式找到实际目录名
    if list_result.returncode == 0 and list_result.stdout.strip():
        # 从列表结果中提取实际的目录名（可能大小写不同）
        dir_entries = list_result.stdout.strip().split('\n')
        for entry in dir_entries:
            parts = entry.split()
            if len(parts) >= 9:  # ls -la输出格式中文件名在第9位
                actual_name = parts[8]
                if actual_name.lower() == package_name.lower():
                    package_name = actual_name  # 使用实际的目录名
                    logging.info(f"找到实际的包目录名: {actual_name}")
                    break
    
    # 构建包目录路径
    package_dir = f"{fedora_sources_dir}/{package_name}"
    
    # 检查包目录是否存在
    check_dir_cmd = f"wsl -d Fedora bash -c 'test -d \"{package_dir}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\"'"
    
    dir_result = subprocess.run(
        check_dir_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    logging.debug(f"目录检查结果: {dir_result.stdout}")
    
    if 'NOT_EXISTS' in dir_result.stdout:
        logging.error(f"包目录不存在: {package_dir}")
        
        # 尝试在整个源码目录中搜索名称相似的目录
        find_similar_cmd = f"wsl -d Fedora bash -c 'find \"{fedora_sources_dir}\" -maxdepth 1 -type d -name \"*{package_name}*\" 2>/dev/null'"
        
        similar_result = subprocess.run(
            find_similar_cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        if similar_result.returncode == 0 and similar_result.stdout.strip():
            similar_dirs = similar_result.stdout.strip().split('\n')
            logging.info(f"找到可能相关的目录: {similar_dirs}")
            
            # 尝试使用第一个相似目录
            package_dir = similar_dirs[0]
            logging.info(f"尝试使用替代目录: {package_dir}")
        else:
            return None
    
    # 方法1: 使用find命令查找所有.src.rpm文件
    logging.info(f"查找SRPM文件命令: wsl -d Fedora bash -c 'find \"{package_dir}\" -name \"*.src.rpm\" -type f'")
    find_cmd = f"wsl -d Fedora bash -c 'find \"{package_dir}\" -name \"*.src.rpm\" -type f 2>/dev/null || echo \"NOT_FOUND\"'"
    
    find_result = subprocess.run(
        find_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    # 调试输出原始结果
    logging.debug(f"SRPM查找原始结果: {repr(find_result.stdout)}")
    
    if find_result.returncode == 0 and 'NOT_FOUND' not in find_result.stdout:
        srpm_files = find_result.stdout.strip().split('\n')
        if srpm_files and srpm_files[0]:
            logging.info(f"找到SRPM文件: {srpm_files[0]}")
            return srpm_files[0]
    
    # 方法2: 使用ls命令列出所有.src.rpm文件
    logging.info(f"使用ls命令查找SRPM文件: wsl -d Fedora bash -c 'ls -1 \"{package_dir}/\"*.src.rpm'")
    ls_cmd = f"wsl -d Fedora bash -c 'ls -1 \"{package_dir}\"/*.src.rpm 2>/dev/null || echo \"NOT_FOUND\"'"
    
    ls_result = subprocess.run(
        ls_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    # 如果ls命令返回结果
    if ls_result.returncode == 0 and 'NOT_FOUND' not in ls_result.stdout:
        srpm_files = ls_result.stdout.strip().split('\n')
        if srpm_files and srpm_files[0]:
            logging.info(f"使用ls命令找到SRPM文件: {srpm_files[0]}")
            return srpm_files[0]
    
    # 方法3: 直接使用echo展开通配符
    logging.info(f"使用echo命令查找SRPM文件")
    echo_cmd = f"wsl -d Fedora bash -c 'echo \"{package_dir}\"/*.src.rpm 2>/dev/null'"
    
    echo_result = subprocess.run(
        echo_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    # 检查是否得到了有效的文件路径（不包含通配符）
    if echo_result.returncode == 0 and '*' not in echo_result.stdout:
        srpm_files = echo_result.stdout.strip().split('\n')
        if srpm_files and srpm_files[0] and srpm_files[0] != f"{package_dir}/*.src.rpm":
            logging.info(f"使用echo命令找到SRPM文件: {srpm_files[0]}")
            return srpm_files[0]
    
    # 方法4: 递归搜索整个目录树
    logging.info("递归搜索整个fedora_sources目录")
    recursive_cmd = f"wsl -d Fedora bash -c 'find \"{fedora_sources_dir}\" -name \"{package_name}*.src.rpm\" -type f 2>/dev/null || echo \"NOT_FOUND\"'"
    
    recursive_result = subprocess.run(
        recursive_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    if recursive_result.returncode == 0 and 'NOT_FOUND' not in recursive_result.stdout:
        srpm_files = recursive_result.stdout.strip().split('\n')
        if srpm_files and srpm_files[0]:
            logging.info(f"在整个目录树中找到SRPM文件: {srpm_files[0]}")
            return srpm_files[0]
    
    logging.error(f"在{package_dir}目录中未找到SRPM文件")
    return None
