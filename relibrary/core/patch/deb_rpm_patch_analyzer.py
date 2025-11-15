import os
import subprocess
import re

def safe_run(cmd, timeout=None):
    result = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout)
    out = result.stdout
    if isinstance(out, bytes):
        out = out.decode('utf-8', errors='replace')
    return out

def find_debian_patch_dir(package_name, debian_base_dir="/home/penny/packages_info"):
    package_dir = f"{debian_base_dir}/{package_name}"
    find_cmd = f"wsl -d Debian -u penny sh -c \"find '{package_dir}' -type d -path '*/debian/patches' 2>/dev/null || echo 'NOT_FOUND'\""
    output = safe_run(find_cmd).strip()
    potential_dirs = [line for line in output.split('\n') if line.strip() and line != 'NOT_FOUND']
    if not potential_dirs:
        return None, None, False
    patches_dir = potential_dirs[0]
    series_path = f"{patches_dir}/series"
    check_series_cmd = f"wsl -d Debian -u penny sh -c \"if [ -f '{series_path}' ]; then echo 'SERIES_EXISTS'; else echo 'NO_SERIES'; fi\""
    has_series = 'SERIES_EXISTS' in safe_run(check_series_cmd)
    return patches_dir, (series_path if has_series else None), True

def get_debian_patch_names(series_path, patches_dir):
    patch_names = []
    if series_path:
        cat_cmd = f"wsl -d Debian -u penny sh -c \"cat '{series_path}' 2>/dev/null || echo 'ERROR'\""
        output = safe_run(cat_cmd).strip()
        if output and output != 'ERROR':
            for line in output.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patch_names.append(line)
            if patch_names:
                return patch_names
    if patches_dir:
        find_cmd = f"wsl -d Debian -u penny sh -c \"find '{patches_dir}' -type f \\( -name '*.patch' -o -name '*.diff' \\) 2>/dev/null || echo 'NOT_FOUND'\""
        output = safe_run(find_cmd).strip()
        if output and 'NOT_FOUND' not in output:
            for patch_file in output.splitlines():
                if patch_file.startswith(patches_dir):
                    relative_path = patch_file[len(patches_dir):].lstrip('/')
                    patch_names.append(relative_path)
                else:
                    patch_names.append(os.path.basename(patch_file))
    return patch_names

def get_debian_patch_file_content(patch_name, patches_dir):
    patches_dir = patches_dir.replace("\\", "/")
    patch_name = patch_name.replace("\\", "/")
    patch_path = f"{patches_dir}/{patch_name}"
    command_check = f"wsl -d Debian bash -c 'test -f \"{patch_path}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\"'"
    command_cat = f"wsl -d Debian bash -c 'cat \"{patch_path}\"'"
    if "EXISTS" in safe_run(command_check):
        raw = safe_run(command_cat)
        return raw.splitlines()
    return None


def normalize_patch_content(patch_content):
    if isinstance(patch_content, list):
        lines = patch_content
    else:
        lines = patch_content.splitlines()
    normalized_lines = []
    in_hunk = False
    for line in lines:
        if line.startswith('@@ '):
            in_hunk = True
            normalized_lines.append('@@')
            continue
        if not in_hunk:
            continue
        clean_line = line.replace('\r', '').strip()
        if clean_line == '':
            continue
        if clean_line.startswith(('--- ', '+++ ')):
            normalized_lines.append(clean_line)
            continue
        normalized_lines.append(clean_line)
    return normalized_lines

def extract_diff_lines_only(normalized_content):
    diff_lines = []
    for line in normalized_content:
        if re.match(r'^[-+]{3} ', line):
            continue
        if line.startswith('+') or line.startswith('-'):
            content = line[1:].strip()
            if not content:
                continue
            if content in ('-', '+', '--', '++', '===', '====', 'diff', 'index'):
                continue
            if re.fullmatch(r'[-=+]+', content):
                continue
            if content.lstrip().startswith('//'):
                continue
            norm_line = line[0] + re.sub(r'\s+', '', content)
            diff_lines.append(norm_line)
    return diff_lines

def diff_lines_similarity(diff1, diff2):
    set1, set2 = set(diff1), set(diff2)
    if not set1 or not set2:
        return 0
    return len(set1 & set2) / len(set1 | set2)

def compare_patches_by_diff_only(contentA, contentB, threshold=0.8):
    normA = normalize_patch_content(contentA)
    normB = normalize_patch_content(contentB)
    diffA = extract_diff_lines_only(normA)
    diffB = extract_diff_lines_only(normB)
    sim = diff_lines_similarity(diffA, diffB)
    return sim, sim >= threshold

def get_spec_content(package_name, distribution, spec_dir="/home/penny/rpmbuild/SPECS"):
    spec_path = f"{spec_dir}/{package_name}.spec"
    cmd = f"wsl -d {distribution} bash -c 'cat \"{spec_path}\"'"
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=60)
        return res.stdout if res.returncode == 0 and res.stdout.strip() else None
    except Exception:
        return None

from rpm_patch_analyzer import get_patch_info, get_patch_file_content
