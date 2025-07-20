#!/usr/bin/env python3

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
DEFAULT_FEDORA_SPEC_DIR = "/home/XXX/rpmbuild/SPECS"
DEFAULT_DEBIAN_BASE_DIR = "/home/XXX/packages_info"
DEFAULT_OUTPUT_DIR = "data/patches"
DEFAULT_OUTPUT_FILE = "deb_rpm_patch_comparison_report.json"
DEFAULT_LOG_FILE = "data/patches/deb_rpm_patches.log"
DEFAULT_FEDORA_DISTRO = "Fedora"
DEFAULT_DEBIAN_DISTRO = "Debian"

IS_WINDOWS = platform.system() == "Windows"

def check_wsl_path_exists(path, distro="Fedora"):
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
    if path:
        return path.replace("\\", "/")
    return path


def setup_logging(log_file=DEFAULT_LOG_FILE):
    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)
    
    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers:
            root_logger.removeHandler(handler)
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    console_handler = logging.StreamHandler()
    
    log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
    file_handler.setFormatter(log_format)
    console_handler.setFormatter(log_format)
    
    root_logger.setLevel(logging.DEBUG)
    file_handler.setLevel(logging.DEBUG)
    console_handler.setLevel(logging.INFO)
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

def load_common_packages(json_file=DEFAULT_COMMON_PACKAGES_FILE):
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            package_data = json.load(f)
        
        if "debian_fedora_common" in package_data:
            common_packages = package_data["debian_fedora_common"]
            return common_packages
        else:
            alternative_keys = [k for k in package_data.keys() if "debian" in k.lower() and "fedora" in k.lower()]
            if alternative_keys:
                common_packages = package_data[alternative_keys[0]]
                return common_packages
            else:
                return {}
    except Exception as e:
        return {}

def test_debian_patch_extraction(package_name, debian_base_dir=DEFAULT_DEBIAN_BASE_DIR):
    
    debian_base_dir = normalize_path(debian_base_dir)
    
    patches_dir, series_file, has_patches = find_debian_patch_dir(package_name, debian_base_dir)
    
    if not has_patches:
        return []
    
    patch_names = get_debian_patch_names(series_file, patches_dir)
    
    results = {}
    for patch_name in patch_names:
        
        patch_content = get_debian_patch_file_content(patch_name, patches_dir)
        if not patch_content:
            continue
        
        patch_info_data = analyze_patch(patch_content)
        
        normalized_content = normalize_patch_content(patch_content)
        
        strip_level = 1
        
        features = extract_patch_features(normalized_content, strip_level)
        
        results[patch_name] = {
            "info": patch_info_data,
            "features": features,
            "strip_level": strip_level
        }
    
    output_dir = DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{package_name}_debian_patches.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    return results

def test_fedora_patch_extraction(package_name, fedora_dist=DEFAULT_FEDORA_DISTRO, spec_dir=DEFAULT_FEDORA_SPEC_DIR):
    
    spec_dir = normalize_path(spec_dir)
    
    spec_file = os.path.join(spec_dir, f"{package_name}.spec")
    spec_file = normalize_path(spec_file)
    
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
        from relibrary.core.patch.deb_rpm_patch_analyzer_fileName import find_srpm_file
        
        srpm_path = find_srpm_file(package_name)
        
        if srpm_path:
            srpm_file = os.path.basename(srpm_path)
            
            srpm_dir = os.path.dirname(srpm_path)
            install_cmd = f"wsl -d {fedora_dist} bash -c 'cd \"{srpm_dir}\" && rpm -ivh {srpm_file}'"
            install_result = subprocess.run(
                install_cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if install_result.returncode == 0:
                fedora_result = subprocess.run(
                    command_cat,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                if fedora_result.returncode != 0:
                    return None
            else:
                return None
        else:
            return None
    
    spec_content = result_cat.stdout
    
    patch_info = get_patch_info(spec_content)
    patches = list(patch_info.keys())
    
    results = {}
    for patch_name in patches:
        
        patch_content = get_patch_file_content(fedora_dist, patch_name)
        if not patch_content:
            continue
        
        patch_info_data = analyze_patch(patch_content)
        
        normalized_content = normalize_patch_content(patch_content)
        
        strip_level = patch_info.get(patch_name, {}).get('strip_level', 0)
        
        features = extract_patch_features(normalized_content, strip_level)
        
        results[patch_name] = {
            "info": patch_info_data,
            "features": features,
            "strip_level": strip_level
        }
    
    output_dir = DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{package_name}_fedora_patches.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    return results

def test_distro_comparison(package_name, fedora_name=None, debian_name=None, fedora_spec=None, debian_base_dir=DEFAULT_DEBIAN_BASE_DIR, fedora_dist=DEFAULT_FEDORA_DISTRO, similarity_threshold=0.7):
    fedora_package_name = fedora_name or package_name
    debian_package_name = debian_name or package_name

    
    debian_base_dir = normalize_path(debian_base_dir)
    
    if not fedora_spec:
        fedora_spec = normalize_path(os.path.join(DEFAULT_FEDORA_SPEC_DIR, f"{fedora_package_name}.spec"))
    else:
        fedora_spec = normalize_path(fedora_spec)
    
    if not check_wsl_path_exists(fedora_spec, fedora_dist):
        
        fedora_source_dir = normalize_path("/home/XXX/rpmbuild/SOURCES")
        if check_wsl_path_exists(fedora_source_dir, fedora_dist):
            fedora_patch_dir = fedora_source_dir
        else:
            temp_dir = tempfile.mkdtemp(prefix="fedora_patch_")
            fedora_patch_dir = normalize_path(temp_dir)
    else:
        fedora_patch_dir = normalize_path("/home/XXX/rpmbuild/SOURCES")
        
        if not check_wsl_path_exists(fedora_patch_dir, fedora_dist):
            temp_dir = tempfile.mkdtemp(prefix="fedora_patch_")
            fedora_patch_dir = normalize_path(temp_dir)
    
    debian_patches_dir, series_file, has_debian_patches = find_debian_patch_dir(debian_package_name, debian_base_dir)
    
    if not has_debian_patches:
        debian_patches = []
    else:
        debian_patches = get_debian_patch_names(series_file, debian_patches_dir)
    
    fedora_command = f"wsl -d {fedora_dist} bash -c 'cat \"{fedora_spec}\"'"
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
            from relibrary.core.patch.deb_rpm_patch_analyzer_fileName import find_srpm_file
            
            srpm_path = find_srpm_file(fedora_package_name)
            
            if srpm_path:
                srpm_file = os.path.basename(srpm_path)
                
                srpm_dir = os.path.dirname(srpm_path)
                install_cmd = f"wsl -d {fedora_dist} bash -c 'cd \"{srpm_dir}\" && rpm -ivh {srpm_file}'"
                install_result = subprocess.run(
                    install_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                if install_result.returncode == 0:
                    fedora_result = subprocess.run(
                        fedora_command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace'
                    )
                    
                    if fedora_result.returncode != 0:
                        return None
                else:
                    return None
            else:
                return None
        
        fedora_spec_content = fedora_result.stdout
    except Exception as e:
        return None
    
    fedora_patches = get_patch_names(fedora_spec_content)
    match_result = compare_fedora_debian_patches(
        fedora_patch_dir, 
        fedora_package_name, 
        debian_patches_dir, 
        series_file, 
        threshold=similarity_threshold 
    )
    
    matched_patches_dict, unmatched_fedora, unmatched_debian, same_function_patches = match_result
    common_patches = [
        {"Fedora": f_patch, "Debian": info["debian_patch"]}
        for f_patch, info in matched_patches_dict.items()
    ]
    
    result = {
        "common_patches": common_patches,
        "unique_fedora_patches": unmatched_fedora,
        "unique_debian_patches": unmatched_debian,
        "same_function_different_content": same_function_patches,
        "missing_patches": {"fedora": [], "debian": []}
    }
    
    if not fedora_patches and not debian_patches:
        result["no_patches"] = True
        return result
    
    missing_fedora = len(result["missing_patches"]["fedora"])
    missing_debian = len(result["missing_patches"]["debian"])
    all_missing = (missing_fedora == len(fedora_patches) and fedora_patches) or \
                 (missing_debian == len(debian_patches) and debian_patches)
    
    if all_missing:
        result["all_patches_missing"] = True
        return result

    if 'missing_patches' in result:
        fedora_missing = len(result['missing_patches']['fedora'])
        debian_missing = len(result['missing_patches']['debian'])
    return result

def test_from_common_packages(json_file=DEFAULT_COMMON_PACKAGES_FILE, output_prefix="report_", similarity_threshold=0.7, max_packages=None, custom_packages=None):
    if custom_packages:
        common_packages = custom_packages
    else:
        common_packages = load_common_packages(json_file)
        if not common_packages:
            return
    
    if max_packages and max_packages > 0:
        package_keys = list(common_packages.keys())[:max_packages]
    else:
        package_keys = common_packages.keys()
    
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
    
    packages_comparison = {}
    error_packages = []
    
    for i, package_key in enumerate(package_keys):
        package_info = common_packages[package_key]
        
        fedora_info = package_info.get("Fedora", {})
        debian_info = package_info.get("Debian", {})
        
        fedora_package_name = fedora_info.get("package_name", package_key)
        debian_package_name = debian_info.get("package_name", package_key)
        
        progress_msg = f" [{i+1}/{len(package_keys)}]: {package_key} (Fedora: {fedora_package_name}, Debian: {debian_package_name})"
        print(progress_msg)
        logging.info(progress_msg)
        
        try:
            fedora_spec = normalize_path(os.path.join(DEFAULT_FEDORA_SPEC_DIR, f"{fedora_package_name}.spec"))
            
            result = test_distro_comparison(
                package_key,
                fedora_name=fedora_package_name,
                debian_name=debian_package_name,
                fedora_spec=fedora_spec,
                similarity_threshold=similarity_threshold
            )
            
            if not result:
                error_msg = f" {package_key} "
                logging.error(error_msg)
                print(error_msg)
                stats["failed_packages"] += 1
                error_packages.append({"package": package_key, "reason": "none"})
                continue
            
            if "no_patches" in result and result["no_patches"]:
                stats["packages_without_patches"] += 1
                info_msg = f" {package_key} "
                logging.info(info_msg)
                print(info_msg)
            else:
                stats["packages_with_patches"] += 1
                
                stats["total_patch_stats"]["common_patches"] += len(result.get("common_patches", []))
                stats["total_patch_stats"]["same_function_different_content"] += len(result.get("same_function_different_content", []))
                stats["total_patch_stats"]["unique_to_fedora"] += len(result.get("unique_fedora_patches", []))
                stats["total_patch_stats"]["unique_to_debian"] += len(result.get("unique_debian_patches", []))
                
                if result.get("missing_patches"):
                    fedora_missing = len(result["missing_patches"].get("fedora", []))
                    debian_missing = len(result["missing_patches"].get("debian", []))
                    if fedora_missing > 0 or debian_missing > 0:
                        stats["packages_with_missing_patches"].append(package_key)
            
            packages_comparison[package_key] = result
            
            stats["processed_packages"] += 1
            status_msg = f" {package_key}"
            logging.info(status_msg)
            print(status_msg)
            
        except Exception as e:
            error_msg = f" {package_key} : {str(e)}"
            logging.error(error_msg)
            logging.error(traceback.format_exc())
            print(error_msg)
            stats["failed_packages"] += 1
            error_packages.append({"package": package_key, "reason": str(e)})
    
    def clean_comparison_results(packages_comp):
        cleaned_results = {}
        for pkg_name, result in packages_comp.items():
            cleaned_result = {}
            
            for key in result:
                if key == 'missing_patches':
                    if (not result['missing_patches'].get('fedora', []) and 
                        not result['missing_patches'].get('debian', [])):
                        continue
                    else:
                        cleaned_result['missing_patches'] = result['missing_patches']
                elif key in ['common_patches', 'unique_fedora_patches', 'unique_debian_patches', 
                           'same_function_different_content']:
                    cleaned_patches = []
                    for patch in result[key]:
                        if key == 'common_patches' and isinstance(patch, dict) and 'debian_patch' in patch:
                            fedora_patch = next(iter(patch.keys()))
                            debian_patch = patch.get('debian_patch')
                            patch_info = {
                                "fedora_patch": fedora_patch,
                                "debian_patch": debian_patch
                            }
                            if 'similarity' in patch:
                                patch_info['similarity'] = patch['similarity']
                            cleaned_patches.append(patch_info)
                        elif isinstance(patch, str):
                            cleaned_patches.append(patch)
                        else:
                            cleaned_patch = {k: v for k, v in patch.items() 
                                           if k not in ['path', 'strip_level']}
                            cleaned_patches.append(cleaned_patch)
                    cleaned_result[key] = cleaned_patches
                else:
                    cleaned_result[key] = result[key]
            
            cleaned_results[pkg_name] = cleaned_result
        
        return cleaned_results
    
    cleaned_packages_comparison = clean_comparison_results(packages_comparison)
    
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
    
    output_msg = f"{output_file}"
    print(output_msg)
    logging.info(output_msg)
    
    return stats

def main():
    parser = argparse.ArgumentParser(description="比较Fedora和Debian的软件包补丁")
    
    parser.add_argument('--common_packages', type=str, default=DEFAULT_COMMON_PACKAGES_FILE,
                      help='path')
    parser.add_argument('--output_dir', type=str, default=DEFAULT_OUTPUT_DIR,
                      help='output')
    parser.add_argument('--test_single', type=str, default=None,
                      help='single')
    parser.add_argument('--fedora_spec', type=str, default=None,
                      help='Fedora spec')
    parser.add_argument('--log_level', type=str, default="DEBUG",
                      choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                      help='level')
    parser.add_argument('--similarity_threshold', type=float, default=0.7,
                      help='similarity threshold, default: 0.7')
    parser.add_argument('--max_packages', type=int, default=None,
                      help='max packages')
    parser.add_argument('--verbose', action='store_true', 
                      help='verbose')
    
    args = parser.parse_args()
    
    log_dir = os.path.dirname(DEFAULT_LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    
    log_level = getattr(logging, args.log_level)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        handlers=[
            logging.FileHandler(DEFAULT_LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    os.makedirs(args.output_dir, exist_ok=True)
    
    if args.test_single:
        
        common_packages = load_common_packages(args.common_packages)
        package_info = common_packages.get(args.test_single, {})
        
        fedora_name = package_info.get("Fedora", {}).get("package_name", args.test_single)
        debian_name = package_info.get("Debian", {}).get("package_name", args.test_single)
        
        fedora_spec = args.fedora_spec
        if not fedora_spec:
            fedora_spec = normalize_path(os.path.join(DEFAULT_FEDORA_SPEC_DIR, f"{fedora_name}.spec"))
        else:
            fedora_spec = normalize_path(fedora_spec)
        
        single_package_dict = {args.test_single: package_info}
        
        test_from_common_packages(
            json_file=None,
            output_prefix="single_",
            similarity_threshold=args.similarity_threshold,
            max_packages=1,
            custom_packages=single_package_dict
        )
    else:
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
        if not logging.getLogger().handlers:
            setup_logging(DEFAULT_LOG_FILE)
        sys.exit(1)