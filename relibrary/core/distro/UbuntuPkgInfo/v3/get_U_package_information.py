#!/usr/bin/env python3
# get_DU_package_information.py

import json
import subprocess
import os
import shutil
import re
import logging
import uuid
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import pwd
import grp
import stat
import getpass

# 配置日志
logging.basicConfig(
    filename='DU_package_info.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8',
    level=logging.INFO
)

def run_command(command):
    """
    在当前的 WSL 环境中运行命令，并返回输出和错误信息。
    """
    logging.info(f"执行命令: {command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode != 0:
            logging.error(f"运行命令失败: {command} - {result.stderr.strip()}")
            return None, result.stderr.strip()
        return result.stdout.strip(), None
    except Exception as e:
        logging.error(f"运行命令时出错: {command} - {e}")
        return None, str(e)

def load_package_list(json_file, distro):
    """从 JSON 文件中加载指定发行版的包名列表。"""
    distro_key_map = {
        'Ubuntu-24.04': 'ubuntu_all',
        'Debian': 'debian_all',
    }
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        key = distro_key_map.get(distro)
        if key and key in data:
            package_names = sorted(data[key].keys())
            logging.info(f"加载了 {len(package_names)} 个 {distro} 软件包")
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

def create_download_dir(download_dir):
    """创建下载目录，并设置正确的权限和所有者。"""
    os.makedirs(download_dir, exist_ok=True)
    # 设置目录权限为 0755
    os.chmod(download_dir, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    # 设置目录所有者为当前用户
    username = getpass.getuser()
    uid = pwd.getpwnam(username).pw_uid
    gid = grp.getgrnam(username).gr_gid
    os.chown(download_dir, uid, gid)

def download_source_package(package, download_dir):
    """
    下载源码包到指定的下载目录。
    """
    if not package or package.lower() in ['name', '(none)']:
        logging.warning(f"跳过无效的软件包名: {package}")
        return False

    # 创建目录
    create_download_dir(download_dir)

    # 下载源码包
    download_command = f'cd "{download_dir}" && apt-get source {package}'
    stdout, stderr = run_command(download_command)
    if stdout is not None:
        # 检查是否下载了 .dsc 文件
        dsc_files = [f for f in os.listdir(download_dir) if f.endswith('.dsc')]
        if dsc_files:
            logging.info(f"下载成功: {package} 下载文件: {dsc_files}")
            return True
        else:
            logging.warning(f"未找到 .dsc 文件，可能下载失败: {package} - {stderr}")
            return False
    else:
        logging.error(f"下载源码包失败: {package} - {stderr}")
        return False

def parse_dsc_file(dsc_path):
    """解析 .dsc 文件获取版本、上游项目等信息。"""
    import re  # 确保导入正则表达式模块

    package_info = {
        'name': '未知',
        'binary': '未知',
        'version': '未知',
        'upstream_version': '未知',  # 添加 upstream_version 字段
        'homepage': '未知',
        'standards_version': '未知',
    }

    try:
        with open(dsc_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('Source:'):
                    package_info['name'] = line.split(':', 1)[1].strip()
                elif line.startswith('Binary:'):
                    package_info['binary'] = line.split(':', 1)[1].strip()
                elif line.startswith('Version:'):
                    version_str = line.split(':', 1)[1].strip()
                    package_info['version'] = version_str
                    # 提取上游版本，即在第一个 '-' 或 '~' 之前的部分
                    upstream_version = re.split(r'[-~]', version_str)[0]
                    package_info['upstream_version'] = upstream_version
                elif line.startswith('Homepage:'):
                    package_info['homepage'] = line.split(':', 1)[1].strip()
                elif line.startswith('Standards-Version:'):
                    package_info['standards_version'] = line.split(':', 1)[1].strip()
    except Exception as e:
        logging.error(f"解析 .dsc 文件时出错: {dsc_path} - {e}")

    return package_info

def parse_patches(patches_dir):
    """解析 debian/patches/ 目录下的补丁信息。"""
    patches_info = []
    if not os.path.isdir(patches_dir):
        return patches_info
    try:
        # 如果存在 series 文件，则按顺序读取补丁
        series_file = os.path.join(patches_dir, 'series')
        if os.path.exists(series_file):
            with open(series_file, 'r', encoding='utf-8') as f:
                patch_files = [line.strip() for line in f if line.strip()]
        else:
            # 否则，列出所有补丁文件
            patch_files = [f for f in os.listdir(patches_dir) if f.endswith('.patch') or f.endswith('.diff')]

        for patch_file in patch_files:
            patch_path = os.path.join(patches_dir, patch_file)
            name = patch_file
            provider = "未提供"
            date = "未提供"
            description = "无描述"
            try:
                with open(patch_path, 'r', encoding='utf-8', errors='replace') as f:
                    for line in f:
                        if line.startswith('From:'):
                            provider = line[len('From:'):].strip()
                        elif line.startswith('Date:'):
                            date = line[len('Date:'):].strip()
                        elif line.startswith('Subject:'):
                            description = line[len('Subject:'):].strip()
                        if provider != "未提供" and date != "未提供" and description != "无描述":
                            break
            except Exception as e:
                logging.error(f"读取补丁文件 {patch_path} 时出错: {e}")
            patches_info.append({
                'name': name,
                'provider': provider,
                'date': date,
                'description': description
            })
    except Exception as e:
        logging.error(f"解析补丁目录 {patches_dir} 时出错: {e}")
    return patches_info

def get_run_dependencies(package):
    """使用 apt-cache depends 命令获取运行依赖。"""
    command = f'apt-cache depends {package}'
    stdout, stderr = run_command(command)
    run_deps = []
    if stdout is not None:
        lines = stdout.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('Depends:'):
                dep = line[len('Depends:'):].strip()
                # 处理可能的格式，如 "<python3:any>"
                dep = dep.strip('<>').split(':')[0]
                run_deps.append(dep)
        return run_deps
    else:
        logging.error(f"获取运行依赖失败: {package} - {stderr}")
        return []

def get_source_info(package, source_dir):
    """获取源码包的详细信息。"""
    try:
        logging.info(f"下载路径: {source_dir} for package: {package}")

        # 找到 .dsc 文件
        dsc_files = [f for f in os.listdir(source_dir) if f.endswith('.dsc')]
        if not dsc_files:
            logging.error(f"未找到 .dsc 文件: {source_dir} for package: {package}")
            return {}
        dsc_path = os.path.join(source_dir, dsc_files[0])
        logging.info(f"使用的 .dsc 文件: {dsc_path} for package: {package}")

        # 解析 .dsc 文件
        package_info = parse_dsc_file(dsc_path)

        # 找到源码目录（包含 debian/ 目录的目录）
        subdirs = [d for d in os.listdir(source_dir) if os.path.isdir(os.path.join(source_dir, d))]
        source_subdir = None
        for d in subdirs:
            if os.path.isdir(os.path.join(source_dir, d, 'debian')):
                source_subdir = d
                break
        if not source_subdir:
            logging.error(f"未找到包含 debian/ 目录的源码目录: {source_dir} for package: {package}")
            return {}
        source_path = os.path.join(source_dir, source_subdir)
        logging.info(f"使用的源码目录: {source_path} for package: {package}")

        # 获取构建依赖（仍然从 control 文件中获取）
        control_path = os.path.join(source_path, 'debian', 'control')
        build_deps = []
        try:
            with open(control_path, 'r', encoding='utf-8') as f:
                content = f.read()
            paragraphs = content.strip().split('\n\n')
            # 解析源包信息
            source_paragraph = paragraphs[0]
            fields = parse_control_fields(source_paragraph)
            if 'Build-Depends' in fields:
                build_deps_raw = fields['Build-Depends']
                build_deps = [dep.strip().split(' ')[0] for dep in build_deps_raw.split(',')]
        except Exception as e:
            logging.error(f"解析 control 文件时出错: {control_path} - {e}")

        # 获取运行依赖（使用 apt-cache depends 命令）
        run_deps = get_run_dependencies(package)

        # 解析补丁信息
        patches_dir = os.path.join(source_path, 'debian', 'patches')
        patches = parse_patches(patches_dir)

        # 组装信息
        source_info = {
            'name': package_info.get('name', '未知'),
            'version': package_info.get('version', '未知'),
            '构建依赖': build_deps,
            '运行依赖': run_deps,
            '上游项目': package_info.get('homepage', '未知'),
            '上游版本': package_info.get('upstream_version', '未知'),
            'patches': patches
        }

        return source_info
    except Exception as e:
        logging.error(f"获取源码信息时出错: {package} - {e}")
        return {}

def parse_control_fields(paragraph):
    """辅助函数，解析 control 文件的字段，处理多行字段。"""
    fields = {}
    current_field = None
    current_value = ''
    lines = paragraph.strip().split('\n')
    for line in lines:
        if not line.strip():
            continue
        if re.match(r'^\S+:', line):
            if current_field:
                fields[current_field] = current_value.strip()
            parts = line.split(':', 1)
            current_field = parts[0]
            current_value = parts[1].strip()
        elif line.startswith(' '):
            current_value += ' ' + line.strip()
        else:
            continue
    if current_field:
        fields[current_field] = current_value.strip()
    return fields

def process_package(package):
    """处理单个软件包，返回其信息。"""
    try:
        download_dir = os.path.join('/tmp', f'downloads_{uuid.uuid4().hex}')
        logging.info(f"为包 {package} 生成下载目录: {download_dir}")
        success = download_source_package(package, download_dir)
        if not success:
            logging.warning(f"跳过下载失败的软件包: {package}")
            return None
        # 获取源码信息
        source_info = get_source_info(package, download_dir)
        # 删除下载目录
        shutil.rmtree(download_dir)
        return source_info
    except Exception as e:
        logging.error(f"处理包 {package} 时出错: {e}")
        return None

def main():
    json_input_file = 'packages_data_all_distributions.json'
    output_json_file = 'Ubuntu_packages_info.json'
    distributions = ['Ubuntu-24.04']  # 只处理 Ubuntu-24.04 发行版

    DU_packages_info = {}
    for distro in distributions:
        DU_packages_info[distro] = {}
        package_list = load_package_list(json_input_file, distro)
        if not package_list:
            continue

        # 在程序开始时执行一次 sudo apt-get update
        update_command = f'sudo apt-get update'
        logging.info(f"更新命令: {update_command}")
        stdout, stderr = run_command(update_command)
        if stdout is None:
            logging.error(f"更新软件包列表失败 - {stderr}")
            print("Error: 更新软件包列表失败")
            return

        # 测试时只处理前 10 个包，实际运行时请注释掉下一行
        # package_list = package_list[:10]

        max_workers = 4  # 您可以根据实际情况调整
        failed_packages = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_package, pkg): pkg for pkg in package_list}
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"处理 {distro} 软件包"):
                pkg_name = futures[future]
                try:
                    package_info = future.result()
                    if package_info:
                        # 添加到最终数据结构
                        DU_packages_info[distro][package_info['name']] = package_info
                except Exception as e:
                    logging.error(f"处理软件包 {pkg_name} 时出错: {e}")
                    failed_packages.append(pkg_name)  # 记录失败的软件包
                    continue

        if failed_packages:
            logging.warning(f"以下软件包处理失败：{failed_packages}")

    try:
        with open(output_json_file, 'w', encoding='utf-8') as f:
            json.dump(DU_packages_info, f, ensure_ascii=False, indent=4)
        logging.info(f"已生成 JSON 文件：{output_json_file}")
        print(f"已生成 JSON 文件：{output_json_file}")
    except Exception as e:
        logging.error(f"写入 JSON 文件时出错: {e}")
        print(f"Error: 写入 JSON 文件时出错: {e}")

if __name__ == '__main__':
    main()
