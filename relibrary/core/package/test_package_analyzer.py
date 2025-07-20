import sys
import os
import logging
import argparse

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

try:
    package_dir = os.path.join(project_root, 'relibrary', 'core', 'package')
    sys.path.insert(0, package_dir)
    
    from package_analyzer import (
        get_package_list, 
        compare_packages,
        find_similar_packages,
        analyze_and_save
    )
except ImportError as e:
    sys.exit(1)

def test_detailed_analysis(distributions):
    package_data = {}
    
    for distro in distributions:
        try:
            packages = get_package_list(distro)
            if not packages:
                continue
                
            package_data[distro] = packages
            
        except Exception as e:
            import traceback
            traceback.print_exc()
    
    return package_data

def test_json_output(distributions, output_dir="data/packages", with_version=False):
    try:
        result = analyze_and_save(distributions, output_dir, with_version)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None

def main():
    parser = argparse.ArgumentParser(description='TOOLS')
    parser.add_argument('--mode', choices=['detailed', 'json', 'all'], default='all',
                        help='MODE: detailed, json, all')
    parser.add_argument('--distros', nargs='+', 
                        default=['Ubuntu-24.04', 'Debian', 'Fedora', 'openEuler-24.03'],
                        help='DISTRO LISTS')
    parser.add_argument('--output', default='data/packages', 
                        help='OUTPUT_DIR')
    parser.add_argument('--withVersion', action='store_true',
                        help='VERSION?')
    
    args = parser.parse_args()
    
    if args.mode in ['detailed', 'all']:
        test_detailed_analysis(args.distros)
    
    if args.mode in ['json', 'all']:
        test_json_output(args.distros, args.output, args.withVersion)
    

if __name__ == '__main__':
    main() 