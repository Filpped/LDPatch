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

logging.basicConfig(
    filename='DU_package_info.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8',
    level=logging.INFO
)

def run_command(command):
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
            return None, result.stderr.strip()
        return result.stdout.strip(), None
    except Exception as e:
        return None, str(e)

def load_package_list(json_file, distro):
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
            return package_names
        else:
            return []
    except Exception as e:
        return []

def create_download_dir(download_dir):
    os.makedirs(download_dir, exist_ok=True)
    os.chmod(download_dir, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    username = getpass.getuser()
    uid = pwd.getpwnam(username).pw_uid
    gid = grp.getgrnam(username).gr_gid
    os.chown(download_dir, uid, gid)

def download_source_package(package, download_dir):

    if not package or package.lower() in ['name', '(none)']:
        return False

    create_download_dir(download_dir)

    download_command = f'cd "{download_dir}" && apt-get source {package}'
    stdout, stderr = run_command(download_command)
    if stdout is not None:
        dsc_files = [f for f in os.listdir(download_dir) if f.endswith('.dsc')]
        if dsc_files:
            return True
        else:
            return False
    else:
        return False

def parse_dsc_file(dsc_path):
    import re  
    package_info = {
        'name': 'UNKNOWN',
        'binary': 'UNKNOWN',
        'version': 'UNKNOWN',
        'upstream_version': 'UNKNOWN',  
        'homepage': 'UNKNOWN',
        'standards_version': 'UNKNOWN',
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
                    upstream_version = re.split(r'[-~]', version_str)[0]
                    package_info['upstream_version'] = upstream_version
                elif line.startswith('Homepage:'):
                    package_info['homepage'] = line.split(':', 1)[1].strip()
                elif line.startswith('Standards-Version:'):
                    package_info['standards_version'] = line.split(':', 1)[1].strip()
    except Exception as e:
        logging.error("error")

    return package_info

def parse_patches(patches_dir):
    patches_info = []
    if not os.path.isdir(patches_dir):
        return patches_info
    try:
        series_file = os.path.join(patches_dir, 'series')
        if os.path.exists(series_file):
            with open(series_file, 'r', encoding='utf-8') as f:
                patch_files = [line.strip() for line in f if line.strip()]
        else:
            patch_files = [f for f in os.listdir(patches_dir) if f.endswith('.patch') or f.endswith('.diff')]

        for patch_file in patch_files:
            patch_path = os.path.join(patches_dir, patch_file)
            name = patch_file
            provider = "UNKNOWN"
            date = "UNKNOWN"
            description = "UNKNOWN"
            try:
                with open(patch_path, 'r', encoding='utf-8', errors='replace') as f:
                    for line in f:
                        if line.startswith('From:'):
                            provider = line[len('From:'):].strip()
                        elif line.startswith('Date:'):
                            date = line[len('Date:'):].strip()
                        elif line.startswith('Subject:'):
                            description = line[len('Subject:'):].strip()
                        if provider != "UNKNOWN" and date != "UNKNOWN" and description != "UNKNOWN":
                            break
            except Exception as e:
                logging.error("ERROR")
            patches_info.append({
                'name': name,
                'provider': provider,
                'date': date,
                'description': description
            })
    except Exception as e:
        logging.error("ERROR")
    return patches_info

def get_run_dependencies(package):
    command = f'apt-cache depends {package}'
    stdout, stderr = run_command(command)
    run_deps = []
    if stdout is not None:
        lines = stdout.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('Depends:'):
                dep = line[len('Depends:'):].strip()
                dep = dep.strip('<>').split(':')[0]
                run_deps.append(dep)
        return run_deps
    else:
        return []

def get_source_info(package, source_dir):
    try:
        dsc_files = [f for f in os.listdir(source_dir) if f.endswith('.dsc')]
        if not dsc_files:
            return {}
        dsc_path = os.path.join(source_dir, dsc_files[0])
        package_info = parse_dsc_file(dsc_path)
        subdirs = [d for d in os.listdir(source_dir) if os.path.isdir(os.path.join(source_dir, d))]
        source_subdir = None
        for d in subdirs:
            if os.path.isdir(os.path.join(source_dir, d, 'debian')):
                source_subdir = d
                break
        if not source_subdir:
            return {}
        source_path = os.path.join(source_dir, source_subdir)

        control_path = os.path.join(source_path, 'debian', 'control')
        build_deps = []
        try:
            with open(control_path, 'r', encoding='utf-8') as f:
                content = f.read()
            paragraphs = content.strip().split('\n\n')
            source_paragraph = paragraphs[0]
            fields = parse_control_fields(source_paragraph)
            if 'Build-Depends' in fields:
                build_deps_raw = fields['Build-Depends']
                build_deps = [dep.strip().split(' ')[0] for dep in build_deps_raw.split(',')]
        except Exception as e:
            logging.error("ERROR")

        run_deps = get_run_dependencies(package)

        patches_dir = os.path.join(source_path, 'debian', 'patches')
        patches = parse_patches(patches_dir)

        source_info = {
            'name': package_info.get('name', 'UNKNOWN'),
            'version': package_info.get('version', 'UNKNOWN'),
            'Build dependencies': build_deps,
            'Runtime dependencies': run_deps,
            'Upstream': package_info.get('homepage', 'UNKNOWN'),
            'UpstreamVersion': package_info.get('upstream_version', 'UNKNOWN'),
            'patches': patches
        }

        return source_info
    except Exception as e:
        return {}

def parse_control_fields(paragraph):
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
    try:
        download_dir = os.path.join('/tmp', f'downloads_{uuid.uuid4().hex}')
        success = download_source_package(package, download_dir)
        if not success:
            return None
        source_info = get_source_info(package, download_dir)
        shutil.rmtree(download_dir)
        return source_info
    except Exception as e:
        return None

def main():
    json_input_file = 'packages_data_all_distributions.json'
    output_json_file = 'Ubuntu_packages_info.json'
    distributions = ['Ubuntu-24.04']  

    DU_packages_info = {}
    for distro in distributions:
        DU_packages_info[distro] = {}
        package_list = load_package_list(json_input_file, distro)
        if not package_list:
            continue

        update_command = f'sudo apt-get update'
        stdout, stderr = run_command(update_command)
        if stdout is None:
            return
        max_workers = 4  
        failed_packages = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_package, pkg): pkg for pkg in package_list}
            for future in tqdm(as_completed(futures), total=len(futures), desc=f" {distro}"):
                pkg_name = futures[future]
                try:
                    package_info = future.result()
                    if package_info:
                        DU_packages_info[distro][package_info['name']] = package_info
                except Exception as e:
                    failed_packages.append(pkg_name)  
                    continue

        if failed_packages:
            logging.warning("UNKNOWN")

    try:
        with open(output_json_file, 'w', encoding='utf-8') as f:
            json.dump(DU_packages_info, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error("ERROR")

if __name__ == '__main__':
    main()
