import json
import os

def load_and_transform(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if 'packages_comparison' in data:
        data = data['packages_comparison']
    result = {}
    for pkg, info in data.items():
        in_list = []
        for k in ['common_patches', 'same_function_different_content']:
            for patch in info.get(k, []):
                patch_lower = {kk.lower(): vv for kk, vv in patch.items()}
                in_list.append({
                    'fedora': patch_lower.get('fedora', ''),
                    'debian': patch_lower.get('debian', '')
                })
        result[pkg.lower()] = {
            'origin_pkg': pkg,
            'in': in_list,
            'unique_fedora_patches': info.get('unique_fedora_patches', []),
            'unique_debian_patches': info.get('unique_debian_patches', [])
        }
    return result

def compare_in_sets_detail(dict1, dict2):
    diff = {}
    all_pkgs = set(dict1.keys()) | set(dict2.keys())
    for pkg in all_pkgs:
        in1 = dict1.get(pkg, {}).get('in', [])
        in2 = dict2.get(pkg, {}).get('in', [])
        set1 = set((x['fedora'], x['debian']) for x in in1)
        set2 = set((x['fedora'], x['debian']) for x in in2)
        only1 = set1 - set2
        only2 = set2 - set1
        if only1 or only2:
            diff_name = dict1.get(pkg, {}).get('origin_pkg', dict2.get(pkg, {}).get('origin_pkg', pkg))
            diff[diff_name] = {
                'file1_only': [x for x in in1 if (x['fedora'], x['debian']) in only1],
                'file2_only': [x for x in in2 if (x['fedora'], x['debian']) in only2]
            }
    return diff

def main():
    file1 = 'deb_rpm_patch_comparison_report.json'
    file2 = 'deb_rpm_patch_comparison_xiugai.json'
    out_file = 'patch_in_diff.json'
    dict1 = load_and_transform(file1)
    dict2 = load_and_transform(file2)
    diff = compare_in_sets_detail(dict1, dict2)
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(diff, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main() 