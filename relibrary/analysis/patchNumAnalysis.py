import json

def analyze_patch_overlap(json_path, distro1, distro2):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    total_pkgs = len(data)
    pkgs_with_patch = 0
    pkgs_with_overlap = 0
    pkgs_completely_different = 0
    overlap_ratios = []

    for pkg, info in data.items():
        patches_1 = info.get(f'unique_{distro1}_patches', [])
        patches_2 = info.get(f'unique_{distro2}_patches', [])
        common_patches = info.get('common_patches', [])
        similar_patches = info.get('same_function_different_content', [])
        # 有补丁软件包的判定
        has_patch = patches_1 or patches_2 or common_patches or similar_patches
        if not has_patch:
            continue
        pkgs_with_patch += 1
        # 有重叠的判定
        if common_patches or similar_patches:
            pkgs_with_overlap += 1
            # 计算重叠率
            overlap_cnt = len(common_patches) + len(similar_patches)
            total_cnt = (
                len(patches_1) + len(patches_2) + len(common_patches) + len(similar_patches)
            )
            # 若同一补丁计数重复会导致分母变大，但你的json结构一般不会重复，可以忽略。也可加 set() 去重
            union_set = set(patches_1) | set(patches_2)
            # 把common和similar的内容分别加入集合，处理下内容格式
            for x in common_patches:
                # common_patches 结构是 dict，需提取值
                for v in x.values():
                    union_set.add(v)
            for x in similar_patches:
                for v in x.values():
                    union_set.add(v)
            if len(union_set) > 0:
                overlap_ratios.append(overlap_cnt / len(union_set))
            else:
                overlap_ratios.append(0)
        else:
            pkgs_completely_different += 1
    completely_diff_rate = pkgs_completely_different / pkgs_with_patch if pkgs_with_patch else 0
    overall_overlap_rate = pkgs_with_overlap / pkgs_with_patch if pkgs_with_patch else 0
    avg_patch_overlap_ratio = sum(overlap_ratios) / len(overlap_ratios) if overlap_ratios else 0
    return {
        "total_pkgs": total_pkgs,
        "pkgs_with_patch": pkgs_with_patch,
        "pkgs_with_overlap": pkgs_with_overlap,
        "pkgs_completely_different": pkgs_completely_different,
        "overall_overlap_rate": overall_overlap_rate,
        "avg_patch_overlap_ratio": avg_patch_overlap_ratio,
        "completely_diff_rate": completely_diff_rate,
    }

# Fedora-Debian
deb_rpm_file = 'relibrary/core/patch/deb_rpm_patch_comparison_report.json'
debian_fedora_stats = analyze_patch_overlap(deb_rpm_file, "fedora", "debian")

# Fedora-openEuler
rpm_file = 'relibrary/core/patch/rpm_patch_comparison_report.json'
fedora_openeuler_stats = analyze_patch_overlap(rpm_file, "fedora", "openeuler")

def print_stats(title, stats):
    print(f"{title} 共有包数: {stats['total_pkgs']}, 有补丁包数: {stats['pkgs_with_patch']}, "
          f"有重叠补丁包数: {stats['pkgs_with_overlap']}, 完全不同补丁包数: {stats['pkgs_completely_different']}, "
          f"重叠包比例: {stats['overall_overlap_rate']:.2%}, "
          f"完全不同补丁包数: {stats['pkgs_completely_different']} ({stats['completely_diff_rate']:.2%}), "
          f"重叠包平均补丁重叠率: {stats['avg_patch_overlap_ratio']:.2%}")

print_stats("Fedora-Debian", debian_fedora_stats)
print_stats("Fedora-openEuler", fedora_openeuler_stats)
