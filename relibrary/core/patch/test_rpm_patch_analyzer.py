#!/usr/bin/env python3

import sys
import os
import json
import argparse
import subprocess
import logging
from relibrary.core.patch.rpm_patch_analyzer_fileName import (
    get_patch_names,
    get_patch_info,
    get_patch_file_content,
    normalize_patch_content,
    get_patch_hash,
    compare_patches
)

DEFAULT_FEDORA_DISTRO = "Fedora"
DEFAULT_OPENEULER_DISTRO = "openEuler-24.03"
DEFAULT_SPEC_DIR = "/home/XXX/rpmbuild/SPECS"
DEFAULT_SOURCE_DIR = "/home/XXX/rpmbuild/SOURCES"

logging.basicConfig(
    filename='patch_compare.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    encoding='utf-8'
)
console = logging.StreamHandler()
console.setLevel(logging.WARNING)
logging.getLogger().addHandler(console)

def get_spec_content(package_name, distribution, spec_dir=DEFAULT_SPEC_DIR):
    spec_path = f"{spec_dir}/{package_name}.spec"
    command = f"wsl -d {distribution} bash -c 'cat \"{spec_path}\"'"
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return result.stdout
    except Exception as e:
        return None

def main(package_analysis_file, output_file="rpm_patch_comparison_report.json"):
    with open(package_analysis_file, 'r', encoding='utf-8') as f:
        package_data = json.load(f)
    common_packages = package_data.get("fedora_openeuler-24.03_common", {})
    packages_comparison = {}

    total_pkgs = len(common_packages)
    for idx, (package_key, package_info) in enumerate(common_packages.items(), 1):
        try:
            fedora_info = package_info.get("Fedora", {})
            openeuler_info = package_info.get("openEuler-24.03", {})
            fedora_package_name = fedora_info.get("package_name", package_key)
            openeuler_package_name = openeuler_info.get("package_name", package_key)
            fedora_spec_content = get_spec_content(fedora_package_name, DEFAULT_FEDORA_DISTRO)
            openeuler_spec_content = get_spec_content(openeuler_package_name, DEFAULT_OPENEULER_DISTRO)
            if not fedora_spec_content or not openeuler_spec_content:
                packages_comparison[package_key] = {"error": "spec file missing"}
                continue

            fedora_patch_info = get_patch_info(fedora_spec_content)
            openeuler_patch_info = get_patch_info(openeuler_spec_content)
            fedora_patches = list(fedora_patch_info.keys())
            openeuler_patches = list(openeuler_patch_info.keys())

            fedora_patch_contents = {}
            openeuler_patch_contents = {}
            for patch_name in fedora_patches:
                content = get_patch_file_content(DEFAULT_FEDORA_DISTRO, patch_name)
                if content:
                    fedora_patch_contents[patch_name] = content
            for patch_name in openeuler_patches:
                content = get_patch_file_content(DEFAULT_OPENEULER_DISTRO, patch_name)
                if content:
                    openeuler_patch_contents[patch_name] = content
            matched_fedora = set()
            matched_openeuler = set()
            fedora_hash_map = {}
            openeuler_hash_map = {}
            for fname, content in fedora_patch_contents.items():
                stripA = fedora_patch_info.get(fname, {}).get('strip_level', 0)
                norm = normalize_patch_content(content)
                hashval = get_patch_hash(norm)
                fedora_hash_map[fname] = (hashval, stripA)
            for oname, content in openeuler_patch_contents.items():
                stripB = openeuler_patch_info.get(oname, {}).get('strip_level', 0)
                norm = normalize_patch_content(content)
                hashval = get_patch_hash(norm)
                openeuler_hash_map[oname] = (hashval, stripB)

            common_patches = []
            fedora_left = set(fedora_patch_contents)
            openeuler_left = set(openeuler_patch_contents)
            matched_fedora = set()
            matched_openeuler = set()

            for fname in list(fedora_left):
                fcontent = fedora_patch_contents[fname]
                stripA = fedora_patch_info.get(fname, {}).get('strip_level', 0)
                found = False
                for oname in list(openeuler_left):
                    ocontent = openeuler_patch_contents[oname]
                    stripB = openeuler_patch_info.get(oname, {}).get('strip_level', 0)
                    sim, _ = compare_patches(fcontent, ocontent, stripA, stripB)
                    if sim == 1.0:
                        common_patches.append({"fedora": fname, "openeuler": oname})
                        fedora_left.discard(fname)
                        openeuler_left.discard(oname)
                        matched_fedora.add(fname)
                        matched_openeuler.add(oname)
                        found = True
                        break
                if found:
                    continue

            same_func_diff_content = []
            for fname in list(fedora_left):
                fcontent = fedora_patch_contents[fname]
                stripA = fedora_patch_info.get(fname, {}).get('strip_level', 0)
                for oname in list(openeuler_left):
                    ocontent = openeuler_patch_contents[oname]
                    stripB = openeuler_patch_info.get(oname, {}).get('strip_level', 0)
                    sim, is_sim = compare_patches(fcontent, ocontent, stripA, stripB)
                    if is_sim:
                        same_func_diff_content.append({"fedora": fname, "openeuler": oname, "similarity": round(sim, 3)})
                        fedora_left.discard(fname)
                        openeuler_left.discard(oname)
                        matched_fedora.add(fname)
                        matched_openeuler.add(oname)
                    
                        break

            unique_fedora = [x for x in fedora_left if x not in matched_fedora]
            unique_openeuler = [x for x in openeuler_left if x not in matched_openeuler]
            final_matched_fedora = set()
            final_matched_openeuler = set()

            for fpatch in unique_fedora:
                fcontent = fedora_patch_contents[fpatch]
                stripA = fedora_patch_info.get(fpatch, {}).get('strip_level', 0)
                for opatch in unique_openeuler:
                    if opatch in final_matched_openeuler:
                        continue
                    ocontent = openeuler_patch_contents[opatch]
                    stripB = openeuler_patch_info.get(opatch, {}).get('strip_level', 0)
                    sim, is_sim = compare_patches(fcontent, ocontent, stripA, stripB)
                    if sim == 1.0:
                        common_patches.append({"fedora": fpatch, "openeuler": opatch})
                        final_matched_fedora.add(fpatch)
                        final_matched_openeuler.add(opatch)
                        break
                    elif is_sim:
                        same_func_diff_content.append({
                            "fedora": fpatch,
                            "openeuler": opatch,
                            "similarity": round(sim, 3)
                        })
                        final_matched_fedora.add(fpatch)
                        final_matched_openeuler.add(opatch)
                        break

            unique_fedora = [x for x in unique_fedora if x not in final_matched_fedora]
            unique_openeuler = [x for x in unique_openeuler if x not in final_matched_openeuler]

            def _make_patch_pair_set(pairlist):
                return set((item["fedora"], item["openeuler"]) for item in pairlist)

            common_pairs = _make_patch_pair_set(common_patches)
            same_func_diff_content = [
                item for item in same_func_diff_content
                if (item["fedora"], item["openeuler"]) not in common_pairs
            ]

            packages_comparison[package_key] = {
                "common_patches": common_patches,
                "same_function_different_content": same_func_diff_content,
                "unique_fedora_patches": unique_fedora,
                "unique_openeuler_patches": unique_openeuler
            }
        except Exception as e:
            packages_comparison[package_key] = {"error": str(e)}

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(packages_comparison, f, ensure_ascii=False, indent=2)
    total_common = 0
    total_similar = 0
    total_fedora_unique = 0
    total_openeuler_unique = 0
    total_missing_fedora = 0
    total_missing_openeuler = 0

    for pkg, result in packages_comparison.items():
        common_patches = result.get("common_patches", [])
        similar_patches = result.get("same_function_different_content", [])
        fedora_unique = result.get("unique_fedora_patches", [])
        openeuler_unique = result.get("unique_openeuler_patches", [])
        fedora_missing = result.get("missing_patches", {}).get("fedora", [])
        openeuler_missing = result.get("missing_patches", {}).get("openeuler", [])
        total_common += len(common_patches)
        total_similar += len(similar_patches)
        total_fedora_unique += len(fedora_unique)
        total_openeuler_unique += len(openeuler_unique)
        total_missing_fedora += len(fedora_missing)
        total_missing_openeuler += len(openeuler_missing)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, help='JSON of common packages')
    parser.add_argument('--output', default='rpm_patch_comparison_report.json', help='Output report')
    args = parser.parse_args()
    main(args.input, args.output)
