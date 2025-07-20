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

from relibrary.core.patch.rpm_patch_analyzer_fileName import (
    parse_defines, replace_macros_with_values, get_patch_info, get_patch_file_content,
    strip_patch_path, normalize_file_path, extract_patch_features,
    normalize_patch_content, calculate_patch_similarity,
    is_only_header_difference, compare_patches, get_patch_names
)

def find_debian_patch_dir(package_name, debian_base_dir=None):
    
    if debian_base_dir is None:
        debian_base_dir = "/home/xxx/packages_info"
      
    package_name = package_name.replace("\\", "/")
    debian_base_dir = debian_base_dir.replace("\\", "/")
    
    package_dir = f"{debian_base_dir}/{package_name}"
    find_cmd = f"wsl -d Debian -u xxx sh -c \"find '{package_dir}' -type d -path '*/debian/patches' 2>/dev/null || echo 'NOT_FOUND'\""
    
    result = subprocess.run(
        find_cmd, 
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    if result.returncode != 0:
        return None, None, False
    
    output = result.stdout.strip()
    potential_dirs = [line for line in output.split('\n') if line.strip() and line != 'NOT_FOUND']

    
    if not potential_dirs:
        list_dirs_cmd = f"wsl -d Debian -u xxx sh -c \"find '{package_dir}' -type d -name debian 2>/dev/null || echo 'NOT_FOUND'\""
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
        
        for debian_dir in debian_dirs:
            check_patches_cmd = f"wsl -d Debian -u xxx sh -c \"[ -d '{debian_dir}/patches' ] && echo '{debian_dir}/patches' || echo 'NOT_FOUND'\""
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
                potential_dirs.append(patches_dir)
        if not potential_dirs:
            version_cmd = f"wsl -d Debian -u xxx sh -c \"ls -d {package_dir}/*/ 2>/dev/null | sort -V | tail -1 || echo 'NOT_FOUND'\""
            version_result = subprocess.run(
                version_cmd, 
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            latest_dir = version_result.stdout.strip()
            if latest_dir and latest_dir != 'NOT_FOUND':
                check_debian_cmd = f"wsl -d Debian -u xxx sh -c \"[ -d '{latest_dir}/debian/patches' ] && echo '{latest_dir}/debian/patches' || echo 'NOT_FOUND'\""
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
                    potential_dirs.append(patches_dir)
    
    if not potential_dirs:
        return None, None, False
    
    patches_dir = potential_dirs[0]

    verify_cmd = f"wsl -d Debian -u xxx sh -c \"[ -d '{patches_dir}' ] && echo 'EXISTS' || echo 'NOT_EXISTS'\""
    verify_result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    
    if 'EXISTS' not in verify_result.stdout:
        return None, None, False
    
    series_path = f"{patches_dir}/series"
    check_series_cmd = f"wsl -d Debian -u xxx sh -c \"if [ -f '{series_path}' ]; then echo 'SERIES_EXISTS'; else echo 'NO_SERIES'; fi\""
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
        return patches_dir, series_path, True
    else:
        return patches_dir, None, True


def get_debian_patch_names(series_path, patches_dir):
  
    patches_dir = patches_dir.replace("\\", "/") if patches_dir else None
    series_path = series_path.replace("\\", "/") if series_path else None
    
    patch_names = []
    if series_path:
        cat_cmd = f"wsl -d Debian -u xxx sh -c \"cat '{series_path}' 2>/dev/null || echo 'ERROR'\""
        cat_result = subprocess.run(
            cat_cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        
        output = cat_result.stdout.strip()
        
        if output and output != 'ERROR':
            lines = output.splitlines()
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    patch_names.append(line)
            valid_patches = []
            for patch_name in patch_names:
                patch_path = f"{patches_dir}/{patch_name}"
                check_cmd = f"wsl -d Debian -u xxx sh -c \"test -f '{patch_path}' && echo 'EXISTS' || echo 'NOT_EXISTS'\""
                check_result = subprocess.run(
                    check_cmd,
                    shell=True,
                    capture_output=True,
                    text=True
                )
                
                if 'EXISTS' in check_result.stdout:
                    valid_patches.append(patch_name)
                else:
                    logging.warning("ERROR")
            
            patch_names = valid_patches
            
            if patch_names:
                return patch_names
    
    if patches_dir:
        find_cmd = f"wsl -d Debian -u xxx sh -c \"find '{patches_dir}' -type f \\( -name '*.patch' -o -name '*.diff' \\) 2>/dev/null || echo 'NOT_FOUND'\""
        find_result = subprocess.run(
            find_cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        
        output = find_result.stdout.strip()

        if output and 'NOT_FOUND' not in output:
            patch_files = [line.strip() for line in output.splitlines() if line.strip()]
            for patch_file in patch_files:
                if patch_file.startswith(patches_dir):
                    relative_path = patch_file[len(patches_dir):].lstrip('/')
                    patch_names.append(relative_path)
                else:
                    file_name = os.path.basename(patch_file)
                    patch_names.append(file_name)
    if not patch_names and patches_dir:
        wide_find_cmd = f"wsl -d Debian -u xxx sh -c \"find '{patches_dir}' -type f -name '*patch*' 2>/dev/null || echo 'NOT_FOUND'\""
        wide_find_result = subprocess.run(
            wide_find_cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        
        output = wide_find_result.stdout.strip()
        
        if output and 'NOT_FOUND' not in output:
            patch_files = [line.strip() for line in output.splitlines() if line.strip()]
            
            for patch_file in patch_files:
                if patch_file.startswith(patches_dir):
                    relative_path = patch_file[len(patches_dir):].lstrip('/')
                    patch_names.append(relative_path)
                else:
                    file_name = os.path.basename(patch_file)
                    patch_names.append(file_name)
    return patch_names


def get_debian_patch_file_content(patch_name, patches_dir):
    if not patches_dir or not patch_name:
        return None
    
    patches_dir = patches_dir.replace("\\", "/")
    patch_name = patch_name.replace("\\", "/")
    patch_path = f"{patches_dir}/{patch_name}"

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
                return patch_content
            else:
                return None
        else:
            return None
    except Exception as e:
        return None


def compare_fedora_debian_patches(fedora_patch_dir, pkg_name, debian_patch_dir, debian_series_file, threshold=0.7):
    def check_wsl_path_exists(path, distro="Debian"):
        if not path:
            return False
        path = path.replace("\\", "/")
        cmd = f"wsl -d {distro} bash -c 'test -e \"{path}\"'"
        try:
            result = subprocess.run(cmd, shell=True)
            exists = (result.returncode == 0)
            return exists
        except Exception as e:
            return False

    if not check_wsl_path_exists(fedora_patch_dir, "Fedora"):
        return {}, [], [], []

    if debian_patch_dir and not check_wsl_path_exists(debian_patch_dir, "Debian"):
        return {}, [], [], []

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
                    patch_file = os.path.basename(line.strip())
                    fedora_patches.append(patch_file)
        else:
            logging.warning("ERROR")
            if pkg_name:
                fedora_spec_dir = "/home/xxx/rpmbuild/SPECS"
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
                            fedora_patches.append(patch_name)
                        else:
                            logging.warning("ERROR")
    except Exception as e:
        logging.warning("ERROR")
    
    debian_patches = get_debian_patch_names(debian_series_file, debian_patch_dir)
    
    if not debian_patches:
        return {}, fedora_patches, [], []
    matched_patches = {}
    same_function_patches = []
    processed_patches = set() 
    thresholds = [0.7, 0.6, 0.5]
    
    for f_patch in fedora_patches:
        f_path = os.path.join(fedora_patch_dir, f_patch)
        f_path = f_path.replace("\\", "/")
        
        f_content = get_patch_file_content("Fedora", f_patch, fedora_patch_dir)
        
        if not f_content:
            continue
        if len(f_content) > 10000:
            continue
            
        for d_patch in debian_patches:
            patch_pair = (f_patch, d_patch)
            if patch_pair in processed_patches:
                continue
                
            d_path = f"{debian_patch_dir}/{d_patch}"
            d_content = get_debian_patch_file_content(d_patch, debian_patch_dir)
            
            if not d_content:
                continue
            if len(d_content) > 10000:
                continue
                
            try:
                if len(f_content) < 3 or len(d_content) < 3:
                    continue
                
                similarity = calculate_patch_similarity_improved(f_content, d_content)
                processed_patches.add(patch_pair)
                
                if similarity == 1.0:
                    if f_patch not in matched_patches:
                        matched_patches[f_patch] = {
                            "debian_patch": d_patch,
                            "similarity": similarity
                        }
                else:
                    for current_threshold in thresholds:
                        if similarity >= current_threshold:
                            same_function_patches.append({
                                "Fedora": f_patch,
                                "Debian": d_patch,
                                "Similarity": f"{similarity:.2f}"
                            })
                           
                            break
            except Exception as e:
                logging.error(traceback.format_exc())

    func_best = {}
    for patch in same_function_patches:
        f = patch.get("Fedora")
        sim = float(patch.get("Similarity", 0))
        if f not in func_best or sim > float(func_best[f].get("Similarity", 0)):
            func_best[f] = patch
    same_function_patches = list(func_best.values())

    matched_fedora = list(matched_patches.keys())
    matched_debian = [info.get("debian_patch") for info in matched_patches.values()]
    same_function_fedora = [p.get("Fedora") for p in same_function_patches]
    same_function_debian = [p.get("Debian") for p in same_function_patches]
    
    unmatched_fedora = [p for p in fedora_patches if p not in matched_fedora and p not in same_function_fedora]
    unmatched_debian = [p for p in debian_patches if p not in matched_debian and p not in same_function_debian]
    
    return matched_patches, unmatched_fedora, unmatched_debian, same_function_patches

def analyze_fedora_debian_patches(package_name, fedora_dist, debian_path, fedora_source_dir, fedora_spec_dir):
 
    package_name = package_name.replace("\\", "/")
    fedora_source_dir = fedora_source_dir.replace("\\", "/")
    fedora_spec_dir = fedora_spec_dir.replace("\\", "/")
    if debian_path:
        debian_path = debian_path.replace("\\", "/")

    patches_dir, series_path, found = find_debian_patch_dir(package_name)
    if not found:
        debian_patches = []
    else:
        debian_patches = get_debian_patch_names(series_path, patches_dir)
    fedora_patches = get_fedora_patch_names(package_name, fedora_spec_dir)
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
    
    result["stats"] = {
        "total_debian_patches": len(result["debian_patches"]),
        "total_fedora_patches": len(result["fedora_patches"]),
        "common_patches": len(result["common_patches"]),
        "unique_debian_patches": len(result["unique_debian_patches"]),
        "unique_fedora_patches": len(result["unique_fedora_patches"])
    }
    return result

def read_wsl_file_content(file_path):

    file_path = file_path.replace("\\", "/")  
    cmd = f"wsl -d Debian -u xxx bash -c 'cat \"{file_path}\" 2>/dev/null || echo \"\"'"
    result = subprocess.run(
        cmd, 
        shell=True, 
        capture_output=True, 
        text=True,
        encoding='utf-8',  
        errors='replace'  
    )
    return result.stdout

def get_fedora_patch_names(package_name, spec_dir):
    package_name = package_name.replace("\\", "/")
    spec_dir = spec_dir.replace("\\", "/") if spec_dir else None

    spec_file = f"{spec_dir}/{package_name}.spec"

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
        return []
    
    spec_content = cat_result.stdout
    
    patch_names = get_patch_names(spec_content)
    
    return patch_names

def get_patch_file_content(distribution, patch_name, source_dir="/home/xxx/rpmbuild/SOURCES"):
    if patch_name.startswith('http'):
        try:
            response = requests.get(patch_name)
            if response.status_code == 200:
                return response.text.splitlines()
            else:
                return None
        except Exception as e:
            return None
    else:
        patch_path = f"{source_dir}/{patch_name}"
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
                    return patch_content
                else:
                    return None
            else:
                return None
        except Exception as e:
            return None

def get_patch_content(path, is_debian=False):
    path = path.replace("\\", "/")
    
    distribution = "Debian" if is_debian else "Fedora"
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
                return patch_content
            else:
                return None
        else:
            return None
    except Exception as e:
        return None

def normalize_patch_lines(patch_lines):
    normalized = []
    for line in patch_lines:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('//') or line.startswith('/*') or line.startswith('*') or line.startswith('*/'):
            continue
        normalized.append(line)
    return normalized

def extract_fuzzy_paths(patch_lines):
    paths = set()
    for line in patch_lines:
        if line.startswith('+++ ') or line.startswith('--- '):
            path = line.split('\t')[0][4:]  
            path = path.strip()
            if path.startswith('a/') or path.startswith('b/'):
                path = path[2:] 
            parts = path.split('/')
            if len(parts) >= 2:
                fuzzy_path = '/'.join(parts[-2:])  
            else:
                fuzzy_path = parts[-1] 
            paths.add(fuzzy_path)
    return paths

def calculate_patch_similarity_improved(patch1_lines, patch2_lines):
    if not patch1_lines or not patch2_lines:
        return 0.0

    paths1 = extract_fuzzy_paths(patch1_lines)
    paths2 = extract_fuzzy_paths(patch2_lines)

    if paths1 or paths2:
        intersection = len(paths1 & paths2)
        union = len(paths1 | paths2)
        path_similarity = intersection / union if union else 0.0
    else:
        path_similarity = 0.0

    added_lines1 = [line[1:].strip() for line in patch1_lines if line.startswith('+') and not line.startswith('+++')]
    removed_lines1 = [line[1:].strip() for line in patch1_lines if line.startswith('-') and not line.startswith('---')]

    added_lines2 = [line[1:].strip() for line in patch2_lines if line.startswith('+') and not line.startswith('+++')]
    removed_lines2 = [line[1:].strip() for line in patch2_lines if line.startswith('-') and not line.startswith('---')]

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
    normalized_patch1 = normalize_patch_lines(patch1_lines)
    normalized_patch2 = normalize_patch_lines(patch2_lines)
    raw_similarity = 0.0
    if normalized_patch1 and normalized_patch2:
        raw_matcher = difflib.SequenceMatcher(None, '\n'.join(normalized_patch1), '\n'.join(normalized_patch2))
        raw_similarity = raw_matcher.ratio()

    final_similarity = 0.1 * path_similarity + 0.9 * code_similarity

    if code_similarity < 0.5 and raw_similarity > 0.8:
        final_similarity = (final_similarity + raw_similarity) / 2

    return final_similarity

def find_srpm_file(package_name, fedora_sources_dir="/home/xxx/fedora_sources"):
    package_name = package_name.replace("\\", "/")
    fedora_sources_dir = fedora_sources_dir.replace("\\", "/")
    
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
        return None
    
    list_dir_cmd = f"wsl -d Fedora bash -c 'ls -la \"{fedora_sources_dir}/\" | grep -i \"{package_name}\"'"
    
    list_result = subprocess.run(
        list_dir_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    if list_result.returncode == 0 and list_result.stdout.strip():
        dir_entries = list_result.stdout.strip().split('\n')
        for entry in dir_entries:
            parts = entry.split()
            if len(parts) >= 9: 
                actual_name = parts[8]
                if actual_name.lower() == package_name.lower():
                    package_name = actual_name  
                    break
    package_dir = f"{fedora_sources_dir}/{package_name}"
    
    check_dir_cmd = f"wsl -d Fedora bash -c 'test -d \"{package_dir}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\"'"
    
    dir_result = subprocess.run(
        check_dir_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    if 'NOT_EXISTS' in dir_result.stdout:
        
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
            
            package_dir = similar_dirs[0]
        else:
            return None
    find_cmd = f"wsl -d Fedora bash -c 'find \"{package_dir}\" -name \"*.src.rpm\" -type f 2>/dev/null || echo \"NOT_FOUND\"'"
    
    find_result = subprocess.run(
        find_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    if find_result.returncode == 0 and 'NOT_FOUND' not in find_result.stdout:
        srpm_files = find_result.stdout.strip().split('\n')
        if srpm_files and srpm_files[0]:
            return srpm_files[0]
    
    ls_cmd = f"wsl -d Fedora bash -c 'ls -1 \"{package_dir}\"/*.src.rpm 2>/dev/null || echo \"NOT_FOUND\"'"
    
    ls_result = subprocess.run(
        ls_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    if ls_result.returncode == 0 and 'NOT_FOUND' not in ls_result.stdout:
        srpm_files = ls_result.stdout.strip().split('\n')
        if srpm_files and srpm_files[0]:
            return srpm_files[0]
    echo_cmd = f"wsl -d Fedora bash -c 'echo \"{package_dir}\"/*.src.rpm 2>/dev/null'"
    
    echo_result = subprocess.run(
        echo_cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    if echo_result.returncode == 0 and '*' not in echo_result.stdout:
        srpm_files = echo_result.stdout.strip().split('\n')
        if srpm_files and srpm_files[0] and srpm_files[0] != f"{package_dir}/*.src.rpm":
            return srpm_files[0]
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
            return srpm_files[0]
    return None
