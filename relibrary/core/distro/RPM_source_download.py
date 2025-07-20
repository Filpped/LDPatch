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
    try:
        with open(json_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        sys.exit(1)

def download_fedora_source(package_name, download_dir="./sources"):
    try:
        os.makedirs(download_dir, exist_ok=True)
        
        subprocess.run(["dnf", "install", "-y", "dnf-plugins-core", "rpm-build", "rpmdevtools"], check=True)
        
        home_dir = str(Path.home())
        rpmbuild_dir = os.path.join(home_dir, "rpmbuild")
        if not os.path.exists(rpmbuild_dir):
            subprocess.run(["rpmdev-setuptree"], check=True)
    
        
        with tempfile.TemporaryDirectory() as temp_dir:
            subprocess.run(["dnf", "download", "--source", package_name], 
                          cwd=temp_dir, check=True)
            
            srpm_files = [f for f in os.listdir(temp_dir) if f.endswith(".src.rpm")]
            
            if not srpm_files:
                return False
            
            srpm_path = os.path.join(temp_dir, srpm_files[0])
            
            package_dir = os.path.join(download_dir, package_name)
            os.makedirs(package_dir, exist_ok=True)
            
            dest_srpm_path = os.path.join(package_dir, srpm_files[0])
            shutil.copy2(srpm_path, dest_srpm_path)
            
            subprocess.run(["rpm", "-ivh", dest_srpm_path], check=True)
            
            spec_dir = os.path.join(rpmbuild_dir, "SPECS")
            spec_files = [f for f in os.listdir(spec_dir) if f.endswith(".spec") and package_name.lower() in f.lower()]
            
            if spec_files:
                spec_path = os.path.join(spec_dir, spec_files[0])
                spec_link = os.path.join(package_dir, "spec_file_link.spec")
                if os.path.exists(spec_link):
                    os.remove(spec_link)
                os.symlink(spec_path, spec_link)
            else:
                print("ERROR")
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
    
    download_dir = os.path.join(script_dir, "fedora_sources")
    if len(sys.argv) > 2:
        download_dir = sys.argv[2]
    
    os.makedirs(download_dir, exist_ok=True)
    
    fedora_packages = []
    for package, data in packages_data.get("debian_fedora_common", {}).items():
        if "Fedora" in data and "package_name" in data["Fedora"]:
            fedora_packages.append(data["Fedora"]["package_name"])

    try:
        subprocess.run(["dnf", "config-manager", "--set-enabled", "*-source"], 
                       stdout=subprocess.PIPE, 
                       stderr=subprocess.PIPE)
        
        subprocess.run(["dnf", "update", "-y"], check=True)
    except Exception as e:
        print("ERROR")
    
    successful = 0
    failed = 0
    
    rpmbuild_dir = os.path.join(str(Path.home()), "rpmbuild")
    for package in fedora_packages:
        if download_fedora_source(package, download_dir):
            successful += 1
        else:
            failed += 1
if __name__ == "__main__":
    main() 