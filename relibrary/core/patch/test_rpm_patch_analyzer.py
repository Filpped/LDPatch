#!/usr/bin/env python3
import sys
import os
import json
import argparse
import subprocess
import logging
import hashlib
from rpm_patch_analyzer import (
    get_patch_info,
    get_patch_file_content,
    compare_patches_by_diff_only,
    extract_diff_lines_only,
    normalize_patch_content
)

DEFAULT_FEDORA_DISTRO = "Fedora"
DEFAULT_OPENEULER_DISTRO = "openEuler-24.03"
DEFAULT_SPEC_DIR = "/home/penny/rpmbuild/SPECS"
DEFAULT_SOURCE_DIR = "/home/penny/rpmbuild/SOURCES"

log_filename = 'patch_compare.log'
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


def get_spec_content(package_name, distribution, spec_dir=DEFAULT_SPEC_DIR):
    spec_path = f"{spec_dir}/{package_name}.spec"
    cmd = f"wsl -d {distribution} bash -c 'cat \"{spec_path}\"'"
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=60)
        return res.stdout if res.returncode == 0 and res.stdout.strip() else None
    except Exception as e:
        logging.error(f": {package_name}({distribution}): {e}")
        return None


def normalize_content(content):

    if isinstance(content, list):
        return '\n'.join(str(line) for line in content)
    return content


def filter_diff_lines(diff_lines):

    filtered = []
    for l in diff_lines:
        if l in ('+', '-'):
            continue
        if l.startswith('--- ') or l.startswith('+++ '):
            continue
        filtered.append(l)
    return filtered


def match_round(threshold, label, left_src, left_tgt, record, src_dict, tgt_dict):
    logging.info(f" {threshold} ({label})")
    matched_src, matched_tgt = set(), set()
    for s in list(left_src):
        s_txt = src_dict[s]
        raw_s = extract_diff_lines_only(normalize_patch_content(s_txt))
        d_s = filter_diff_lines(raw_s)
        for t in list(left_tgt):
            t_txt = tgt_dict[t]
            raw_t = extract_diff_lines_only(normalize_patch_content(t_txt))
            d_t = filter_diff_lines(raw_t)
            sim, ok = compare_patches_by_diff_only(s_txt, t_txt, threshold=threshold)
            logging.info(f"{label}: {s} vs {t}, sim={sim:.3f}")
            logging.info(f"Fed diff(filtered): {d_s}")
            logging.info(f"Oe diff(filtered): {d_t}")
            if ok:
                record.append({"fedora": s, "openeuler": t, "similarity": round(sim, 3)})
                left_src.remove(s)
                left_tgt.remove(t)
                matched_src.add(s)
                matched_tgt.add(t)
                logging.info(f" [{label}]: {s} <==> {t}")
                break


def extract_package_pairs(data):
  
    package_pairs = []
    
    for top_key, top_value in data.items():
        if isinstance(top_value, dict):
            for pkg_key, package_data in top_value.items():
                if isinstance(package_data, dict):
                    fedora_data = package_data.get('Fedora', {})
                    openeuler_data = None
                    openeuler_key = None
                    for key in package_data.keys():
                        if key.startswith('openEuler'):
                            openeuler_key = key
                            openeuler_data = package_data.get(key, {})
                            break
                    
                    fed_name = fedora_data.get('package_name', '')
                    ope_name = openeuler_data.get('package_name', '') if openeuler_data else ''
                    
                    if fed_name and ope_name:
                        package_pairs.append({
                            'key': pkg_key,
                            'fedora': {
                                'package_name': fed_name,
                                'version': fedora_data.get('version', ''),
                            },
                            'openeuler': {
                                'package_name': ope_name,
                                'version': openeuler_data.get('version', '') if openeuler_data else '',
                                'openeuler_key': openeuler_key
                            }
                        })
    
    return package_pairs


def main(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    logging.info("=" * 70)
    logging.info(f"{input_file}")
    logging.info("=" * 70)
    
    package_pairs = extract_package_pairs(data)
    report = {}
    total = len(package_pairs)
    

    for idx, pair in enumerate(package_pairs, start=1):
        pkg_key = pair['key']
        fed_name = pair['fedora']['package_name']
        ope_name = pair['openeuler']['package_name']
        
        if idx % 100 == 0 or idx == 1:
            print(f"[{idx}/{total}] : {idx*100//total}%")
        
        try:
            logging.info(f"  Fedora: {fed_name} (: {pair['fedora']['version']})")
            logging.info(f"  OpenEuler: {ope_name} (: {pair['openeuler']['version']})")

            fed_spec = get_spec_content(fed_name, DEFAULT_FEDORA_DISTRO, DEFAULT_SPEC_DIR)
            ope_spec = get_spec_content(ope_name, DEFAULT_OPENEULER_DISTRO, DEFAULT_SPEC_DIR)
            
            if not fed_spec:
                logging.warning(f"Fedora spec missing: {fed_name}")
                report[pkg_key] = {
                    "fedora_package": fed_name,
                    "openeuler_package": ope_name,
                    "error": f"Fedora spec missing: {fed_name}"
                }
                continue
            
            if not ope_spec:
                logging.warning(f"OpenEuler spec missing: {ope_name}")
                report[pkg_key] = {
                    "fedora_package": fed_name,
                    "openeuler_package": ope_name,
                    "error": f"OpenEuler spec missing: {ope_name}"
                }
                continue

            fed_patches = list(get_patch_info(fed_spec).keys())
            ope_patches = list(get_patch_info(ope_spec).keys())

        
            fed_contents = {}
            ope_contents = {}
            
            for name in fed_patches:
                raw = get_patch_file_content(DEFAULT_FEDORA_DISTRO, name, DEFAULT_SOURCE_DIR)
                if raw:
                    txt = normalize_content(raw)
                    fed_contents[name] = txt
                    logging.info(f"Fedora: {name}, {len(txt.splitlines())} ")
                else:
                    logging.warning(f"Fedora: {name}")
            
            for name in ope_patches:
                raw = get_patch_file_content(DEFAULT_OPENEULER_DISTRO, name, DEFAULT_SOURCE_DIR)
                if raw:
                    txt = normalize_content(raw)
                    ope_contents[name] = txt
                    logging.info(f": {name}, {len(txt.splitlines())} ")
                else:
                    logging.warning(f": {name}")

            fed_left = set(fed_contents.keys())
            ope_left = set(ope_contents.keys())

            for n in sorted(fed_contents):
                h = hashlib.md5(fed_contents[n].encode('utf-8', 'ignore')).hexdigest()
                logging.info(f"Fedora: {n} -> {h}")
            for n in sorted(ope_contents):
                h = hashlib.md5(ope_contents[n].encode('utf-8', 'ignore')).hexdigest()
                logging.info(f"OpenEuler: {n} -> {h}")

            common_list = []
            similar_list = []
            match_round(1.0, 'common', fed_left, ope_left, common_list, fed_contents, ope_contents)
            match_round(0.8,'sim', fed_left, ope_left, similar_list, fed_contents, ope_contents)

            unique_fed = list(fed_left)
            unique_ope = list(ope_left)
            report[pkg_key] = {
                "fedora_package": fed_name,
                "openeuler_package": ope_name,
                "fedora_version": pair['fedora']['version'],
                "openeuler_version": pair['openeuler']['version'],
                "common_patches": common_list,
                "same_function_different_content": similar_list,
                "unique_fedora_patches": unique_fed,
                "unique_openeuler_patches": unique_ope,
                "fedora_patch_count": len(fed_contents),
                "openeuler_patch_count": len(ope_contents)
            }
            
            
        except Exception as e:
            logging.error(f": {pkg_key} (Fedora: {fed_name}, OpenEuler: {ope_name}), error: {e}", exc_info=True)
            report[pkg_key] = {
                "fedora_package": fed_name if 'fed_name' in locals() else '',
                "openeuler_package": ope_name if 'ope_name' in locals() else '',
                "error": str(e)
            }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


    totals = (
        sum(len(v.get('common_patches', [])) for v in report.values() if 'error' not in v),
        sum(len(v.get('same_function_different_content', [])) for v in report.values() if 'error' not in v),
        sum(len(v.get('unique_fedora_patches', [])) for v in report.values() if 'error' not in v),
        sum(len(v.get('unique_openeuler_patches', [])) for v in report.values() if 'error' not in v)
    )
    
    total_fedora_patches = sum(v.get('fedora_patch_count', 0) for v in report.values() if 'error' not in v)
    total_openeuler_patches = sum(v.get('openeuler_patch_count', 0) for v in report.values() if 'error' not in v)
    
    error_count = sum(1 for v in report.values() if 'error' in v)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', default='rpm_patch_comparison_report.json')
    args = parser.parse_args()
    main(args.input, args.output)
