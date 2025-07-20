import os
import time
import logging
import subprocess
import json
import re
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from collections import Counter

def get_package_list(distribution):
    if distribution in ['Ubuntu-24.04', 'Debian']:
        command_packages = f'wsl -d {distribution} -- bash -c "cat /var/lib/apt/lists/*Packages"'
        command_sources = f'wsl -d {distribution} -- bash -c "cat /var/lib/apt/lists/*Sources"'
    elif distribution in ['Fedora', 'openEuler-24.03']:
        command_packages = f'''wsl -d {distribution} -- bash -c "export LANG=en_US.UTF-8 && dnf repoquery --queryformat '%{{source_name}}|%{{name}}|%{{url}}|%{{summary}}|%{{version}}\\n' --available"'''
        command_sources = None
    else:
        return {}

    try:
        env = os.environ.copy()
        env['LANG'] = 'en_US.UTF-8'
        env['LC_ALL'] = 'en_US.UTF-8'

        source_to_binaries = {}
        binary_descriptions = {}

        if distribution in ['Ubuntu-24.04', 'Debian']:
            return _process_debian_packages(command_packages, command_sources, env)
        else:
            return _process_rpm_packages(command_packages, env)

    except subprocess.TimeoutExpired:
        return {}
    except subprocess.CalledProcessError as e:
        return {}
    except Exception as e:
        return {}

def _process_debian_packages(command_packages, command_sources, env):
    source_to_binaries = {}
    binary_descriptions = {}
    process_packages = subprocess.Popen(
        command_packages,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    current_binary = None
    description = ''
    version = ''
    in_description = False
    unique_descriptions = set()
    
    for line in process_packages.stdout:
        line = line.rstrip('\n')
        if line.startswith('Package:'):
            if current_binary and description:
                description_key = description.split('Description-md5')[0].strip()
                if description_key not in unique_descriptions:
                    binary_descriptions[current_binary] = {
                        'description': description.strip(),
                        'version': version
                    }
                    unique_descriptions.add(description_key)
            current_binary = line.split('Package:', 1)[1].strip()
            description = ''
            version = ''
            in_description = False
        elif line.startswith('Version:'):
            version = line.split('Version:', 1)[1].strip()
        elif line.startswith('Description:'):
            description = line.split('Description:', 1)[1].strip()
            in_description = True
        elif line.startswith(' '):
            if in_description:
                description += ' ' + line.strip()
        else:
            in_description = False
    
    if current_binary and description:
        description_key = description.split('Description-md5')[0].strip()
        if description_key not in unique_descriptions:
            binary_descriptions[current_binary] = {
                'description': description.strip(),
                'version': version
            }
            unique_descriptions.add(description_key)
    
    process_packages.stdout.close()
    process_packages.wait()
    if command_sources:
        logging.info(f'command：{command_sources}')
        process_sources = subprocess.Popen(
            command_sources,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        current_source = None
        binaries = []
        homepage = ''
        
        for line in process_sources.stdout:
            line = line.rstrip('\n')
            if line.startswith('Package:'):
                if current_source:
                    descriptions = [binary_descriptions.get(b, {}).get('description', '') for b in binaries]
                    description = ' '.join(set(descriptions))
                    versions = [binary_descriptions.get(b, {}).get('version', '') for b in binaries]
                    version = versions[0] if versions else ''
                    source_to_binaries[current_source] = {
                        'binaries': binaries, 
                        'homepage': homepage, 
                        'description': description.strip(),
                        'version': version,
                        'package_name': current_source
                    }
                    logging.debug(f"Source package: {current_source}, Description length: {len(description.strip())}")
                
                current_source = line.split('Package:', 1)[1].strip()
                binaries = []
                homepage = ''
            elif line.startswith('Binary:'):
                binary_line = line.split('Binary:', 1)[1].strip()
                binaries = [b.strip() for b in binary_line.replace('\n', '').replace(' ', '').split(',')]
            elif line.startswith('Homepage:'):
                homepage = line.split('Homepage:', 1)[1].strip()
        
        if current_source:
            descriptions = [binary_descriptions.get(b, {}).get('description', '') for b in binaries]
            description = ' '.join(set(descriptions))
            versions = [binary_descriptions.get(b, {}).get('version', '') for b in binaries]
            version = versions[0] if versions else ''
            source_to_binaries[current_source] = {
                'binaries': binaries, 
                'homepage': homepage, 
                'description': description.strip(),
                'version': version,
                'package_name': current_source
            }
        
        process_sources.stdout.close()
        process_sources.wait()
    
    logging.info(f'cpmpated：{time.strftime("%Y-%m-%d %H:%M:%S")}')
    return source_to_binaries

def _process_rpm_packages(command_packages, env):
    source_to_binaries = {}

    try:
        process_packages = subprocess.Popen(
            command_packages,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        line_count = 0
        total_lines = 0
        for _ in process_packages.stdout:
            total_lines += 1
        process_packages.stdout.close()
        process_packages.wait()
        process_packages = subprocess.Popen(
            command_packages,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        for line in process_packages.stdout:
            line = line.strip()
            if not line:
                continue
            
            line_count += 1
            if line_count % 1000 == 0:
                progress = (line_count / total_lines) * 100
            
            parts = line.split('|', 4)
            if len(parts) == 5:
                source_pkg, binary_pkg, homepage, description, version = parts
                source_pkg = source_pkg.strip()
                binary_pkg = binary_pkg.strip()
                homepage = homepage.strip()
                description = description.strip()
                version = version.strip()

                if not source_pkg or source_pkg.lower() == '(none)':
                    source_to_binaries[binary_pkg] = {
                        'binaries': [binary_pkg],
                        'homepage': homepage if homepage else 'UNKNOWN',
                        'description': description if description else 'UNKNOWN',
                        'version': version if version else 'UNKNOWN',
                        'package_name': binary_pkg,
                        'source_pkg': 'none'
                    }
                    continue

                if source_pkg in source_to_binaries:
                    source_to_binaries[source_pkg]['binaries'].append(binary_pkg)
                    if not source_to_binaries[source_pkg].get('homepage') and homepage:
                        source_to_binaries[source_pkg]['homepage'] = homepage
                    if description and description not in source_to_binaries[source_pkg]['description']:
                        source_to_binaries[source_pkg]['description'] += f" {description}"
                else:
                    source_to_binaries[source_pkg] = {
                        'binaries': [binary_pkg],
                        'homepage': homepage if homepage else 'UNKNOWN',
                        'description': description if description else 'UNKNOWN',
                        'version': version if version else 'UNKNOWN',
                        'package_name': source_pkg
                    }
        
        print() 
        process_packages.stdout.close()
        process_packages.stderr.close()
        process_packages.wait()
        return source_to_binaries
        
    except Exception as e:
        return {}

def sort_packages(package_list):
    def sort_key(s):
        if not s:
            return (2, s)
        first_char = s[0]
        if first_char.isdigit():
            return (0, s.lower())
        elif first_char.isalpha():
            return (1, s.lower())
        else:
            return (2, s.lower())
    return sorted(package_list, key=sort_key)

def is_similar_name(name1, name2):

    if name1.lower() == name2.lower():
        return True

    def calculate_similarity(s1, s2):
        s1 = s1.lower()
        s2 = s2.lower()
     
        def levenshtein_distance(s1, s2):
            if len(s1) < len(s2):
                return levenshtein_distance(s2, s1)
            if not s2:
                return len(s1)
            previous_row = range(len(s2) + 1)
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
            return previous_row[-1]
        
        distance = levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        similarity = 1 - (distance / max_len)
        return similarity

    prefixes = ['lib', 'python3-', 'python-', 'perl-', 'ruby-', 'php-', 'golang-', 'nodejs-']
    suffixes = ['-dev', '-doc', '-common', '-devel', '-libs', '-tools', '-bin','-utils']
    
    name1 = name1.lower()
    name2 = name2.lower()
    
    orig_name1 = name1
    orig_name2 = name2
    
    for prefix in prefixes:
        if name1.startswith(prefix):
            name1 = name1[len(prefix):]
        if name2.startswith(prefix):
            name2 = name2[len(prefix):]
 
    for suffix in suffixes:
        if name1.endswith(suffix):
            name1 = name1[:-len(suffix)]
        if name2.endswith(suffix):
            name2 = name2[:-len(suffix)]
    
    similarity = calculate_similarity(name1, name2)
    if similarity >= 0.97:
        return True

    similarity = calculate_similarity(orig_name1, orig_name2)
    return similarity >= 0.97

def is_similar_homepage(url1, url2):

    if not url1 or not url1.strip() or url1.strip() == 'UNKNOWN':
        return False
    if not url2 or not url2.strip() or url2.strip() == 'UNKNOWN':
        return False
    
    def normalize_url(url):
        url = url.lower()
        url = url.replace('https://', '').replace('http://', '')
        url = url.replace('www.', '')
        url = url.rstrip('/')
        if '?' in url:
            url = url.split('?')[0]
        return url
    
    norm_url1 = normalize_url(url1)
    norm_url2 = normalize_url(url2)
    
    if norm_url1 == norm_url2:
        return True
      
    domain1 = norm_url1.split('/')[0] if '/' in norm_url1 else norm_url1
    domain2 = norm_url2.split('/')[0] if '/' in norm_url2 else norm_url2

    if domain1 == domain2:
        return True
        
    if ('github.com' in norm_url1 and 'github.com' in norm_url2):
        parts1 = norm_url1.split('/')
        parts2 = norm_url2.split('/')
        if len(parts1) >= 3 and len(parts2) >= 3:
            return parts1[1] == parts2[1] and parts1[2] == parts2[2]
    
    def extract_project_name(url):
        if '/' in url:
            parts = url.split('/')
            for i in range(len(parts)-1, -1, -1):
                if parts[i].strip():
                    return parts[i].strip()
        return None
    
    project1 = extract_project_name(norm_url1)
    project2 = extract_project_name(norm_url2)
    
    if project1 and project2 and project1 == project2:
        return True
            
    return False

def find_similar_packages(name, homepage, all_packages):
    similar_packages = []
    
    for pkg, info in all_packages.items():
        if pkg == name:
            continue
        if is_similar_name(name, pkg):
            if name.lower() == pkg.lower():
                similar_packages.append((pkg, "exact_match"))
                continue
            pkg_homepage = info.get('homepage', '')
            if homepage and pkg_homepage and is_similar_homepage(homepage, pkg_homepage):
                similar_packages.append((pkg, "similar_name_same_homepage"))
                continue
        elif homepage and info.get('homepage', '') and is_similar_homepage(homepage, info.get('homepage', '')):
            similar_packages.append((pkg, "different_name_same_homepage"))
            continue
    
    return similar_packages

def save_to_json(data: dict, output_dir: str = "data/packages", filename: str = "package_analysis.json") -> str:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    file_path = output_path / filename
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("-" * 50)
    for key, value in data.items():
        if key.endswith('_all'):
            print(f"{key}: {len(value)}")
        elif key.endswith('_common'):
            if isinstance(value, dict):
                print(f"{key}: {len(value)}")
            else:
                print(f"{key}: {len(value)}")
    
    print("-" * 50)
    
    return str(file_path)

def format_result_for_output(raw_result: dict) -> dict:
    formatted_result = {}
    distro_package_data = raw_result.get('package_data', {})
    distributions = raw_result.get('distributions', [])
    comparisons = raw_result.get('comparisons', {})
    common_packages_multi = raw_result.get('common_packages', {})

    total_source_matches = 0 
    result_statistics = {}

    for distro in distributions:
        distro_lower = distro.lower()
        data = distro_package_data.get(distro, {})
        formatted_result[f"{distro_lower}_all"] = data
        result_statistics[f"{distro_lower}_all"] = len(data)

    for key, comparison in comparisons.items():
        try:
            distro1, distro2 = key.split('_vs_')
            distro1_lower = distro1.lower()
            distro2_lower = distro2.lower()
        except ValueError:
            continue

        common_canonical_list = comparison.get('common', [])
        match_info_map = comparison.get('match_info', {}) 

        common_packages_formatted = {}
        missing_data_count = 0
        source_match_count_pair = 0 

        for pkg_canonical in common_canonical_list:
            info = match_info_map.get(pkg_canonical)
            if not info:
                continue

            pkg1_orig = info.get('distro1_orig')
            pkg2_orig = info.get('distro2_orig')
            match_type = info.get('match_type', '')

            if not pkg1_orig or not pkg2_orig:
                continue

            data1 = distro_package_data.get(distro1, {}).get(pkg1_orig)
            data2 = distro_package_data.get(distro2, {}).get(pkg2_orig)

            if data1 and data2:
                norm_name = pkg_canonical.split(':', 1)[0].lower() if ':' in pkg_canonical else pkg_canonical.lower()
                final_key = norm_name
                pkg_name1_internal = data1.get('package_name', '').lower()
                pkg_name2_internal = data2.get('package_name', '').lower()
                if pkg_name1_internal and pkg_name1_internal == pkg_name2_internal:
                    final_key = pkg_name1_internal

                pkg_data = {
                    distro1: data1,
                    distro2: data2,
                    "match_info": {"match_type": match_type}
                }
                if match_type == "source_match":
                    source_match_count_pair += 1
                    total_source_matches += 1
                    pkg_data["match_info"]["note"] = "NOTE"

                common_packages_formatted[final_key] = pkg_data
            else:
                missing_data_count += 1

        formatted_key_pair = f"{distro1_lower}_{distro2_lower}_common"
        formatted_result[formatted_key_pair] = common_packages_formatted
        result_statistics[formatted_key_pair] = {
            "count": len(common_packages_formatted),
            "source_matches": source_match_count_pair
        }

    all_package_mapping_detailed = {}
    for comp_key, comparison in comparisons.items():
        try:
            distro1, distro2 = comp_key.split('_vs_')
        except ValueError:
            continue 

        match_info_map = comparison.get('match_info', {})
        for pkg_norm_with_type, info in match_info_map.items():
            norm_name = pkg_norm_with_type.split(':', 1)[0] 
            pkg_lower = norm_name.lower()

            if pkg_lower not in all_package_mapping_detailed:
                all_package_mapping_detailed[pkg_lower] = {
                    'original_names': {}, 
                    'match_types': {}     
                }
            if distro1 not in all_package_mapping_detailed[pkg_lower]['original_names']:
                all_package_mapping_detailed[pkg_lower]['original_names'][distro1] = info.get('distro1_orig')
            if distro2 not in all_package_mapping_detailed[pkg_lower]['original_names']:
                 all_package_mapping_detailed[pkg_lower]['original_names'][distro2] = info.get('distro2_orig')

            pair_key = tuple(sorted((distro1, distro2)))
            all_package_mapping_detailed[pkg_lower]['match_types'][pair_key] = info.get('match_type', 'unknown')

    multi_distro_results_formatted = {} 
    for group_key, common_pkg_list_norm in common_packages_multi.items():
        if not group_key.endswith('_common'): continue

        current_distros = distributions if group_key == 'all_common' else group_key.split('_common')[0].split('_')
        current_distros_lower = [d.lower() for d in current_distros]
        formatted_key_multi = f"{'_'.join(current_distros_lower)}_common"

        common_packages_formatted_multi = {}
        missing_data_count_multi = 0
        source_match_count_group = 0
        match_type_aggregation_final = Counter() 

        for pkg_norm_with_type in common_pkg_list_norm:
            norm_name = pkg_norm_with_type.split(':', 1)[0]
            pkg_lower = norm_name.lower()

            mapping_info = all_package_mapping_detailed.get(pkg_lower)
            if not mapping_info:
                continue

            if not all(distro in mapping_info['original_names'] and mapping_info['original_names'][distro] is not None
                       for distro in current_distros):
                continue

            package_data_multi = {}
            all_data_found = True
            for distro in current_distros:
                orig_name = mapping_info['original_names'][distro]
                data = distro_package_data.get(distro, {}).get(orig_name)
                if data:
                    package_data_multi[distro] = data
                else:
                    missing_data_count_multi += 1
                    all_data_found = False
                   
                    break

            if not all_data_found:
                continue

            relevant_match_types = []
            for i in range(len(current_distros)):
                for j in range(i + 1, len(current_distros)):
                    pair_key = tuple(sorted((current_distros[i], current_distros[j])))
                    match_type = mapping_info['match_types'].get(pair_key, 'unknown')
                    if match_type != 'unknown':
                        relevant_match_types.append(match_type)

            priority = {'source_match': 1, 'std_match': 2, 'exact_match': 3}
            final_match_type = 'unknown'
            min_priority_val = float('inf') 

            if not relevant_match_types:
                 logging.warning("WARNNING")
            else:
                 for mt in relevant_match_types:
                     current_priority = priority.get(mt, 0)
                     if 0 < current_priority < min_priority_val: 
                         min_priority_val = current_priority
                         final_match_type = mt
                     elif current_priority == min_priority_val and mt != final_match_type:
                          pass

                 if min_priority_val == float('inf'):
                     final_match_type = 'unknown' 

            match_type_aggregation_final[final_match_type] += 1
            if final_match_type == 'source_match':
                source_match_count_group += 1

            package_names_internal = [package_data_multi[distro].get('package_name', '').lower() for distro in current_distros]
            use_pkg_name_as_key = package_names_internal and all(name == package_names_internal[0] for name in package_names_internal) and package_names_internal[0]
            final_key_multi = package_names_internal[0] if use_pkg_name_as_key else pkg_lower

            package_data_multi["match_info"] = {"match_type": final_match_type}
            if final_match_type == "source_match":
                package_data_multi["match_info"]["note"] = "NOTE"

            common_packages_formatted_multi[final_key_multi] = package_data_multi

        multi_distro_results_formatted[formatted_key_multi] = {
            'data': common_packages_formatted_multi,
            'count': len(common_packages_formatted_multi),
            'source_matches': source_match_count_group
        }
    for key, result_info in multi_distro_results_formatted.items():
        formatted_result[key] = result_info['data']
        result_statistics[key] = {
            "count": result_info['count'],
            "source_matches": result_info.get('source_matches', 0)
        }
    for key, value in result_statistics.items():
        if key.endswith('_all'):
            print(f"{key}: {value}")
        elif key.endswith('_common'):
            if isinstance(value, dict):
                print(f"{key}: COMMON: {value['count']}, SOURCE: {value.get('source_matches', 0)}")
            else: 
                print(f"{key}: {len(value)}")
    print("-" * 50)
    
    print("-" * 50)

    return formatted_result

def extract_upstream_version(version_str):
    if not version_str or version_str.lower() == 'UNKNOWN':
        return None
        
    version_str = version_str.lower().strip()

    if ':' in version_str:
        version_str = version_str.split(':', 1)[1]

    prefixes = ['v', 'version', 'ver', 'release']
    for prefix in prefixes:
        if version_str.startswith(prefix):
            version_str = version_str[len(prefix):].strip()

    if '-' in version_str:
        parts = version_str.split('-')
        version_str = '-'.join(parts[:-1])

    if '+' in version_str:
        version_str = version_str.split('+')[0]

    if '~' in version_str:
        version_str = version_str.split('~')[0]

    parts = version_str.split('.')
    normalized_parts = []
    for part in parts:
        if part.isdigit():
            normalized_parts.append(str(int(part)))
        else:
            normalized_parts.append(part)

    return '.'.join(normalized_parts)


def compare_versions(version1, version2):
    if not version1 or not version2:
        return False

    v1 = extract_upstream_version(version1)
    v2 = extract_upstream_version(version2)
    
    if not v1 or not v2:
        return False

    return v1 == v2

def analyze_and_save(distributions: list, output_dir: str = "data/packages", with_version: bool = False) -> dict:
    package_data = {}
    package_sets = {}

    for distro in distributions:
        packages = get_package_list(distro)
        if packages:
            package_data[distro] = packages
            package_sets[distro] = set(packages.keys())

    comparison_results = {}
    total_comparisons = len(distributions) * (len(distributions) - 1) // 2
    comparison_count = 0
    
    for i in range(len(distributions)):
        for j in range(i+1, len(distributions)):
            comparison_count += 1
            distro1, distro2 = distributions[i], distributions[j]
            if distro1 in package_data and distro2 in package_data:
                result = advanced_compare_packages(package_data[distro1], package_data[distro2])
                
                if with_version:
                    version_matched = {}
                    for pkg, info in result['match_info'].items():
                        pkg1 = info['distro1_orig']
                        pkg2 = info['distro2_orig']
                        
                        version1 = package_data[distro1][pkg1].get('version', '')
                        version2 = package_data[distro2][pkg2].get('version', '')
                        
                        if compare_versions(version1, version2):
                            version_matched[pkg] = info
                    
                    result['match_info'] = version_matched
                    result['common'] = list(version_matched.keys())
                
                comparison_results[f"{distro1}_vs_{distro2}"] = result

    all_package_mapping = {}  
    for distro1, distro2, result in [(distributions[i], distributions[j], comparison_results[f"{distributions[i]}_vs_{distributions[j]}"]) 
                                    for i in range(len(distributions)) 
                                    for j in range(i+1, len(distributions))]:
        for pkg_norm, info in result['match_info'].items():
            if ':' in pkg_norm:
                norm_name, pkg_type = pkg_norm.split(':', 1)
            else:
                norm_name = pkg_norm
                pkg_type = 'runtime'
                
            key = f"{norm_name}:{pkg_type}"
            
            if key not in all_package_mapping:
                all_package_mapping[key] = {}

            all_package_mapping[key][distro1] = info['distro1_orig']
            all_package_mapping[key][distro2] = info['distro2_orig']
    
    multi_distro_combinations = []
    
    for i in range(len(distributions)):
        for j in range(i+1, len(distributions)):
            for k in range(j+1, len(distributions)):
                distro1, distro2, distro3 = distributions[i], distributions[j], distributions[k]
                combo = [distro1, distro2, distro3]
                key = f"{distro1}_{distro2}_{distro3}_common"
                multi_distro_combinations.append((combo, key))
    
    if len(distributions) >= 4:
        multi_distro_combinations.append((distributions, "all_common"))
    
    multi_distro_results = {}
    
    for combo, key in multi_distro_combinations:
        
        common_pkgs = []
        
        for pkg_norm, distro_map in all_package_mapping.items():
            if all(distro in distro_map for distro in combo):
                if not with_version:
                    common_pkgs.append(pkg_norm)
                else:
                    versions = []
                    for distro in combo:
                        orig_pkg = distro_map[distro]
                        version = package_data[distro][orig_pkg].get('version', '')
                        upstream_version = extract_upstream_version(version)
                        versions.append(upstream_version)
                    
                    if len(set(versions)) == 1:  
                        common_pkgs.append(pkg_norm)
        
        multi_distro_results[key] = common_pkgs
    
    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "distributions": distributions,
        "package_data": package_data,
        "comparisons": comparison_results,
        "common_packages": multi_distro_results
    }
    

    formatted_result = format_result_for_output(result)
 
    output_filename = "package_analysis_withVersion.json" if with_version else "package_analysis.json"
    save_to_json(formatted_result, output_dir, output_filename)
    
    return result

def advanced_compare_packages(pkg_data1, pkg_data2, similarity_threshold=0.8):
    
    common_canonical = {}
    
    pkgs1_lower = {k.lower(): k for k in pkg_data1.keys()}
    pkgs2_lower = {k.lower(): k for k in pkg_data2.keys()}
    
    common_exact_names = set(pkgs1_lower.keys()) & set(pkgs2_lower.keys())

    matched_pkgs1 = set()
    matched_pkgs2 = set()
    
    exact_match_success = 0
    
    filtered_packages = []
    
    for pkg_lower in common_exact_names:
        orig_name1 = pkgs1_lower[pkg_lower]
        orig_name2 = pkgs2_lower[pkg_lower]
        
        pkg_info1 = pkg_data1[orig_name1]
        pkg_info2 = pkg_data2[orig_name2]
        
        pkg_type = 'runtime' 
        if orig_name1.endswith('-dev') or orig_name1.endswith('-devel'):
            pkg_type = 'dev'
        elif orig_name1.endswith('-doc'):
            pkg_type = 'doc'
        elif orig_name1.endswith('-common'):
            pkg_type = 'common'
        elif orig_name1.endswith('-libs'):
            pkg_type = 'libs'
        elif orig_name1.endswith('-tools'):
            pkg_type = 'tools'
        elif orig_name1.endswith('-bin'):
            pkg_type = 'bin'
            
        desc1 = pkg_info1.get('description', '')
        desc2 = pkg_info2.get('description', '')
        desc_similarity = get_package_description_similarity(desc1, desc2)
        
        homepage1 = pkg_info1.get('homepage', '')
        homepage2 = pkg_info2.get('homepage', '')
        homepage_match = is_similar_homepage(homepage1, homepage2)
        
        evidence = []
        evidence.append(f"EXCATMATCH: {pkg_lower}")
        evidence.append(f"SIM: {desc_similarity:.2f}")
        evidence.append(f"HOMEPAGE: {homepage_match}")
        
        canonical_key = f"{pkg_lower}:{pkg_type}"
        
        common_canonical[canonical_key] = {
            "match_type": "exact_match",
            "distro1_orig": orig_name1,
            "distro2_orig": orig_name2,
            "normalized_name": pkg_lower,
            "package_type": pkg_type,
            "evidence": ", ".join(evidence)
        }

        matched_pkgs1.add(orig_name1)
        matched_pkgs2.add(orig_name2)
        exact_match_success += 1
        
        if desc_similarity < similarity_threshold and not homepage_match:
            filtered_packages.append({
                "package_name": pkg_lower,
                "distro1_orig": orig_name1,
                "distro2_orig": orig_name2,
                "description1": desc1[:100] + ("..." if len(desc1) > 100 else ""),
                "description2": desc2[:100] + ("..." if len(desc2) > 100 else ""),
                "desc_similarity": desc_similarity,
                "homepage1": homepage1,
                "homepage2": homepage2,
                "homepage_match": homepage_match
            })

    unmatched_pkg_data1 = {k: v for k, v in pkg_data1.items() if k not in matched_pkgs1}
    unmatched_pkg_data2 = {k: v for k, v in pkg_data2.items() if k not in matched_pkgs2}
    
    
    pkgs1_std = {}  
    pkgs2_std = {}
    
    for pkg_name, pkg_info in unmatched_pkg_data1.items():
        std_name, pkg_type = normalize_package_name(pkg_name, level='medium')
        
        if std_name not in pkgs1_std:
            pkgs1_std[std_name] = {}
        pkgs1_std[std_name][pkg_type] = pkg_name
    
    for pkg_name, pkg_info in unmatched_pkg_data2.items():
        std_name, pkg_type = normalize_package_name(pkg_name, level='medium')
        
        if std_name not in pkgs2_std:
            pkgs2_std[std_name] = {}
        pkgs2_std[std_name][pkg_type] = pkg_name

    common_std_names = set(pkgs1_std.keys()) & set(pkgs2_std.keys())
    std_match_success = 0

    for std_name in common_std_names:
        for pkg_type in set(pkgs1_std[std_name].keys()) & set(pkgs2_std[std_name].keys()):
            orig_name1 = pkgs1_std[std_name][pkg_type]
            orig_name2 = pkgs2_std[std_name][pkg_type]
            
            pkg_info1 = pkg_data1[orig_name1]
            pkg_info2 = pkg_data2[orig_name2]
            
            desc1 = pkg_info1.get('description', '')
            desc2 = pkg_info2.get('description', '')
            desc_similarity = get_package_description_similarity(desc1, desc2)
            
            homepage1 = pkg_info1.get('homepage', '')
            homepage2 = pkg_info2.get('homepage', '')
            homepage_match = is_similar_homepage(homepage1, homepage2)
            
            evidence = []
            evidence.append(f"STDMATCH: {std_name} (ORIG: {orig_name1}/{orig_name2})")
            evidence.append(f"SIM: {desc_similarity:.2f}")
            evidence.append(f"HOMEPAGE: {homepage_match}")
            
            canonical_key = f"{std_name}:{pkg_type}"
            
            match_condition = False
            
            if std_name:  
                match_condition = (
                    desc_similarity >= similarity_threshold or
                    homepage_match or
                    (len(std_name) >= 4 and desc_similarity >= 0.4)
                )
            
            if match_condition:
                common_canonical[canonical_key] = {
                    "match_type": "std_match",
                    "distro1_orig": orig_name1,
                    "distro2_orig": orig_name2,
                    "normalized_name": std_name,
                    "package_type": pkg_type,
                    "evidence": ", ".join(evidence)
                }
                matched_pkgs1.add(orig_name1)
                matched_pkgs2.add(orig_name2)
                std_match_success += 1
              
    matched_pkgs1.update([info["distro1_orig"] for info in common_canonical.values()])
    matched_pkgs2.update([info["distro2_orig"] for info in common_canonical.values()])
    
    unmatched_pkg_data1 = {k: v for k, v in pkg_data1.items() if k not in matched_pkgs1}
    unmatched_pkg_data2 = {k: v for k, v in pkg_data2.items() if k not in matched_pkgs2}
  
    pkgs1_src = {} 
    pkgs2_src = {}
    
    for pkg_name, pkg_info in unmatched_pkg_data1.items():
        src_name = get_source_package_name(pkg_info)
        if src_name:
            if src_name not in pkgs1_src:
                pkgs1_src[src_name] = []
            pkgs1_src[src_name].append(pkg_name)
    
    for pkg_name, pkg_info in unmatched_pkg_data2.items():
        src_name = get_source_package_name(pkg_info)
        if src_name:
            if src_name not in pkgs2_src:
                pkgs2_src[src_name] = []
            pkgs2_src[src_name].append(pkg_name)
    
    common_src_names = set(pkgs1_src.keys()) & set(pkgs2_src.keys())
    
    source_match_count = 0
    
    for src_name in common_src_names:
        for orig_name1 in pkgs1_src[src_name]:
            for orig_name2 in pkgs2_src[src_name]:
                if orig_name1 in matched_pkgs1 or orig_name2 in matched_pkgs2:
                    continue
                    
                std_name1, pkg_type1 = normalize_package_name(orig_name1, level='medium')
                std_name2, pkg_type2 = normalize_package_name(orig_name2, level='medium')
                
                if pkg_type1 == pkg_type2:
                    pkg_info1 = pkg_data1[orig_name1]
                    pkg_info2 = pkg_data2[orig_name2]
                    
                    desc1 = pkg_info1.get('description', '')
                    desc2 = pkg_info2.get('description', '')
                    desc_similarity = get_package_description_similarity(desc1, desc2)
                    
                    evidence = []
                    evidence.append(f"SOURCE: {src_name}")
                    evidence.append(f"SIM: {desc_similarity:.2f}")
                    
                    if len(std_name1) <= len(std_name2):
                        norm_name = std_name1
                    else:
                        norm_name = std_name2
                    
                    canonical_key = f"{norm_name}:{pkg_type1}"
                    
                    if canonical_key not in common_canonical:
                        common_canonical[canonical_key] = {
                            "match_type": "source_match",  
                            "distro1_orig": orig_name1,
                            "distro2_orig": orig_name2,
                            "normalized_name": norm_name,
                            "package_type": pkg_type1,
                            "evidence": ", ".join(evidence)
                        }
                        matched_pkgs1.add(orig_name1)
                        matched_pkgs2.add(orig_name2)
                        source_match_count += 1
    
    
    match_types = {}
    for info in common_canonical.values():
        match_type = info.get("match_type", "unknown")
        match_types[match_type] = match_types.get(match_type, 0) + 1
    
    return {
        "common": sort_packages(list(common_canonical.keys())),
        "match_info": common_canonical
    }
def compare_packages(pkg_data1, pkg_data2):
    pkgs1_lower = {k.lower(): k for k in pkg_data1.keys()}
    pkgs2_lower = {k.lower(): k for k in pkg_data2.keys()}
    
    common_canonical = {} 
    
    common_names = set(pkgs1_lower.keys()) & set(pkgs2_lower.keys())
    
    for pkg_lower in common_names:
        orig_name1 = pkgs1_lower[pkg_lower]
        orig_name2 = pkgs2_lower[pkg_lower]
        
        common_canonical[pkg_lower] = {
            "match_type": "exact",
            "distro1_orig": orig_name1,
            "distro2_orig": orig_name2
        }
    return {
        "common": sort_packages(list(common_canonical.keys())), 
        "match_info": common_canonical
    }

def calculate_similarity(s1, s2):
    if len(s1) < len(s2):
        return calculate_similarity(s2, s1)
    if not s2:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    distance = previous_row[-1]
    max_len = max(len(s1), len(s2))
    return 1 - (distance / max_len)

def normalize_package_name(pkg_name, level='full'):
    prefixes = ['lib', 'python3-', 'python-', 'perl-', 'ruby-', 'php-', 'golang-', 'nodejs-']
    suffixes = ['-dev', '-doc', '-common', '-devel', '-libs', '-tools', '-bin']
    
    name = pkg_name.lower()
    
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    
    pkg_type = 'runtime'  
    if pkg_name.endswith('-dev') or pkg_name.endswith('-devel'):
        pkg_type = 'dev'
    elif pkg_name.endswith('-doc'):
        pkg_type = 'doc'
    elif pkg_name.endswith('-common'):
        pkg_type = 'common'
    elif pkg_name.endswith('-libs'):
        pkg_type = 'libs'
    elif pkg_name.endswith('-tools'):
        pkg_type = 'tools'
    elif pkg_name.endswith('-bin'):
        pkg_type = 'bin'
    
    if level == 'full':
        name = name.replace('-', '').replace('_', '').replace('.', '')
    elif level == 'medium':
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
    
    return name, pkg_type

def get_source_package_name(pkg_info):
    if 'source_pkg' in pkg_info and pkg_info['source_pkg'] != 'none':
        return pkg_info['source_pkg']
    elif 'package_name' in pkg_info:
        return pkg_info['package_name']
    return None

def get_package_description_similarity(desc1, desc2):
    if not desc1 or not desc2:
        return 0.0
    vectorizer = TfidfVectorizer()
    try:
        tfidf_matrix = vectorizer.fit_transform([desc1, desc2])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return similarity
    except:
        return 0.0