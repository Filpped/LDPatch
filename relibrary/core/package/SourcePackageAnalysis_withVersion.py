import subprocess
import re
import os
import time
import html 
import json 
import logging 
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import itertools  
from tqdm import tqdm  
import uuid  
from packaging.version import Version, InvalidVersion

logging.basicConfig(
    filename='package_info.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8',  
    level=logging.INFO
)

def get_package_list(distribution):
    if distribution in ['Ubuntu-24.04', 'Debian']:
        command_packages = f'wsl -d {distribution} -- bash -c "cat /var/lib/apt/lists/*Packages"'
        command_sources = f'wsl -d {distribution} -- bash -c "cat /var/lib/apt/lists/*Sources"'
    elif distribution in ['Fedora', 'openEuler-24.03']:
        command_packages = f'''wsl -d {distribution} -- bash -c "dnf repoquery --queryformat '%{{source_name}}|%{{name}}|%{{url}}|%{{version}}-%{{release}}|%{{summary}}\\n' --available"'''
        command_sources = None
    else:
        logging.warning(f'未知的发行版: {distribution}')
        print(f'未知的发行版: {distribution}')
        return {}

    try:
        logging.info(f'执行命令：{command_packages}')
        env = os.environ.copy()
        env['LANG'] = 'C.UTF-8'

        source_to_binaries = {}
        binary_descriptions = {}
        binary_versions = {}

        if distribution in ['Ubuntu-24.04', 'Debian']:
            process_packages = subprocess.Popen(
                command_packages,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            current_binary = None
            description = ''
            version = ''
            in_description = False
            unique_descriptions = set()
            for line in process_packages.stdout:
                line = line.rstrip('\n')
                if line.startswith('Package:'):
                    if current_binary:
                        if description:
                            description_key = description.split('Description-md5')[0].strip()
                            if description_key not in unique_descriptions:
                                binary_descriptions[current_binary] = description.strip()
                                unique_descriptions.add(description_key)
                        if version:
                            binary_versions[current_binary] = version.strip()
                    current_binary = line.split('Package:', 1)[1].strip()
                    description = ''
                    version = ''
                    in_description = False
                elif line.startswith('Version:'):
                    version = line.split('Version:', 1)[1].strip()
                elif line.startswith('Description:'):
                    description = line.split('Description:', 1)[1].strip()
                    in_description = True
                elif line.startswith(' '):
                    if in_description:
                        description += ' ' + line.strip()
                else:
                    in_description = False
            if current_binary:
                if description:
                    description_key = description.split('Description-md5')[0].strip()
                    if description_key not in unique_descriptions:
                        binary_descriptions[current_binary] = description.strip()
                        unique_descriptions.add(description_key)
                if version:
                    binary_versions[current_binary] = version.strip()
            process_packages.stdout.close()
            process_packages.wait()

            if command_sources:
                logging.info(f'执行命令：{command_sources}')
                print(f'执行命令：{command_sources}')
                process_sources = subprocess.Popen(
                    command_sources,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )

                current_source = None
                binaries = []
                homepage = ''
                version = ''
                for line in process_sources.stdout:
                    line = line.rstrip('\n')
                    if line.startswith('Package:'):
                        if current_source:
                            descriptions = [binary_descriptions.get(b, '') for b in binaries]
                            description = ' '.join(set(descriptions))
                            versions = [binary_versions.get(b, '') for b in binaries]
                            source_to_binaries[current_source] = {
                                'binaries': binaries,
                                'homepage': homepage,
                                'description': description.strip(),
                                'version': version
                            }
                            logging.debug(f"Source package: {current_source}, Description length: {len(description.strip())}")
                        current_source = line.split('Package:', 1)[1].strip()
                        binaries = []
                        homepage = ''
                        version = ''
                    elif line.startswith('Binary:'):
                        binary_line = line.split('Binary:', 1)[1].strip()
                        binaries = [b.strip() for b in binary_line.replace('\n', '').replace(' ', '').split(',')]
                    elif line.startswith('Homepage:'):
                        homepage = line.split('Homepage:', 1)[1].strip()
                    elif line.startswith('Version:'):
                        version = line.split('Version:', 1)[1].strip()
                if current_source:
                    descriptions = [binary_descriptions.get(b, '') for b in binaries]
                    description = ' '.join(set(descriptions))
                    versions = [binary_versions.get(b, '') for b in binaries]
                    source_to_binaries[current_source] = {
                        'binaries': binaries,
                        'homepage': homepage,
                        'description': description.strip(),
                        'version': version
                    }
                process_sources.stdout.close()
                process_sources.wait()
            logging.info(f'完成处理 {distribution} 的输出，时间：{time.strftime("%Y-%m-%d %H:%M:%S")}')
            return source_to_binaries

        else:
            process_packages = subprocess.Popen(
                command_packages,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            for line in process_packages.stdout:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('|', 4)  
                if len(parts) == 5:
                    source_pkg, binary_pkg, homepage, version, description = parts  
                    source_pkg = source_pkg.strip()
                    binary_pkg = binary_pkg.strip()
                    homepage = homepage.strip()
                    version = version.strip()
                    description = description.strip()

                    if not source_pkg or source_pkg.lower() == '(none)':
                        logging.warning(f"跳过 source_pkg 为 '(none)' 或空的包: {line}")
                        continue  

                    if source_pkg in source_to_binaries:
                        source_to_binaries[source_pkg]['binaries'].append(binary_pkg)
                        if not source_to_binaries[source_pkg].get('homepage') and homepage:
                            source_to_binaries[source_pkg]['homepage'] = homepage
                        if description and description not in source_to_binaries[source_pkg]['description']:
                            source_to_binaries[source_pkg]['description'] += f" {description}"
                        if 'version' not in source_to_binaries[source_pkg]:
                            source_to_binaries[source_pkg]['version'] = version
                        else:
                            existing_version = source_to_binaries[source_pkg].get('version', '')
                            if existing_version != version:
                                logging.warning(f"源码包 {source_pkg} 存在不同的版本：{existing_version} vs {version}。保留第一个版本。")
                    else:
                        source_to_binaries[source_pkg] = {
                            'binaries': [binary_pkg],
                            'homepage': homepage if homepage else '未知',
                            'description': description if description else '无描述',
                            'version': version
                        }
                else:
                    logging.warning(f"无效的行格式: {line}")
            process_packages.stdout.close()
            process_packages.wait()
            logging.info(f'完成处理 {distribution} 的输出，时间：{time.strftime("%Y-%m-%d %H:%M:%S")}')
            return source_to_binaries

    except subprocess.TimeoutExpired:
        logging.error(f'获取 {distribution} 的软件包时超时')
        return {}
    except subprocess.CalledProcessError as e:
        logging.error(f'获取 {distribution} 的软件包时出错:\n{e.stderr}')
        return {}
    except Exception as e:
        logging.error(f'获取 {distribution} 的软件包时出错: {e}')
        return {}

def sort_packages(package_list):
    def sort_key(s):
        if not s:
            return (2, s)
        first_char = s[0]
        if first_char.isdigit():
            return (0, s.lower())
        elif first_char.isalpha():
            return (1, s.lower())
        else:
            return (2, s.lower())
    return sorted(package_list, key=sort_key)

def generate_html(package_data, distros):
    html_content = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>源码包分析</title>
    <style>
        body {font-family: Arial, sans-serif;}
        ul {list-style-type: none;}
        li {margin: 5px 0;}
        .menu {display: flex; flex-wrap: wrap; margin-bottom: 20px;}
        .menu a {margin-right: 10px; text-decoration: none; color: blue;}
        .hidden {display: none;}
        .source-package {cursor: pointer; color: blue; text-decoration: underline;}
        .binary-packages {margin-left: 20px;}
    </style>
    <script>
        function showSection(id) {
            var sections = document.getElementsByClassName('section');
            for (var i = 0; i < sections.length; i++) {
                sections[i].classList.add('hidden');
            }
            var sectionToShow = document.getElementById(id);
            if (sectionToShow) {
                sectionToShow.classList.remove('hidden');
            } else {
                console.error("Section with ID '" + id + "' not found.");
            }
        }

        function toggleBinaryPackages(id) {
            var elem = document.getElementById(id);
            if (elem) {
                if (elem.classList.contains('hidden')) {
                    elem.classList.remove('hidden');
                } else {
                    elem.classList.add('hidden');
                }
            } else {
                console.error("Element with ID '" + id + "' not found.");
            }
        }
    </script>
</head>
<body>
    <div class="menu">
        <a href="#" onclick="showSection('ubuntu_all')">1. Ubuntu-24.04 全部软件包</a>
        <a href="#" onclick="showSection('debian_all')">2. Debian12 全部软件包</a>
        <a href="#" onclick="showSection('fedora_all')">3. Fedora41 全部软件包</a>
        <a href="#" onclick="showSection('openeuler_all')">4. openEuler-24.03 全部软件包</a>
        <a href="#" onclick="showSection('ubuntu_debian_common')">5. Ubuntu24.04和Debian12共有的软件包</a>
        <a href="#" onclick="showSection('ubuntu_fedora_common')">6. Ubuntu24.04和Fedora41共有的软件包</a>
        <a href="#" onclick="showSection('ubuntu_openeuler_common')">7. Ubuntu24.04和openEuler24.03共有的软件包</a>
        <a href="#" onclick="showSection('debian_fedora_common')">8. Debian12和Fedora41共有的软件包</a>
        <a href="#" onclick="showSection('debian_openeuler_common')">9. Debian12和openEuler24.03共有的软件包</a>
        <a href="#" onclick="showSection('fedora_openeuler_common')">10. Fedora41和openEuler24.03共有的软件包</a>
        <a href="#" onclick="showSection('ubuntu_debian_fedora_common')">11. Ubuntu24.04、Debian12和Fedora41共有的软件包</a>
        <a href="#" onclick="showSection('all_common')">12. 四个发行版共有的软件包</a>
    </div>
'''

    titles = {
        'ubuntu_all': '1. Ubuntu-24.04 全部软件包',
        'debian_all': '2. Debian12 全部软件包',
        'fedora_all': '3. Fedora41 全部软件包',
        'openeuler_all': '4. openEuler-24.03 全部软件包',
        'ubuntu_debian_common': '5. Ubuntu24.04和Debian12共有的软件包',
        'ubuntu_fedora_common': '6. Ubuntu24.04和Fedora41共有的软件包',
        'ubuntu_openeuler_common': '7. Ubuntu24.04和openEuler24.03共有的软件包',
        'debian_fedora_common': '8. Debian12和Fedora41共有的软件包',
        'debian_openeuler_common': '9. Debian12和openEuler24.03共有的软件包',
        'fedora_openeuler_common': '10. Fedora41和openEuler24.03共有的软件包',
        'ubuntu_debian_fedora_common': '11. Ubuntu24.04、Debian12和Fedora41共有的软件包',
        'all_common': '12. 四个发行版共有的软件包'
    }
    logging.debug("Package data keys: %s", list(package_data.keys()))
    print("Package data keys:", list(package_data.keys()))

    for key, pkg_dict in package_data.items():
        if key not in titles:
            logging.warning(f"Key '{key}' not defined in titles. Skipping.")
            print(f"Warning: Key '{key}' not defined in titles. Skipping.")
            continue

        html_content += f'<div id="{key}" class="section hidden">\n'
        title = titles.get(key, key)
        html_content += f'<h2>{title} 共{len(pkg_dict)}个源软件包</h2>\n'
        html_content += '<ul>\n'
        for i, src_pkg in enumerate(sort_packages(list(pkg_dict.keys()))):
            data = pkg_dict[src_pkg]
            binary_pkgs_id = f"{key}_binary_{i}"
            html_content += f'    <li><span class="source-package" onclick="toggleBinaryPackages(\'{binary_pkgs_id}\')">{html.escape(src_pkg)}</span>\n'
            html_content += f'        <div id="{binary_pkgs_id}" class="binary-packages hidden">\n'

            if isinstance(data, dict) and any(distro in data for distro in distros):
                for distro in data:
                    distro_data = data[distro]
                    binary_pkgs = distro_data.get('binaries', [])
                    homepage = distro_data.get('homepage', '未知')
                    description = distro_data.get('description', '无描述')
                    version = distro_data.get('version', '未知')
                    pkg_name = distro_data.get('package_name', src_pkg)  

                    homepage_escaped = html.escape(homepage)
                    description_escaped = html.escape(description)
                    version_escaped = html.escape(version)
                    upstream_version = extract_upstream_version(version)
                    upstream_version_escaped = html.escape(upstream_version)
                    binary_pkgs_html = ''.join(f'<li>{html.escape(bin_pkg)}</li>' for bin_pkg in binary_pkgs)

                    html_content += f'            <h3>{distro}:</h3>\n'
                    html_content += f'            <p>包名：{html.escape(pkg_name)}</p>\n'
                    html_content += f'            <p>版本：{version_escaped}</p>\n'
                    html_content += f'            <p>上游项目版本：{upstream_version_escaped}</p>\n'

                    if homepage != '未知':
                        html_content += f'            <p>主页：<a href="{homepage_escaped}" target="_blank">{homepage_escaped}</a></p>\n'
                    else:
                        html_content += f'            <p>主页：未知</p>\n'
                    html_content += f'            <p>描述：{description_escaped}</p>\n'
                    html_content += f'            <ul>\n{binary_pkgs_html}\n            </ul>\n'
            else:
                binary_pkgs = data.get('binaries', [])
                homepage = data.get('homepage', '未知')
                description = data.get('description', '无描述')
                version = data.get('version', '未知')

                homepage_escaped = html.escape(homepage)
                description_escaped = html.escape(description)
                version_escaped = html.escape(version)
                upstream_version = extract_upstream_version(version)
                upstream_version_escaped = html.escape(upstream_version)
                binary_pkgs_html = ''.join(f'<li>{html.escape(bin_pkg)}</li>' for bin_pkg in binary_pkgs)
                pkg_name = data.get('package_name', src_pkg)
                html_content += f'            <p>包名：{html.escape(pkg_name)}</p>\n'
                html_content += f'            <p>版本：{version_escaped}</p>\n'
                html_content += f'            <p>上游项目版本：{upstream_version_escaped}</p>\n'
                if homepage != '未知':
                    html_content += f'            <p>主页：<a href="{homepage_escaped}" target="_blank">{homepage_escaped}</a></p>\n'
                else:
                    html_content += f'            <p>主页：未知</p>\n'
                html_content += f'            <p>描述：{description_escaped}</p>\n'
                html_content += f'            <ul>\n{binary_pkgs_html}\n            </ul>\n'
            html_content += f'        </div>\n'
            html_content += '    </li>\n'
        html_content += '</ul>\n</div>\n'
        logging.debug(f'生成了 section: {key}')

    html_content += '''
    <script>
        showSection('ubuntu_all');
    </script>
</body>
</html>
'''
    try:
        with open('Source_packages_withVersion.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        logging.info('已生成HTML文件：Source_packages_withVersion.html')
        print('已生成HTML文件：Source_packages_withVersion.html')
    except Exception as e:
        logging.error(f'写入 HTML 文件时发生错误: {e}')
        print(f'写入 HTML 文件时发生错误: {e}')

def extract_upstream_version(version):
    """提取上游版本，即第一个 '-' 前的部分"""
    return version.split('-', 1)[0]

def find_common_packages(package_lists, description_threshold=0.8, description_threshold_no_homepage=0.95):
    distros = list(package_lists.keys())
    distros = [d for d in distros if d not in ['common_packages']]
    common_pkgs_dict = {}

    distro_lower_pkg_name_to_actual_pkg_name = {distro: {} for distro in distros}
    for distro in distros:
        for pkg_name in package_lists[distro].keys():
            distro_lower_pkg_name_to_actual_pkg_name[distro][pkg_name.lower()] = pkg_name

    pkgname_to_packages = {}
    for distro in distros:
        for src_pkg in package_lists[distro].keys():
            pkg_name_lower = src_pkg.lower()
            if pkg_name_lower in pkgname_to_packages:
                pkgname_to_packages[pkg_name_lower][distro] = src_pkg
            else:
                pkgname_to_packages[pkg_name_lower] = {distro: src_pkg}

    common_pkg_names_all = [pkg_name_lower for pkg_name_lower, distros_pkgs in pkgname_to_packages.items() if len(distros_pkgs) == len(distros)]
    logging.info(f"找到 {len(common_pkg_names_all)} 个在所有发行版中具有相同名称的包。")

    num_name_and_version_matching_packages = 0
    for pkg_name_lower in common_pkg_names_all:
        distros_pkgs = pkgname_to_packages[pkg_name_lower]
        upstream_versions = []
        versions_match = True
        for distro in distros:
            src_pkg = distros_pkgs[distro]
            version = package_lists[distro][src_pkg].get('version', '')
            upstream_version = extract_upstream_version(version)
            upstream_versions.append(upstream_version)
        first_version = upstream_versions[0]
        for v in upstream_versions[1:]:
            if v != first_version:
                versions_match = False
                break
        if versions_match:
            pkg_data_all_distros = {}
            for distro in distros:
                src_pkg = distros_pkgs[distro]
                pkg_data = package_lists[distro][src_pkg]
                pkg_data_copy = pkg_data.copy()
                pkg_data_copy['package_name'] = src_pkg  
                pkg_data_all_distros[distro] = pkg_data_copy
            base_distro = distros[0]
            src_pkg_name = distros_pkgs[base_distro]
            common_pkgs_dict[src_pkg_name] = pkg_data_all_distros
            num_name_and_version_matching_packages += 1

    logging.info(f"包名和上游版本一致的包数量：{num_name_and_version_matching_packages}")

    combination_common_pkgs = {}

    desired_combinations = [
        (('Ubuntu-24.04', 'Debian'), 'ubuntu_debian_common'),
        (('Ubuntu-24.04', 'Fedora'), 'ubuntu_fedora_common'),
        (('Ubuntu-24.04', 'openEuler-24.03'), 'ubuntu_openeuler_common'),
        (('Debian', 'Fedora'), 'debian_fedora_common'),
        (('Debian', 'openEuler-24.03'), 'debian_openeuler_common'),
        (('Fedora', 'openEuler-24.03'), 'fedora_openeuler_common'),
        (('Ubuntu-24.04', 'Debian', 'Fedora'), 'ubuntu_debian_fedora_common'),
        (('Ubuntu-24.04', 'Debian', 'Fedora', 'openEuler-24.03'), 'all_common')
    ]

    pkgname_to_distro_pkgs = {}
    for distro in distros:
        for pkg_name in package_lists[distro].keys():
            pkg_name_lower = pkg_name.lower()
            if pkg_name_lower not in pkgname_to_distro_pkgs:
                pkgname_to_distro_pkgs[pkg_name_lower] = {}
            pkgname_to_distro_pkgs[pkg_name_lower][distro] = pkg_name

    for combo, combo_key in desired_combinations:
        logging.info(f"计算组合：{combo}")
        common_pkgs = {}
        for pkg_name_lower, distros_pkgs in pkgname_to_distro_pkgs.items():
            if all(distro in distros_pkgs for distro in combo):
                upstream_versions = []
                versions_match = True
                for distro in combo:
                    pkg_name = distros_pkgs[distro]
                    version = package_lists[distro][pkg_name].get('version', '')
                    upstream_version = extract_upstream_version(version)
                    upstream_versions.append(upstream_version)
                first_version = upstream_versions[0]
                for v in upstream_versions[1:]:
                    if v != first_version:
                        versions_match = False
                        break
                if versions_match:
                    pkg_data_all_distros = {}
                    for distro in combo:
                        pkg_name = distros_pkgs[distro]
                        pkg_data = package_lists[distro][pkg_name]
                        pkg_data_copy = pkg_data.copy()
                        pkg_data_copy['package_name'] = pkg_name
                        pkg_data_all_distros[distro] = pkg_data_copy
                    base_distro = combo[0]
                    pkg_name_base = distros_pkgs[base_distro]
                    common_pkgs[pkg_name_base] = pkg_data_all_distros
        combination_common_pkgs[combo_key] = common_pkgs
        logging.info(f"组合 {combo} 共有包数量：{len(common_pkgs)}")

    return combination_common_pkgs


def main():
    distros = ['Ubuntu-24.04', 'Debian', 'Fedora', 'openEuler-24.03']
    package_lists = {}
    for distro in distros:
        print(f'正在获取 {distro} 的软件包...')
        logging.info(f'正在获取 {distro} 的软件包...')
        packages_dict = get_package_list(distro)
        package_lists[distro] = packages_dict

    combination_common_pkgs = find_common_packages(package_lists, description_threshold=0.8, description_threshold_no_homepage=0.95)

    print(f"1. Ubuntu-24.04 全部软件包 {len(package_lists['Ubuntu-24.04'])} 个")
    print(f"2. Debian12 全部软件包 {len(package_lists['Debian'])} 个")
    print(f"3. Fedora41 全部软件包 {len(package_lists['Fedora'])} 个")
    print(f"4. openEuler-24.03 全部软件包 {len(package_lists['openEuler-24.03'])} 个")
    package_data = {
        'ubuntu_all': package_lists['Ubuntu-24.04'],
        'debian_all': package_lists['Debian'],
        'fedora_all': package_lists['Fedora'],
        'openeuler_all': package_lists['openEuler-24.03'],
    }

    for combo_key, combo_pkgs in combination_common_pkgs.items():
        package_data[combo_key] = combo_pkgs

    logging.debug("Final package_data keys: %s", list(package_data.keys()))
    print("Final package_data keys:", list(package_data.keys()))

    try:
        with open('packages_data_all_distributions.json', 'w', encoding='utf-8') as json_file:
            json.dump(package_data, json_file, ensure_ascii=False, indent=4)
        logging.info('已生成JSON文件：packages_data_all_distributions.json')
        print('已生成JSON文件：packages_data_all_distributions.json')
    except Exception as e:
        logging.error(f'写入 JSON 文件时发生错误: {e}')
        print(f'写入 JSON 文件时发生错误: {e}')

    generate_html(package_data,distros)

if __name__ == '__main__':
    main()
