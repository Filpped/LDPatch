#!/usr/bin/env python3
import sys
import os
import json
import argparse
import logging
import hashlib
from deb_rpm_patch_analyzer import (
    find_debian_patch_dir,
    get_debian_patch_names,
    get_debian_patch_file_content,
    normalize_patch_content,
    extract_diff_lines_only,
    compare_patches_by_diff_only,
    get_spec_content
)
from rpm_patch_analyzer import get_patch_info, get_patch_file_content as get_fedora_patch_file_content

DEFAULT_FEDORA_DISTRO = "Fedora"
DEFAULT_DEBIAN_DISTRO = "Debian"
DEFAULT_FEDORA_SPEC_DIR = "/home/penny/rpmbuild/SPECS"
DEFAULT_FEDORA_SOURCE_DIR = "/home/penny/rpmbuild/SOURCES"
DEFAULT_DEBIAN_BASE_DIR = "/home/penny/packages_info"

log_filename = 'deb_rpm_patch_compare.log'
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    encoding='utf-8',
    filemode='w'  
)
console = logging.StreamHandler()
console.setLevel(logging.WARNING)
logging.getLogger().addHandler(console)

def normalize_content(content):
    if isinstance(content, list):
        return '\n'.join(str(line) for line in content)
    return content

def match_round(threshold, label, left_src, left_tgt, record, src_dict, tgt_dict):
    for s in list(left_src):
        s_txt = src_dict[s]
        d_s = extract_diff_lines_only(normalize_patch_content(s_txt))
        for t in list(left_tgt):
            t_txt = tgt_dict[t]
            d_t = extract_diff_lines_only(normalize_patch_content(t_txt))
            sim, ok = compare_patches_by_diff_only(s_txt, t_txt, threshold=threshold)
            logging.info(f"{label}: {s} vs {t}, sim={sim:.3f}")
            if ok:
                record.append({"fedora": s, "debian": t, "similarity": round(sim, 3)})
                left_src.remove(s)
                left_tgt.remove(t)
                break

def get_fedora_patches(package, spec_dir, source_dir, distro):
    spec_content = get_spec_content(package, distro, spec_dir)
    if not spec_content:
        return {}
    patch_info = get_patch_info(spec_content)
    patch_names = list(patch_info.keys())  
    results = {}
    for name in patch_names:
        raw = get_fedora_patch_file_content(distro, name, source_dir)
        if raw:
            txt = normalize_content(raw)
            results[name] = txt
    return results

def get_debian_patches(package, deb_base_dir):
    patches_dir, series_file, found = find_debian_patch_dir(package, deb_base_dir)
    if not found:
        return {}
    patch_names = get_debian_patch_names(series_file, patches_dir)
    results = {}
    for name in patch_names:
        raw = get_debian_patch_file_content(name, patches_dir)
        if raw:
            txt = normalize_content(raw)
            results[name] = txt
    return results

def extract_package_pairs(data):
  
    package_pairs = []
    seen = set()
 
    for top_key, top_value in data.items():
        if isinstance(top_value, dict):
            for main_key, main_value in top_value.items():
                if isinstance(main_value, dict):
                    for pkg_key, package_data in main_value.items():
                        if isinstance(package_data, dict):
                            debian_data = package_data.get('Debian', {})
                            fedora_data = package_data.get('Fedora', {})
                            
                            deb_name = debian_data.get('package_name', '')
                            fed_name = fedora_data.get('package_name', '')
                            
                            if deb_name and fed_name:
                                unique_key = f"{deb_name}|{fed_name}"
                                if unique_key not in seen:
                                    seen.add(unique_key)
                                    package_pairs.append({
                                        'key': pkg_key,
                                        'main_key': main_key,
                                        'debian': {
                                            'package_name': deb_name,
                                            'version': debian_data.get('version', ''),
                                            'effname': debian_data.get('effname', '')
                                        },
                                        'fedora': {
                                            'package_name': fed_name,
                                            'version': fedora_data.get('version', ''),
                                            'effname': fedora_data.get('effname', '')
                                        }
                                    })
    
    return package_pairs


def main(input_json, output_json):
    with open(input_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    logging.info("=" * 70)
    logging.info(f": {input_json}")
    logging.info("=" * 70)
    
    package_pairs = extract_package_pairs(data)
    report = {}
    total = len(package_pairs)

    for idx, pair in enumerate(package_pairs, start=1):
        pkg_key = pair['key']
        main_key = pair['main_key']
        deb_name = pair['debian']['package_name']
        fed_name = pair['fedora']['package_name']
        
        if idx % 100 == 0 or idx == 1:
            print(f"[{idx}/{total}] : {idx*100//total}%")
        
        try:
            logging.info(f"  Debian: {deb_name} (: {pair['debian']['version']})")
            logging.info(f"  Fedora: {fed_name} (: {pair['fedora']['version']})")
            
            fed_contents = get_fedora_patches(fed_name, DEFAULT_FEDORA_SPEC_DIR, DEFAULT_FEDORA_SOURCE_DIR, DEFAULT_FEDORA_DISTRO)
            deb_contents = get_debian_patches(deb_name, DEFAULT_DEBIAN_BASE_DIR)
            
            fed_left = set(fed_contents.keys())
            deb_left = set(deb_contents.keys())
            

            for n in sorted(fed_contents):
                h = hashlib.md5(fed_contents[n].encode('utf-8', 'ignore')).hexdigest()
                logging.debug(f"  Fedora: {n} -> {h}")
            for n in sorted(deb_contents):
                h = hashlib.md5(deb_contents[n].encode('utf-8', 'ignore')).hexdigest()
                logging.debug(f"  Debian: {n} -> {h}")

            common_list = []
            similar_list = []
            match_round(1.0, 'common', fed_left, deb_left, common_list, fed_contents, deb_contents)
            match_round(0.8, 'sim', fed_left, deb_left, similar_list, fed_contents, deb_contents)

            unique_fed = list(fed_left)
            unique_deb = list(deb_left)

            report[pkg_key] = {
                "main_key": main_key,
                "debian_package": deb_name,
                "fedora_package": fed_name,
                "debian_version": pair['debian']['version'],
                "fedora_version": pair['fedora']['version'],
                "common_patches": common_list,
                "same_function_different_content": similar_list,
                "unique_fedora_patches": unique_fed,
                "unique_debian_patches": unique_deb,
                "fedora_patch_count": len(fed_contents),
                "debian_patch_count": len(deb_contents)
            }
    
            
        except Exception as e:
            report[pkg_key] = {
                "main_key": main_key,
                "debian_package": deb_name,
                "fedora_package": fed_name,
                "error": str(e)
            }

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f" {output_json}")

    totals = (
        sum(len(v.get('common_patches', [])) for v in report.values() if 'error' not in v),
        sum(len(v.get('same_function_different_content', [])) for v in report.values() if 'error' not in v),
        sum(len(v.get('unique_fedora_patches', [])) for v in report.values() if 'error' not in v),
        sum(len(v.get('unique_debian_patches', [])) for v in report.values() if 'error' not in v)
    )
    
    total_fedora_patches = sum(v.get('fedora_patch_count', 0) for v in report.values() if 'error' not in v)
    total_debian_patches = sum(v.get('debian_patch_count', 0) for v in report.values() if 'error' not in v)
    
    error_count = sum(1 for v in report.values() if 'error' in v)
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', default='deb_rpm_patch_comparison_report.json')
    args = parser.parse_args()
    main(args.input, args.output)
