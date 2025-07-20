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
    try:
        result = subprocess.run(command, capture_output=True, text=True, shell=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return None
    except Exception as e:
        return None

def load_package_list(json_file, distro):
    distro_key_map = {
        'Fedora': 'fedora_all',
        'openEuler-24.03': 'openeuler_all',
    }
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        key = distro_key_map.get(distro)
        if key and key in data:
            all_pkgs = data[key]
            package_names = [pkg for pkg in all_pkgs.keys() if pkg and pkg.lower() not in ['name', '(none)']]
            filtered_out = len(all_pkgs) - len(package_names)
            return package_names
        else:
            return []
    except Exception as e:
        print("error")
        return []

def download_source_package(package_name, download_dir):
    os.makedirs(download_dir, exist_ok=True)
    command = f"dnf download --source --destdir={download_dir} {package_name} -y"
    result = run_command(command)
    srpm_pattern = os.path.join(download_dir, f"{package_name}-*.src.rpm")
    srpm_files = glob.glob(srpm_pattern)
    if srpm_files:
        return True
    else:
        return False

def extract_srpm(srpm_path, extract_dir):
    os.makedirs(extract_dir, exist_ok=True)
    command = f"rpm2cpio \"{srpm_path}\" | cpio -D \"{extract_dir}\" -idmv"
    result = run_command(command)
    if result is None:
        return None
    spec_files = [os.path.join(root, file)
                  for root, dirs, files in os.walk(extract_dir)
                  for file in files if file.endswith('.spec')]
    if spec_files:
        spec_file = spec_files[0]
        return spec_file
    else:
        return None

def parse_defines(spec_content):
    defines = {}
    define_pattern = re.compile(r'^\s*%define\s+(\w+)\s+(.+)$', re.MULTILINE)
    for match in define_pattern.findall(spec_content):
        name, value = match
        defines[name] = value.strip()
    return defines

def replace_placeholders(value, defines):
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
    build_dependencies = []
    runtime_dependencies = []
    homepage = "UNKNOWN"
    upstream_version = "UNKNOWN"
    package_name = "UNKNOWN"
    release = "UNKNOWN"  

    defines = parse_defines(spec_content)

    arch = platform.machine()
    os_name = platform.system().lower()
    os_macro = 'linux' if os_name == 'linux' else os_name
    isa_macro = f'({arch})'

    standard_macros = {
        '_isa': isa_macro,
        '_arch': arch,
        '_os': os_macro,
        'release': release  
    }
    defines.update(standard_macros)

    name_match = re.search(r'^Name:\s+(.+)$', spec_content, re.MULTILINE)
    if name_match:
        package_name = name_match.group(1).strip()
        defines['name'] = package_name

    version_match = re.search(r'^Version:\s+(.+)$', spec_content, re.MULTILINE)
    if version_match:
        version_raw = version_match.group(1).strip()
        defines['version'] = version_raw
        version = replace_placeholders(version_raw, defines)
        defines['version'] = version 
        upstream_version = re.split(r'[-~]', version)[0]
    else:
        version = "UNKNOWN"
        upstream_version = "UNKNOWN"

    release_match = re.search(r'^Release:\s+(.+)$', spec_content, re.MULTILINE)
    if release_match:
        release_raw = release_match.group(1).strip()
        release = replace_placeholders(release_raw, defines)
        defines['release'] = release  

    build_requires = re.findall(r'^BuildRequires:\s+(.+)$', spec_content, re.MULTILINE)
    requires = re.findall(r'^Requires:\s+(.+)$', spec_content, re.MULTILINE)

    for req in build_requires:
        deps = req.split(',')
        for dep in deps:
            dep_clean = dep.strip() 
            if dep_clean:
                dep_clean = replace_placeholders(dep_clean, defines)
                build_dependencies.append(dep_clean)

    for req in requires:
        deps = req.split(',')
        for dep in deps:
            dep_clean = dep.strip()  
            if dep_clean:
                dep_clean = replace_placeholders(dep_clean, defines)
                runtime_dependencies.append(dep_clean)

    homepage_match = re.search(r'^(?:URL|Url|Homepage):\s+(.+)$', spec_content, re.MULTILINE)
    if homepage_match:
        homepage = homepage_match.group(1).strip()

    return {
        'name': package_name,
        'version': version,
        'release': release,
        'Build dependencies': build_dependencies,
        'Runtime dependencies': runtime_dependencies,
        'Upstream': homepage,
        'UpstreamVersion': upstream_version
    }


def find_patches(spec_content, extract_dir):
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

    for desc, tag, patch in matches:
        patch = patch.strip()
        description = desc.strip() if desc else "none"

        patch_full = replace_placeholders(patch, defines)

        if patch_full.endswith(('.patch', '.diff', '.patch.gz', '.diff.gz', '.patch.bz2', '.diff.bz2', '.patch.xz', '.diff.xz')):
            patch_name = os.path.basename(patch_full)

            patch_path = os.path.join(extract_dir, patch_name)
            if not os.path.exists(patch_path):
                provider_info = "UNKNOWN"
                date_info = "UNKNOWN"
            else:
                try:
                    provider_info = "UNKNOWN"
                    date_info = "UNKNOWN"
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
                            if provider_info != "UNKNOWN" and date_info != "UNKNOWN" and description_info != "UNKNOWN":
                                break
                except Exception as e:
                    provider_info = "UNKNOWN"
                    date_info = "UNKNOWN"
                    description_info = description

            patches_info.append({
                'name': patch_name,
                'provider': provider_info,
                'date': date_info,
                'description': description_info
            })

    return patches_info

def save_to_json(data, output_file):
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error("ERROR")

def ensure_tools_installed():
    tools = ['rpm2cpio', 'cpio', 'dnf-plugins-core']
    for tool in tools:
        check_command = f"which {tool}"
        tool_path = run_command(check_command)
        if not tool_path:
            install_command = f"sudo dnf install -y {tool}"
            install_result = run_command(install_command)

def process_package(package_name):
    try:
        download_dir = os.path.join(download_base_dir, f"downloads_{uuid.uuid4().hex}")
        success = download_source_package(package_name, download_dir)
        if not success:
            return None

        srpm_pattern = os.path.join(download_dir, f"{package_name}-*.src.rpm")
        srpm_files = glob.glob(srpm_pattern)
        if not srpm_files:
            return None
        srpm_path = srpm_files[0]
        logging.info(f"找到 SRPM 文件: {srpm_path}")
        srpm_filename = os.path.basename(srpm_path)
        srpm_basename = srpm_filename[:-8]  
        if srpm_basename.startswith(package_name + '-'):
            version_full = srpm_basename[len(package_name)+1:]
            upstream_version = re.split(r'[-~]', version_full)[0]
        else:
            version_full = 'UNKNOWN'


        extract_dir = os.path.join(download_dir, 'extracted')
        spec_file = extract_srpm(srpm_path, extract_dir)
        if not spec_file:
            return None

        try:
            with open(spec_file, 'r', encoding='utf-8') as f:
                spec_content = f.read()
        except Exception as e:
            return None
        spec_info = parse_spec_content(spec_content)

        release = spec_info.get('release', 'UNKNOWN')

        patches = find_patches(spec_content, extract_dir)

        package_info = {
            'name': spec_info.get('name', package_name),
            'version': version_full,
            'release': release,
            'Build dependencies': spec_info['dependencies'],
            'Runtime dependencies': spec_info['Runtime dependencies'],
            'Upstream': spec_info['Upstream'],
            'UpstreamVersion': upstream_version,
            'patches': patches
        }
        try:
            subprocess.run(f"rm -rf \"{download_dir}\"", shell=True, check=True)
        except Exception as e:
            logging.error("error")

        return package_info
    except Exception as e:
        return None

def main():
    json_input_file = 'packages_data_all_distributions.json'  
    output_json_file = 'FO_packages_info.json'
    user = os.getenv('USER') or 'XXX' 
    global download_base_dir
    download_base_dir = f"/home/{user}/downloads"

    ensure_tools_installed()

    FO_packages_info = {}

    distributions = ['openEuler-24.03']  
    for distro in distributions:

        packages = load_package_list(json_input_file, distro)
        if not packages:
            continue
        max_workers = os.cpu_count() or 4 
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_package, pkg): pkg for pkg in packages}
            for future in tqdm(as_completed(futures), total=len(futures), desc=f" {distro} "):
                pkg_name = futures[future]
                try:
                    package_info = future.result()
                    if package_info:
                        FO_packages_info[package_info['name']] = package_info
                except Exception as e:
                    failed_packages.append(pkg_name)  
                    continue
    save_to_json(FO_packages_info, output_json_file)

if __name__ == "__main__":
    main()


