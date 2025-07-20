#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import sys
import shutil

def load_package_data(json_file):
    try:
        with open(json_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        sys.exit(1)

def download_and_extract_debian_source(package_name, base_dir="."):
    try:
        package_dir = os.path.join(base_dir, package_name)
        if os.path.exists(package_dir):
            shutil.rmtree(package_dir)
        
        os.makedirs(package_dir, exist_ok=True)
        subprocess.run(["apt-get", "update"], check=True)
        
        subprocess.run(["apt-get", "source", package_name], 
                       cwd=package_dir, check=True)
        
        files = os.listdir(package_dir)
        if not files:
            return False
        
        return True
    
    except subprocess.CalledProcessError as e:
        return False

def main():
    if os.geteuid() != 0:
        sys.exit(1)
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    json_file = os.path.join(script_dir, "debian_fedora_packages.json")
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    packages_data = load_package_data(json_file)
    
    subprocess.run(["apt-get", "install", "-y", "dpkg-dev"], check=True)
    
    try:
        with open("/etc/apt/sources.list", "r") as f:
            sources_content = f.read()
        
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
            
            subprocess.run(["apt-get", "update"], check=True)
    except Exception as e:
        print("ERROR")
    
    debian_packages = []
    for package, data in packages_data.get("debian_fedora_common", {}).items():
        if "Debian" in data and "package_name" in data["Debian"]:
            debian_packages.append(data["Debian"]["package_name"])
    successful = 0
    failed = 0
    
    for package in debian_packages:
        if download_and_extract_debian_source(package, script_dir):
            successful += 1
        else:
            failed += 1

if __name__ == "__main__":
    main() 