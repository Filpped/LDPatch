#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

def load_package_data(json_file):
    """加载包含Debian和Fedora软件包信息的JSON文件"""
    try:
        with open(json_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"错误：无法加载JSON文件 - {e}")
        sys.exit(1)

def download_fedora_source(package_name, download_dir="./sources"):
    """下载Fedora软件包的源代码并使用rpm -ivh安装到标准rpmbuild目录"""
    try:
        # 创建下载目录
        os.makedirs(download_dir, exist_ok=True)
        
        # 确保dnf-plugins-core和rpm-build已安装
        print("检查所需工具...")
        subprocess.run(["dnf", "install", "-y", "dnf-plugins-core", "rpm-build", "rpmdevtools"], check=True)
        
        # 确保rpmbuild目录结构存在
        home_dir = str(Path.home())
        rpmbuild_dir = os.path.join(home_dir, "rpmbuild")
        if not os.path.exists(rpmbuild_dir):
            print("初始化rpmbuild目录结构...")
            subprocess.run(["rpmdev-setuptree"], check=True)
        
        # 下载源码包
        print(f"下载 {package_name} 的源码包...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # 使用dnf download --source下载源码包到临时目录
            subprocess.run(["dnf", "download", "--source", package_name], 
                          cwd=temp_dir, check=True)
            
            # 查找下载的SRPM文件
            srpm_files = [f for f in os.listdir(temp_dir) if f.endswith(".src.rpm")]
            
            if not srpm_files:
                print(f"警告：未找到 {package_name} 的源码包")
                return False
            
            srpm_path = os.path.join(temp_dir, srpm_files[0])
            
            # 创建包专用目录并保存SRPM
            package_dir = os.path.join(download_dir, package_name)
            os.makedirs(package_dir, exist_ok=True)
            
            # 复制SRPM到目标目录
            dest_srpm_path = os.path.join(package_dir, srpm_files[0])
            shutil.copy2(srpm_path, dest_srpm_path)
            
            # 使用rpm -ivh安装SRPM
            print(f"安装 {srpm_files[0]} 源码包到rpmbuild目录...")
            subprocess.run(["rpm", "-ivh", dest_srpm_path], check=True)
            
            # 找出spec文件路径
            spec_dir = os.path.join(rpmbuild_dir, "SPECS")
            spec_files = [f for f in os.listdir(spec_dir) if f.endswith(".spec") and package_name.lower() in f.lower()]
            
            if spec_files:
                spec_path = os.path.join(spec_dir, spec_files[0])
                print(f"spec文件位置: {spec_path}")
                
                # 创建一个软链接到package_dir目录
                spec_link = os.path.join(package_dir, "spec_file_link.spec")
                if os.path.exists(spec_link):
                    os.remove(spec_link)
                os.symlink(spec_path, spec_link)
                
                print(f"已在 {package_dir} 创建spec文件的软链接")
            else:
                print(f"警告：未找到 {package_name} 的spec文件")
            
            print(f"成功下载 {package_name} 的源码包，源码文件位于 {rpmbuild_dir} 目录")
            return True
    
    except subprocess.CalledProcessError as e:
        print(f"错误：下载或安装 {package_name} 时出错 - {e}")
        return False

def main():
    if os.geteuid() != 0:
        print("错误：此脚本需要管理员权限运行。请使用sudo运行。")
        sys.exit(1)
        
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 加载软件包数据，默认JSON文件位于同一目录
    json_file = os.path.join(script_dir, "debian_fedora_packages.json")
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    
    print(f"加载软件包数据：{json_file}")
    packages_data = load_package_data(json_file)
    
    # 下载目录，默认在脚本所在目录下
    download_dir = os.path.join(script_dir, "fedora_sources")
    if len(sys.argv) > 2:
        download_dir = sys.argv[2]
    
    # 创建下载目录
    os.makedirs(download_dir, exist_ok=True)
    
    # 获取所有Fedora软件包
    fedora_packages = []
    for package, data in packages_data.get("debian_fedora_common", {}).items():
        if "Fedora" in data and "package_name" in data["Fedora"]:
            fedora_packages.append(data["Fedora"]["package_name"])
    
    print(f"找到 {len(fedora_packages)} 个Fedora软件包")
    
    # 配置Fedora源码仓库
    print("启用Fedora源码仓库...")
    try:
        # 确保已启用源码仓库
        subprocess.run(["dnf", "config-manager", "--set-enabled", "*-source"], 
                       stdout=subprocess.PIPE, 
                       stderr=subprocess.PIPE)
        
        # 更新源
        subprocess.run(["dnf", "update", "-y"], check=True)
    except Exception as e:
        print(f"警告：无法启用源码仓库 - {e}")
    
    # 下载和解压每个包
    successful = 0
    failed = 0
    
    # 提示用户rpmbuild目录位置
    rpmbuild_dir = os.path.join(str(Path.home()), "rpmbuild")
    print(f"\n源码将被安装到标准rpmbuild目录: {rpmbuild_dir}")
    print(f"SPECS目录位置: {os.path.join(rpmbuild_dir, 'SPECS')}")
    print(f"SOURCES目录位置: {os.path.join(rpmbuild_dir, 'SOURCES')}")
    
    for package in fedora_packages:
        print(f"\n正在处理 {package}...")
        if download_fedora_source(package, download_dir):
            successful += 1
        else:
            failed += 1
    
    print(f"\n下载完成：成功 {successful} 个，失败 {failed} 个")
    print(f"SRPM文件已保存在 {os.path.abspath(download_dir)} 目录下的各个软件包子目录中")
    print(f"源代码和spec文件已安装到 {rpmbuild_dir} 目录")
    print(f"- SPECS目录: {os.path.join(rpmbuild_dir, 'SPECS')} (包含.spec文件)")
    print(f"- SOURCES目录: {os.path.join(rpmbuild_dir, 'SOURCES')} (包含源码包)")
    print(f"- BUILD目录: {os.path.join(rpmbuild_dir, 'BUILD')} (构建时使用)")

if __name__ == "__main__":
    main() 