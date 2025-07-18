import sys
import os
import logging
import argparse

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)
print(f"项目根目录: {project_root}")
print(f"Python路径: {sys.path}")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

print("开始导入模块...")
try:
    # 添加 core/package 目录到 Python 路径
    package_dir = os.path.join(project_root, 'relibrary', 'core', 'package')
    sys.path.insert(0, package_dir)
    
    from package_analyzer import (
        get_package_list, 
        compare_packages,
        find_similar_packages,
        analyze_and_save
    )
    print("成功导入package_analyzer模块")
except ImportError as e:
    print(f"导入package_analyzer模块失败: {e}")
    print(f"Python路径: {sys.path}")
    sys.exit(1)

def test_detailed_analysis(distributions):
    """执行详细的软件包分析测试"""
    print(f"\n===== 开始详细分析 =====")
    package_data = {}
    
    for distro in distributions:
        print(f"\n正在获取 {distro} 的软件包信息...")
        try:
            packages = get_package_list(distro)
            if not packages:
                print(f"未获取到 {distro} 的软件包信息")
                continue
                
            package_data[distro] = packages
            print(f"获取到 {len(packages)} 个软件包")
            
        except Exception as e:
            print(f"处理 {distro} 时出错: {e}")
            import traceback
            traceback.print_exc()
    
    return package_data

def test_json_output(distributions, output_dir="data/packages", with_version=False):
    """测试JSON输出功能"""
    print(f"\n===== 开始JSON输出测试 =====")
    print(f"分析发行版: {', '.join(distributions)}")
    
    try:
        result = analyze_and_save(distributions, output_dir, with_version)
        print(f"分析完成，结果已保存到JSON文件")
        return result
    except Exception as e:
        print(f"分析过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    parser = argparse.ArgumentParser(description='软件包分析工具')
    parser.add_argument('--mode', choices=['detailed', 'json', 'all'], default='all',
                        help='运行模式: detailed-详细分析, json-仅生成JSON, all-全部运行')
    parser.add_argument('--distros', nargs='+', 
                        default=['Ubuntu-24.04', 'Debian', 'Fedora', 'openEuler-24.03'],
                        help='要分析的发行版列表')
    parser.add_argument('--output', default='data/packages', 
                        help='输出目录')
    parser.add_argument('--withVersion', action='store_true',
                        help='是否进行版本比较，生成包含版本信息的JSON文件')
    
    args = parser.parse_args()
    
    print(f"运行模式: {args.mode}")
    print(f"分析发行版: {', '.join(args.distros)}")
    print(f"输出目录: {args.output}")
    print(f"版本比较: {'是' if args.withVersion else '否'}")
    
    if args.mode in ['detailed', 'all']:
        test_detailed_analysis(args.distros)
    
    if args.mode in ['json', 'all']:
        test_json_output(args.distros, args.output, args.withVersion)
    
    print("\n分析完成!")

if __name__ == '__main__':
    main() 