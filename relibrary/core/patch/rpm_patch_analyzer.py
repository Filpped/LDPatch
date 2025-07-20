import re
import os
import subprocess
import platform
import requests
import hashlib

NORMAL_EXTS = {
    ".c", ".cpp", ".cc", ".h", ".hpp", ".hh", ".py", ".java", ".js", ".rb",
    ".go", ".sh", ".bash", ".pl", ".php", ".html", ".htm", ".css", ".xml",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".txt", ".md", ".rst", ".conf",
    ".in", ".am", ".m4", ".po", ".pot", ".desktop", ".service", ".spec", ".xslt",
    ".make", ".mk", ".ac", ".cmake", ".cfg", ".csv", ".svg",".1"
}

def normalize_patch_filename(filename, normal_exts=NORMAL_EXTS):
    base, ext = os.path.splitext(filename)
    if not ext and base:
        base = re.sub(r'(~|\.bak|\.orig|\.backup)$', '', base)
        filename = base
    elif ext.lower() not in normal_exts:
        while ext and ext.lower() not in normal_exts:
            base, ext = os.path.splitext(base)
        filename = base + ext
    filename = re.sub(r'(~|\.bak|\.orig|\.backup)$', '', filename)
    return filename

def strip_patch_path(file_path, strip_level):
    if not file_path or strip_level == 0:
        return file_path
    parts = file_path.split('/')
    if len(parts) <= strip_level:
        return parts[-1]
    return '/'.join(parts[strip_level:])

def parse_defines(spec_content):
    defines = {}
    define_pattern = re.compile(r'^\s*(%define|%global)\s+(\w+)\s+(.+)$', re.MULTILINE)
    for match in define_pattern.findall(spec_content):
        _, name, value = match
        defines[name] = value.strip()
    head_fields = ['url', 'version', 'name', 'release']
    for field in head_fields:
        field_match = re.search(rf'^{field}:\s*(.+)$', spec_content, re.MULTILINE | re.IGNORECASE)
        if field_match:
            defines[field] = field_match.group(1).strip()
    return defines

def replace_macros_with_values(text, defines):
    macro_pattern = re.compile(r'%\{(\??[a-zA-Z0-9_]+)\}')
    max_iterations = 10
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        changed = False
        def replace_macro(match):
            nonlocal changed
            macro_text = match.group(1)
            if macro_text.startswith('?'):
                macro_name = macro_text[1:]
                if macro_name in defines:
                    changed = True
                    return defines[macro_name]
                else:
                    changed = True
                    return ''
            else:
                if macro_text in defines:
                    changed = True
                    return defines[macro_text]
            return match.group(0)
        new_text = macro_pattern.sub(replace_macro, text)
        if new_text == text:
            break
        text = new_text
    return text

def get_patch_info(spec_content):
    defines = parse_defines(spec_content)
    arch = platform.machine()
    os_name = platform.system().lower()
    os_macro = 'linux' if os_name == 'linux' else os_name
    isa_macro = f'({arch})'
    standard_macros = {
        '_isa': isa_macro,
        '_arch': arch,
        '_os': os_macro
    }
    defines.update(standard_macros)
    name_match = re.search(r'^Name:\s+(.+)$', spec_content, re.MULTILINE)
    if name_match:
        package_name = name_match.group(1).strip()
        defines['name'] = package_name
    patch_info = {}
    for line in spec_content.splitlines():
        line = line.strip()
        if line.startswith('#'):
            continue
        patch_match = re.match(r'^[Pp]atch(\d+)\s*:\s*(.+)$', line)
        if patch_match:
            patch_num = patch_match.group(1)
            patch_name = patch_match.group(2).strip()
            if not (patch_name.startswith('http://') or patch_name.startswith('https://') or patch_name.startswith('ftp://')):
                expanded_patch_name = replace_macros_with_values(patch_name, defines)
                patch_info[expanded_patch_name] = {
                    'number': patch_num,
                    'strip_level': None
                }
        elif line.lower().startswith('patch:'):
            patch_name = line[line.index(':')+1:].strip()
            if not (patch_name.startswith('http://') or patch_name.startswith('https://') or patch_name.startswith('ftp://')):
                expanded_patch_name = replace_macros_with_values(patch_name, defines)
                patch_info[expanded_patch_name] = {
                    'number': None,
                    'strip_level': None
                }
    parse_patch_applications(spec_content, patch_info)
    return patch_info


def parse_patch_applications(spec_content, patch_info):
    default_strip = 0
    prep_match = re.search(
        r'%prep\s*(.*?)(?:%(?:build|install|check|files|clean|changelog|description)|$)', 
        spec_content, re.DOTALL | re.MULTILINE)
    if prep_match:
        prep_section = prep_match.group(1)
        for line in prep_section.splitlines():
            m = re.search(r'%autosetup\b.*?-p\s*([0-9]+)', line)
            if m:
                default_strip = int(m.group(1))
                break
        patch_cmds = re.finditer(r'%[Pp]atch\s+(?:-P\s*(\d+))?(?:\s+-p\s*(\d+))?', prep_section)
        for match in patch_cmds:
            patch_num = match.group(1)
            strip_level = match.group(2)
            if patch_num:
                for patch_name, info in patch_info.items():
                    if info['number'] == patch_num:
                        if strip_level:
                            patch_info[patch_name]['strip_level'] = int(strip_level)
    for patch_name in patch_info:
        if patch_info[patch_name]['strip_level'] is None:
            patch_info[patch_name]['strip_level'] = default_strip


def get_patch_hash(normalized_patch_content):
    if isinstance(normalized_patch_content, list):
        norm_text = '\n'.join(normalized_patch_content)
    else:
        norm_text = str(normalized_patch_content)
    import hashlib
    return hashlib.md5(norm_text.encode('utf-8')).hexdigest()

def get_patch_names(spec_content):
    patch_info = get_patch_info(spec_content)
    return list(patch_info.keys())

def get_patch_file_content(distribution, patch_name, source_dir="/home/XXX/rpmbuild/SOURCES"):
    import urllib.parse
    if patch_name.startswith('http://') or patch_name.startswith('https://') or patch_name.startswith('ftp://'):
        parsed = urllib.parse.urlparse(patch_name)
        if parsed.fragment:
            real_name = parsed.fragment
        else:
            real_name = os.path.basename(parsed.path)
    else:
        real_name = patch_name
    patch_path = f"{source_dir}/{real_name}"
    command_check = f"wsl -d {distribution} bash -c 'test -e \"{patch_path}\"'"
    command_cat = f"wsl -d {distribution} bash -c 'cat \"{patch_path}\"'"
    try:
        result_check = subprocess.run(command_check, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result_check.returncode == 0:
            result_cat = subprocess.run(command_cat, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result_cat.returncode == 0:
                patch_content = result_cat.stdout.splitlines()
                return patch_content
            else:
                return None
        else:
            return None
    except Exception:
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
            fname = clean_line.split()[-1]
            fname = re.sub(r'^([ab]/)+', '', fname)
            normalized_lines.append(clean_line[:4] + fname)
            continue
        normalized_lines.append(clean_line)
    return normalized_lines

def extract_patch_features(normalized_content, strip_level=0):
    modified_files = []
    diff_lines = []
    for line in normalized_content:
        if line.startswith('--- ') or line.startswith('+++ '):
            file_name = line[4:].strip()
            file_name = re.sub(r'^([ab]/)+', '', file_name)
            file_stripped = strip_patch_path(file_name, strip_level)
            norm_name = normalize_patch_filename(os.path.basename(file_stripped))
            modified_files.append(norm_name)
        if line.startswith('+') or line.startswith('-'):
            diff_lines.append(line)
    return {
        "normalized_filenames": list(set(modified_files)),
        "normalized_diff_lines": diff_lines
    }


def file_list_similarity(files1, files2):
    set1, set2 = set(files1), set(files2)
    if not set1 or not set2:
        return 0
    return len(set1 & set2) / len(set1 | set2)

def diff_lines_similarity(diff1, diff2):
    set1, set2 = set(diff1), set(diff2)
    if not set1 or not set2:
        return 0
    return len(set1 & set2) / len(set1 | set2)

def patch_similarity(patchA, patchB, file_weight=0.5, diff_weight=0.5):
    filesA, filesB = patchA["normalized_filenames"], patchB["normalized_filenames"]
    linesA, linesB = patchA["normalized_diff_lines"], patchB["normalized_diff_lines"]
    files_score = file_list_similarity(filesA, filesB)
    lines_score = diff_lines_similarity(linesA, linesB)
    return file_weight * files_score + diff_weight * lines_score

def compare_patches(contentA, contentB, strip_levelA=0, strip_levelB=0, file_weight=0.3, diff_weight=0.7, threshold=0.7):
    normA = normalize_patch_content(contentA)
    normB = normalize_patch_content(contentB)
    hashA = get_patch_hash(normA)
    hashB = get_patch_hash(normB)
    if hashA == hashB:
        return 1.0, True
    featuresA = extract_patch_features(normA, strip_levelA)
    featuresB = extract_patch_features(normB, strip_levelB)
    sim = patch_similarity(featuresA, featuresB, file_weight, diff_weight)
    return sim, sim >= threshold

