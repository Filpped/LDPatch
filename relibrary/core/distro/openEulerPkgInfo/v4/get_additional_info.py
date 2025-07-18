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

# 配置日志记录
logging.basicConfig(
    filename='additional_package_info.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8',
    level=logging.DEBUG
)
failed_packages = []  # 记录下载失败的软件包列表
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

def load_package_list_from_file(package_file):
    """
    从文件中加载包名列表。
    """
    try:
        with open(package_file, 'r', encoding='utf-8') as f:
            packages = [line.strip() for line in f if line.strip()]
        logging.info(f"从文件加载了 {len(packages)} 个软件包")
        print(f"从文件加载了 {len(packages)} 个软件包")
        return packages
    except Exception as e:
        logging.error(f"加载包文件时出错: {e}")
        print(f"Error: 加载包文件时出错: {e}")
        return []

def download_source_package(package_name, download_dir):
    """下载指定软件包的源代码包"""
    os.makedirs(download_dir, exist_ok=True)
    command = f"dnf download --source --destdir={download_dir} {package_name} -y"
    logging.info(f"下载源代码包: {package_name}")
    result = run_command(command)
    # 检查下载目录中是否存在 SRPM 文件
    srpm_pattern = os.path.join(download_dir, f"{package_name}-*.src.rpm")
    srpm_files = glob.glob(srpm_pattern)
    if srpm_files:
        logging.info(f"下载成功: {package_name}")
        return srpm_files[0]  # 返回找到的 SRPM 文件路径
    else:
        logging.warning(f"下载失败或未找到 SRPM: {package_name}")
        return None

def extract_package_details_from_srpm(srpm_path):
    """
    从 SRPM 文件名中提取包名、版本号和发布号。
    例如：python-mido-1.2.9-21.fc41.src.rpm -> ('python-mido', '1.2.9', '21.fc41')
    """
    srpm_filename = os.path.basename(srpm_path)
    if srpm_filename.endswith(".src.rpm"):
        base_name = srpm_filename[:-8]  # 去掉 ".src.rpm"
        match = re.match(r'^(.+)-([0-9][^-]*)-([^-]+)$', base_name)
        if match:
            name, version, release = match.groups()
            return name, version, release
    return None, None, None


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

def parse_spec_content(spec_content):
    """解析 .spec 文件内容，提取依赖项和补丁信息"""
    build_dependencies = []
    runtime_dependencies = []
    homepage = "未知"

    # 提取 BuildRequires 和 Requires
    build_requires = re.findall(r'^BuildRequires:\s+(.+)$', spec_content, re.MULTILINE)
    requires = re.findall(r'^Requires:\s+(.+)$', spec_content, re.MULTILINE)

    for req in build_requires:
        deps = req.split(',')
        for dep in deps:
            build_dependencies.append(dep.strip())

    for req in requires:
        deps = req.split(',')
        for dep in deps:
            runtime_dependencies.append(dep.strip())

    # 提取 URL 或 Homepage
    homepage_match = re.search(r'^(?:URL|Url|Homepage):\s+(.+)$', spec_content, re.MULTILINE)
    if homepage_match:
        homepage = homepage_match.group(1).strip()

    return {
        '构建依赖': build_dependencies,
        '运行依赖': runtime_dependencies,
        '上游项目': homepage
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
def extract_package_name_from_srpm(srpm_path):
    """
    从 SRPM 文件名中提取包名、版本和 release。
    例如：python-mido-1.2.9-21.fc41.src.rpm -> {'name': 'python-mido', 'version': '1.2.9', 'release': '21.fc41'}
    """
    srpm_filename = os.path.basename(srpm_path)
    if srpm_filename.endswith(".src.rpm"):
        base_name = srpm_filename[:-8]  # 去掉 ".src.rpm"
        match = re.match(r'^(.+)-([\d.]+)-(.+)$', base_name)
        if match:
            return {
                'name': match.group(1),
                'version': match.group(2),
                'release': match.group(3)
            }
    return {
        'name': srpm_filename,
        'version': "未知",
        'release': "未知"
    }

def process_package(package_name):
    """处理单个软件包，返回包信息字典或 None"""
    try:
        logging.info(f"处理软件包: {package_name}")

        # 生成唯一的下载目录
        download_dir = os.path.join(download_base_dir, f"downloads_{uuid.uuid4().hex}")
        srpm_path = download_source_package(package_name, download_dir)
        if not srpm_path:
            logging.warning(f"跳过下载失败的软件包: {package_name}")
            return None

        # 从 SRPM 文件名中提取完整包信息
        full_package_info = extract_package_name_from_srpm(srpm_path)
        logging.info(f"提取到完整包信息: {full_package_info}")

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

        # 查找补丁文件
        patches = find_patches(spec_content, extract_dir)

        # 提取上游项目版本（基于版本号）
        version_full = full_package_info['version']
        upstream_version = re.split(r'[-~]', version_full)[0]

        # 组织数据
        package_info = {
            'name': full_package_info['name'],                     # 软件包名
            'version': version_full,                              # 完整版本号
            'release': full_package_info['release'],              # release 去除分发信息
            '构建依赖': spec_info['构建依赖'],                      # 构建依赖
            '运行依赖': spec_info['运行依赖'],                      # 运行依赖
            '上游项目': spec_info.get('上游项目', '未知'),          # 上游项目地址
            '上游项目版本': upstream_version,                      # 上游项目版本
            'patches': patches                                    # 补丁信息
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
    package_file = 'addition.txt'
    output_json_file = 'additional_packages_info.json'
    user = os.getenv('USER') or 'penny'
    global download_base_dir
    download_base_dir = f"/home/{user}/downloads"

    FO_packages_info = {}
    print("脚本开始执行")
    logging.info("脚本开始执行")

    packages = load_package_list_from_file(package_file)

    if not packages:
        print("软件包列表为空")
        return

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        futures = {executor.submit(process_package, pkg): pkg for pkg in packages}
        for future in tqdm(as_completed(futures), total=len(futures), desc="处理软件包"):
            pkg_name = futures[future]
            try:
                package_info = future.result()
                if package_info:
                    FO_packages_info[package_info['name']] = package_info
            except Exception as e:
                logging.error(f"处理软件包 {pkg_name} 时出错: {e}")
                failed_packages.append(pkg_name)

    save_to_json(FO_packages_info, output_json_file)

    if failed_packages:
        logging.warning(f"以下软件包下载失败: {failed_packages}")
    else:
        logging.info("所有包处理成功！")

    print("脚本执行完毕")

if __name__ == "__main__":
    main()