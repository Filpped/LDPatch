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
import platform  # 导入 platform 模块

# 配置日志记录
logging.basicConfig(
    filename='FO_package_info.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8',
    level=logging.DEBUG  # 设置为 DEBUG 级别，以记录所有日志
)
failed_packages = []  # 记录下载失败的软件包列表
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
        'openEuler-24.03': 'openeuler_all',
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
    # 使用 dnf 代替 yumdownloader
    command = f"dnf download --source --destdir={download_dir} {package_name} -y"
    logging.info(f"下载源代码包: {package_name}")
    result = run_command(command)
    # 检查下载目录中是否存在 SRPM 文件
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
    # 寻找 .spec 文件
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
    # 正则表达式匹配 %{name}、%{?macro} 等宏
    placeholder_pattern = re.compile(r'%{(\??)([\w\d_]+)}')

    def replacer(match):
        optional = match.group(1) == '?'
        key = match.group(2)
        if key in defines:
            return defines[key]
        else:
            return '' if optional else match.group(0)  # 如果是可选宏，未定义则替换为空字符串，否则保持原样

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
    release = "未知"  # 添加 release 字段

    # 提取 %define 定义
    defines = parse_defines(spec_content)
    logging.debug(f"解析到的 %define 定义: {defines}")

    # 获取系统架构和操作系统信息
    arch = platform.machine()
    os_name = platform.system().lower()
    os_macro = 'linux' if os_name == 'linux' else os_name
    isa_macro = f'({arch})'

    # 添加标准宏定义
    standard_macros = {
        '_isa': isa_macro,
        '_arch': arch,
        '_os': os_macro,
        'release': release  # 新增 release 宏
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
        # 先将未替换的版本号加入 defines，以支持在宏中使用 %{version}
        defines['version'] = version_raw
        # 替换占位符
        version = replace_placeholders(version_raw, defines)
        defines['version'] = version  # 更新 defines 中的版本号
        # 提取上游版本，即在第一个 '-' 或 '~' 之前的部分
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
    # 获取系统架构和操作系统信息
    arch = platform.machine()
    os_name = platform.system().lower()
    os_macro = 'linux' if os_name == 'linux' else os_name
    isa_macro = f'({arch})'

    # 添加标准宏定义到 defines
    standard_macros = {
        '_isa': isa_macro,
        '_arch': arch,
        '_os': os_macro,
    }
    defines.update(standard_macros)
    # 确保 'name' 和 'version' 在 defines 中
    name_match = re.search(r'^Name:\s+(.+)$', spec_content, re.MULTILINE)
    if name_match:
        defines['name'] = name_match.group(1).strip()
    version_match = re.search(r'^Version:\s+(.+)$', spec_content, re.MULTILINE)
    if version_match:
        defines['version'] = replace_placeholders(version_match.group(1).strip(), defines)

    patches_info = []

    # 提取 Patch 和 Source 字段中的补丁
    patch_pattern = re.compile(r'^(?:#\s*(?P<desc>.*?)\s*\n)?(Patch\d*|Source\d*):\s+(?P<patch>.+)', re.MULTILINE)
    matches = patch_pattern.findall(spec_content)

    logging.info(f"找到 {len(matches)} 个补丁文件")

    for desc, tag, patch in matches:
        patch = patch.strip()
        description = desc.strip() if desc else "无描述"

        # 替换占位符，包括 package_name 和 version
        patch_full = replace_placeholders(patch, defines)

        # 如果文件名以 .patch 结尾，则认为是补丁
        if patch_full.endswith(('.patch', '.diff', '.patch.gz', '.diff.gz', '.patch.bz2', '.diff.bz2', '.patch.xz', '.diff.xz')):
            # 仅使用补丁文件名，忽略路径前缀
            patch_name = os.path.basename(patch_full)

            # 查找补丁文件路径
            patch_path = os.path.join(extract_dir, patch_name)
            if not os.path.exists(patch_path):
                logging.warning(f"补丁文件未找到: {patch_name} in {extract_dir}")
                provider_info = "未提供"
                date_info = "未提供"
            else:
                # 从补丁文件中提取 'From'、'Date'、'Subject' 信息
                try:
                    provider_info = "未提供"
                    date_info = "未提供"
                    description_info = description  # 默认使用 spec 中的描述
                    with open(patch_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith('From:'):
                                provider_info = line[5:].strip()
                            elif line.startswith('Date:'):
                                date_info = line[5:].strip()
                            elif line.startswith('Subject:'):
                                description_info = line[8:].strip()
                            # 如果已经获取到所有信息，可以提前结束
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

        # 生成唯一的下载目录
        download_dir = os.path.join(download_base_dir, f"downloads_{uuid.uuid4().hex}")
        logging.debug(f"创建下载目录: {download_dir}")

        # 下载源代码包
        success = download_source_package(package_name, download_dir)
        if not success:
            logging.warning(f"跳过下载失败的软件包: {package_name}")
            return None

        # 查找下载的 SRPM 文件
        srpm_pattern = os.path.join(download_dir, f"{package_name}-*.src.rpm")
        srpm_files = glob.glob(srpm_pattern)
        if not srpm_files:
            logging.warning(f"未找到 SRPM 文件: {srpm_pattern}")
            return None
        srpm_path = srpm_files[0]  # 使用第一个匹配的 SRPM 文件
        logging.info(f"找到 SRPM 文件: {srpm_path}")
        # 从 SRPM 文件名中提取完整的版本号
        srpm_filename = os.path.basename(srpm_path)
        # 移除 '.src.rpm' 后缀
        srpm_basename = srpm_filename[:-8]  # 去掉 '.src.rpm'
        # 去掉包名前缀，获取版本信息
        if srpm_basename.startswith(package_name + '-'):
            version_full = srpm_basename[len(package_name)+1:]
            upstream_version = re.split(r'[-~]', version_full)[0]
        else:
            version_full = '未知'


        # 提取 SRPM 文件
        extract_dir = os.path.join(download_dir, 'extracted')
        spec_file = extract_srpm(srpm_path, extract_dir)
        if not spec_file:
            logging.warning(f"跳过提取失败的软件包: {package_name}")
            return None

        # 读取 .spec 文件内容
        try:
            with open(spec_file, 'r', encoding='utf-8') as f:
                spec_content = f.read()
            logging.debug(f"读取到的 spec 文件内容: {spec_content[:500]}")  # 只记录前500字符，避免日志过大
        except Exception as e:
            logging.error(f"读取 spec 文件失败: {spec_file} - {e}")
            return None

        # 解析 .spec 文件内容
        spec_info = parse_spec_content(spec_content)
        logging.debug(f"解析到的 spec 信息: {spec_info}")

        # 获取版本信息
        release = spec_info.get('release', '未知')

        # 查找补丁文件
        patches = find_patches(spec_content, extract_dir)
        logging.debug(f"解析到的补丁信息: {patches}")

        # 组织数据
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

        # 清理下载目录（可选）
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
    json_input_file = 'packages_data_all_distributions.json'  # 确保此文件存在并格式正确
    output_json_file = 'FO_packages_info.json'
    user = os.getenv('USER') or 'penny'  # 获取当前用户名，或者手动指定
    global download_base_dir
    download_base_dir = f"/home/{user}/downloads"

    # 确保必要的工具已安装
    ensure_tools_installed()

    FO_packages_info = {}
    logging.info("脚本开始执行")
    print("脚本开始执行")

    # 加载包列表
    distributions = ['openEuler-24.03']  # 修改为 openEuler-24.03
    for distro in distributions:
        logging.info(f"处理发行版: {distro}")
        print(f"处理发行版: {distro}")

        # 加载包列表
        packages = load_package_list(json_input_file, distro)
        if not packages:
            logging.warning(f"{distro} 的软件包列表为空")
            print(f"Warning: {distro} 的软件包列表为空")
            continue
        logging.info(f"开始处理 {len(packages)} 个 {distro} 软件包")

        # 设置并行处理的线程数，可以根据需要调整
        max_workers = os.cpu_count() or 4  # 使用 CPU 核心数，您也可以根据实际情况调整
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_package, pkg): pkg for pkg in packages}
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"处理 {distro} 软件包"):
                pkg_name = futures[future]
                try:
                    package_info = future.result()
                    if package_info:
                        # 添加到最终数据结构
                        FO_packages_info[package_info['name']] = package_info
                except Exception as e:
                    logging.error(f"处理软件包 {pkg_name} 时出错: {e}")
                    failed_packages.append(pkg_name)  # 记录失败的软件包
                    continue

    # 保存数据到 JSON 文件
    save_to_json(FO_packages_info, output_json_file)

    # 输出所有下载失败的包
    if failed_packages:
        logging.warning(f"以下软件包下载失败: {failed_packages}")
    else:
        logging.info("所有包处理成功！")

    logging.info("脚本执行完毕")
    print("脚本执行完毕")

if __name__ == "__main__":
    main()


