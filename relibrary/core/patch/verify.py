import json

input_path = 'package_analysis_withVersion.json'
output_path = 'filtered_with_version_check.json'

def get_main_version(version):
    return version.split('-')[0] if version else ''

def process():
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    result = {}

    for group_name, pkgs in data.items():
        for pkg_name, pkg_info in pkgs.items():
            match_info = pkg_info.get('match_info')
            if not match_info or match_info.get('match_type') != 'std_match':
                continue

            # 收集所有发行版的version
            versions = {}
            for distro, info in pkg_info.items():
                if distro == 'match_info':
                    continue
                version = info.get('version')
                if version:
                    versions[distro] = version

            # 对比主版本号
            main_versions = {distro: get_main_version(ver) for distro, ver in versions.items()}
            unique_main_versions = set(main_versions.values())
            version_note = None
            if len(unique_main_versions) > 1:
                version_note = f"主版本号不一致: {main_versions}"

            # 记录结果
            if group_name not in result:
                result[group_name] = {}
            result[group_name][pkg_name] = {
                'info': pkg_info,
                'version_check': version_note
            }

    # 输出结果
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    process()