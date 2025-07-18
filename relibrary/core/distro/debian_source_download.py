#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import sys
import shutil

def load_package_data(json_file):
    """加载包含Debian和Fedora软件包信息的JSON文件"""
    try:
        with open(json_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"错误：无法加载JSON文件 - {e}")
        sys.exit(1)

def download_and_extract_debian_source(package_name, base_dir="."):
    """下载Debian软件包的源代码并解压到包名对应的目录"""
    try:
        # 创建包专用目录
        package_dir = os.path.join(base_dir, package_name)
        if os.path.exists(package_dir):
            print(f"目录 {package_dir} 已存在，将清空内容...")
            shutil.rmtree(package_dir)
        
        os.makedirs(package_dir, exist_ok=True)
        
        # 更新apt源列表
        print(f"更新apt源列表...")
        subprocess.run(["apt-get", "update"], check=True)
        
        # 下载源码包并直接解压到包目录
        print(f"下载并解压 {package_name} 的源码包到 {package_dir}...")
        subprocess.run(["apt-get", "source", package_name], 
                       cwd=package_dir, check=True)
        
        # 检查是否成功
        files = os.listdir(package_dir)
        if not files:
            print(f"警告：未找到 {package_name} 的源码包")
            return False
        
        print(f"成功下载并解压 {package_name} 的源码包到 {package_dir}")
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"错误：处理 {package_name} 时出错 - {e}")
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
    
    # 安装源码包所需的工具
    print("安装所需的工具...")
    subprocess.run(["apt-get", "install", "-y", "dpkg-dev"], check=True)
    
    # 启用源码包仓库
    print("启用源码包仓库...")
    try:
        with open("/etc/apt/sources.list", "r") as f:
            sources_content = f.read()
        
        # 检查并添加deb-src条目
        sources_modified = False
        new_sources = []
        for line in sources_content.splitlines():
            new_sources.append(line)
            if line.startswith("deb ") and not line.replace("deb ", "deb-src ") in sources_content:
                new_sources.append(line.replace("deb ", "deb-src "))
                sources_modified = True
        
        if sources_modified:
            with open("/etc/apt/sources.list", "w") as f:
                f.write("\n".join(new_sources))
            
            # 更新源
            subprocess.run(["apt-get", "update"], check=True)
    except Exception as e:
        print(f"警告：无法修改源配置 - {e}")
    
    # 获取所有Debian软件包
    debian_packages = []
    for package, data in packages_data.get("debian_fedora_common", {}).items():
        if "Debian" in data and "package_name" in data["Debian"]:
            debian_packages.append(data["Debian"]["package_name"])
    
    print(f"找到 {len(debian_packages)} 个Debian软件包")
    
    # 下载和解压每个包到各自的目录中
    successful = 0
    failed = 0
    
    for package in debian_packages:
        print(f"\n正在处理 {package}...")
        if download_and_extract_debian_source(package, script_dir):
            successful += 1
        else:
            failed += 1
    
    print(f"\n下载完成：成功 {successful} 个，失败 {failed} 个")
    print(f"源码包已保存在 {script_dir} 下的各个软件包目录中")

if __name__ == "__main__":
    main() 