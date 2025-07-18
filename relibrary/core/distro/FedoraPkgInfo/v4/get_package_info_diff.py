#!/usr/bin/env python3
# get_FO_package_information.py

import os
import subprocess
import json
import logging
import re
from tqdm import tqdm
import uuid
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
import platform 
logging.basicConfig(
    filename='FO_package_info.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8',
    level=logging.DEBUG  
)
failed_packages = []  
def run_command(command):
    """运行命令并返回输出。如果命令失败，返回 None。"""
    try:
        result = subprocess.run(command, capture_output=True, text=True, shell=True, check=True)
        logging.debug(f"命令执行成功: {command}\n输出: {result.stdout.strip()}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"命令执行失败: {command}\n错误信息: {e.stderr.strip()}")
        return None
    except Exception as e:
        logging.error(f"运行命令时出错: {command} - {e}")
        return None

def load_package_list(json_file, distro):
    """
    从 JSON 文件中加载指定发行版的包名列表。
    """
    distro_key_map = {
        'Fedora': 'fedora_all',
    }
    try:
        logging.info(f"加载 JSON 文件: {json_file}")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        key = distro_key_map.get(distro)
        if key and key in data:
            all_pkgs = data[key]
            package_names = [pkg for pkg in all_pkgs.keys() if pkg and pkg.lower() not in ['name', '(none)']]
            filtered_out = len(all_pkgs) - len(package_names)
            if filtered_out > 0:
                logging.info(f"过滤掉了 {filtered_out} 个无效的软件包名")
            logging.info(f"加载了 {len(package_names)} 个 {distro} 软件包")
            logging.debug(f"加载的包名列表: {package_names}")
            print(f"加载了 {len(package_names)} 个 {distro} 软件包")
            return package_names
        else:
            logging.warning(f"在 JSON 文件中未找到键: {key}")
            print(f"Warning: 在 JSON 文件中未找到键: {key}")
            return []
    except Exception as e:
        logging.error(f"加载 JSON 文件时出错: {e}")
        print(f"Error: 加载 JSON 文件时出错: {e}")
        return []

def download_source_package(package_name, download_dir):
    """下载指定软件包的源代码包"""
    os.makedirs(download_dir, exist_ok=True)
    command = f"dnf download --source --destdir={download_dir} {package_name} -y"
    logging.info(f"下载源代码包: {package_name}")
    result = run_command(command)
    srpm_pattern = os.path.join(download_dir, f"{package_name}-*.src.rpm")
    srpm_files = glob.glob(srpm_pattern)
    if srpm_files:
        logging.info(f"下载成功: {package_name}")
        return True
    else:
        logging.warning(f"下载失败或未找到 SRPM: {package_name}")
        return False

def extract_srpm(srpm_path, extract_dir):
    """提取 SRPM 文件并返回 spec 文件路径"""
    os.makedirs(extract_dir, exist_ok=True)
    command = f"rpm2cpio \"{srpm_path}\" | cpio -D \"{extract_dir}\" -idmv"
    logging.info(f"提取 SRPM: {srpm_path}")
    result = run_command(command)
    if result is None:
        logging.error(f"提取 SRPM 失败: {srpm_path}")
        return None
    spec_files = [os.path.join(root, file)
                  for root, dirs, files in os.walk(extract_dir)
                  for file in files if file.endswith('.spec')]
    if spec_files:
        spec_file = spec_files[0]
        logging.info(f"找到 spec 文件: {spec_file}")
        return spec_file
    else:
        logging.warning(f"未找到 spec 文件 in {extract_dir}")
        return None

def parse_defines(spec_content):
    """解析 .spec 文件中的 %define 定义，返回一个字典"""
    defines = {}
    define_pattern = re.compile(r'^\s*%define\s+(\w+)\s+(.+)$', re.MULTILINE)
    for match in define_pattern.findall(spec_content):
        name, value = match
        defines[name] = value.strip()
    return defines

def replace_placeholders(value, defines):
    """替换字符串中的占位符，将其替换为定义的值"""
    placeholder_pattern = re.compile(r'%{(\??)([\w\d_]+)}')

    def replacer(match):
        optional = match.group(1) == '?'
        key = match.group(2)
        if key in defines:
            return defines[key]
        else:
            return '' if optional else match.group(0)  

    return placeholder_pattern.sub(replacer, value)

def parse_spec_content(spec_content):
    """
    解析 .spec 文件内容，提取构建依赖项、运行依赖项、主页和上游版本。
    """
    build_dependencies = []
    runtime_dependencies = []
    homepage = "未知"
    upstream_version = "未知"
    package_name = "未知"
    release = "未知" 

    # 提取 %define 定义
    defines = parse_defines(spec_content)
    logging.debug(f"解析到的 %define 定义: {defines}")

    arch = platform.machine()
    os_name = platform.system().lower()
    os_macro = 'linux' if os_name == 'linux' else os_name
    isa_macro = f'({arch})'

    # 添加标准宏定义
    standard_macros = {
        '_isa': isa_macro,
        '_arch': arch,
        '_os': os_macro,
        'release': release  
    }
    defines.update(standard_macros)

    # 获取 Name
    name_match = re.search(r'^Name:\s+(.+)$', spec_content, re.MULTILINE)
    if name_match:
        package_name = name_match.group(1).strip()
        defines['name'] = package_name

    # 获取 Version
    version_match = re.search(r'^Version:\s+(.+)$', spec_content, re.MULTILINE)
    if version_match:
        version_raw = version_match.group(1).strip()
        defines['version'] = version_raw
        version = replace_placeholders(version_raw, defines)
        defines['version'] = version 
        upstream_version = re.split(r'[-~]', version)[0]
    else:
        version = "未知"
        upstream_version = "未知"

    # 获取 Release
    release_match = re.search(r'^Release:\s+(.+)$', spec_content, re.MULTILINE)
    if release_match:
        release_raw = release_match.group(1).strip()
        # 替换占位符
        release = replace_placeholders(release_raw, defines)
        defines['release'] = release  # 更新 defines 中的 release

    # 获取 BuildRequires 和 Requires
    build_requires = re.findall(r'^BuildRequires:\s+(.+)$', spec_content, re.MULTILINE)
    requires = re.findall(r'^Requires:\s+(.+)$', spec_content, re.MULTILINE)

    logging.debug(f"解析到的 BuildRequires: {build_requires}")
    logging.debug(f"解析到的 Requires: {requires}")

    # 构建依赖
    for req in build_requires:
        deps = req.split(',')
        for dep in deps:
            dep_clean = dep.strip()  # 不去除版本约束
            if dep_clean:
                dep_clean = replace_placeholders(dep_clean, defines)
                build_dependencies.append(dep_clean)

    # 运行依赖
    for req in requires:
        deps = req.split(',')
        for dep in deps:
            dep_clean = dep.strip()  # 不去除版本约束
            if dep_clean:
                dep_clean = replace_placeholders(dep_clean, defines)
                runtime_dependencies.append(dep_clean)

    # 获取 Homepage 或 URL
    homepage_match = re.search(r'^(?:URL|Url|Homepage):\s+(.+)$', spec_content, re.MULTILINE)
    if homepage_match:
        homepage = homepage_match.group(1).strip()

    logging.debug(f"上游项目: {homepage}")
    logging.debug(f"版本: {version}")
    logging.debug(f"上游版本: {upstream_version}")

    return {
        'name': package_name,
        'version': version,
        'release': release,
        '构建依赖': build_dependencies,
        '运行依赖': runtime_dependencies,
        '上游项目': homepage,
        '上游项目版本': upstream_version
    }

def find_patches(spec_content, extract_dir):
    """从 .spec 文件中解析补丁信息并查找补丁文件，包括 Patch 和 Source 字段中的 .patch 文件"""
    defines = parse_defines(spec_content)
    arch = platform.machine()
    os_name = platform.system().lower()
    os_macro = 'linux' if os_name == 'linux' else os_name
    isa_macro = f'({arch})'

    standard_macros = {
        '_isa': isa_macro,
        '_arch': arch,
        '_os': os_macro,
    }
    defines.update(standard_macros)
    name_match = re.search(r'^Name:\s+(.+)$', spec_content, re.MULTILINE)
    if name_match:
        defines['name'] = name_match.group(1).strip()
    version_match = re.search(r'^Version:\s+(.+)$', spec_content, re.MULTILINE)
    if version_match:
        defines['version'] = replace_placeholders(version_match.group(1).strip(), defines)

    patches_info = []

    patch_pattern = re.compile(r'^(?:#\s*(?P<desc>.*?)\s*\n)?(Patch\d*|Source\d*):\s+(?P<patch>.+)', re.MULTILINE)
    matches = patch_pattern.findall(spec_content)

    logging.info(f"找到 {len(matches)} 个补丁文件")

    for desc, tag, patch in matches:
        patch = patch.strip()
        description = desc.strip() if desc else "无描述"

        patch_full = replace_placeholders(patch, defines)

        if patch_full.endswith(('.patch', '.diff', '.patch.gz', '.diff.gz', '.patch.bz2', '.diff.bz2', '.patch.xz', '.diff.xz')):

            patch_name = os.path.basename(patch_full)

            patch_path = os.path.join(extract_dir, patch_name)
            if not os.path.exists(patch_path):
                logging.warning(f"补丁文件未找到: {patch_name} in {extract_dir}")
                provider_info = "未提供"
                date_info = "未提供"
            else:
                try:
                    provider_info = "未提供"
                    date_info = "未提供"
                    description_info = description 
                    with open(patch_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith('From:'):
                                provider_info = line[5:].strip()
                            elif line.startswith('Date:'):
                                date_info = line[5:].strip()
                            elif line.startswith('Subject:'):
                                description_info = line[8:].strip()
                            if provider_info != "未提供" and date_info != "未提供" and description_info != "无描述":
                                break
                    logging.info(f"补丁文件信息: {patch_name}, Provider: {provider_info}, Date: {date_info}, Description: {description_info}")
                except Exception as e:
                    logging.error(f"读取补丁文件时出错: {patch_path} - {e}")
                    provider_info = "未提供"
                    date_info = "未提供"
                    description_info = description

            patches_info.append({
                'name': patch_name,
                'provider': provider_info,
                'date': date_info,
                'description': description_info
            })

    return patches_info

def save_to_json(data, output_file):
    """将数据保存到 JSON 文件"""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logging.info(f"已生成 JSON 文件：{output_file}")
        print(f"已生成 JSON 文件：{output_file}")
    except Exception as e:
        logging.error(f"写入 JSON 文件时出错: {e}")
        print(f"Error: 写入 JSON 文件时出错: {e}")

def ensure_tools_installed():
    """确保必要的工具已安装"""
    tools = ['rpm2cpio', 'cpio', 'dnf-plugins-core']
    for tool in tools:
        check_command = f"which {tool}"
        tool_path = run_command(check_command)
        if not tool_path:
            logging.info(f"{tool} 未安装，正在安装...")
            install_command = f"sudo dnf install -y {tool}"
            install_result = run_command(install_command)
            if install_result is not None:
                logging.info(f"{tool} 安装成功。")
            else:
                logging.error(f"{tool} 安装失败。请手动安装。")

def process_package(package_name):
    """处理单个软件包，返回包信息字典或 None"""
    try:
        logging.info(f"处理软件包: {package_name}")

        download_dir = os.path.join(download_base_dir, f"downloads_{uuid.uuid4().hex}")
        logging.debug(f"创建下载目录: {download_dir}")

        success = download_source_package(package_name, download_dir)
        if not success:
            logging.warning(f"跳过下载失败的软件包: {package_name}")
            return None

        srpm_pattern = os.path.join(download_dir, f"{package_name}-*.src.rpm")
        srpm_files = glob.glob(srpm_pattern)
        if not srpm_files:
            logging.warning(f"未找到 SRPM 文件: {srpm_pattern}")
            return None
        srpm_path = srpm_files[0] 
        logging.info(f"找到 SRPM 文件: {srpm_path}")
        srpm_filename = os.path.basename(srpm_path)
        srpm_basename = srpm_filename[:-8] 
        if srpm_basename.startswith(package_name + '-'):
            version_full = srpm_basename[len(package_name)+1:]
            upstream_version = re.split(r'[-~]', version_full)[0]
        else:
            version_full = '未知'

        extract_dir = os.path.join(download_dir, 'extracted')
        spec_file = extract_srpm(srpm_path, extract_dir)
        if not spec_file:
            logging.warning(f"跳过提取失败的软件包: {package_name}")
            return None
        try:
            with open(spec_file, 'r', encoding='utf-8') as f:
                spec_content = f.read()
            logging.debug(f"读取到的 spec 文件内容: {spec_content[:500]}")  
        except Exception as e:
            logging.error(f"读取 spec 文件失败: {spec_file} - {e}")
            return None

        spec_info = parse_spec_content(spec_content)
        logging.debug(f"解析到的 spec 信息: {spec_info}")
        version = spec_info.get('version', '未知')
        release = spec_info.get('release', '未知')

        patches = find_patches(spec_content, extract_dir)
        logging.debug(f"解析到的补丁信息: {patches}")

        package_info = {
            'name': spec_info.get('name', package_name),
            'version': version_full,
            'release': release,
            '构建依赖': spec_info['构建依赖'],
            '运行依赖': spec_info['运行依赖'],
            '上游项目': spec_info['上游项目'],
            '上游项目版本': upstream_version,
            'patches': patches
        }

        logging.info(f"处理完成的软件包信息: {package_info}")

        try:
            subprocess.run(f"rm -rf \"{download_dir}\"", shell=True, check=True)
            logging.debug(f"已删除下载目录: {download_dir}")
        except Exception as e:
            logging.error(f"删除下载目录失败: {download_dir} - {e}")

        return package_info
    except Exception as e:
        logging.error(f"处理软件包 {package_name} 时出错: {e}")
        return None

def main():
    json_input_file = 'packages_data_all_distributions.json'  
    output_json_file = 'FO_packages_info.json'
    user = os.getenv('USER') or 'xxx' 
    global download_base_dir
    download_base_dir = f"/home/{user}/downloads"

    ensure_tools_installed()

    FO_packages_info = {}
    logging.info("脚本开始执行")
    print("脚本开始执行")

    distributions = ['Fedora']  
    for distro in distributions:
        logging.info(f"处理发行版: {distro}")
        print(f"处理发行版: {distro}")

        packages = load_package_list(json_input_file, distro)
        if not packages:
            logging.warning(f"{distro} 的软件包列表为空")
            print(f"Warning: {distro} 的软件包列表为空")
            continue
        logging.info(f"开始处理 {len(packages)} 个 {distro} 软件包")
        max_workers = os.cpu_count() or 4  
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_package, pkg): pkg for pkg in packages}
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"处理 {distro} 软件包"):
                pkg_name = futures[future]
                try:
                    package_info = future.result()
                    if package_info:
                        FO_packages_info[package_info['name']] = package_info
                except Exception as e:
                    logging.error(f"处理软件包 {pkg_name} 时出错: {e}")
                    failed_packages.append(pkg_name)  # 记录失败的软件包
                    continue

    save_to_json(FO_packages_info, output_json_file)

    if failed_packages:
        logging.warning(f"以下软件包下载失败: {failed_packages}")
    else:
        logging.info("所有包处理成功！")

    logging.info("脚本执行完毕")
    print("脚本执行完毕")

if __name__ == "__main__":
    main()

