"""
Web API服务器模块，提供Web接口访问软件包数据
"""

import os
import json
from flask import Flask, jsonify, request, render_template, send_from_directory
from relibrary.utils.db.sqlite_operations import PackageDatabase
from relibrary.utils.files.file_operations import load_json
from relibrary.analysis.package_compare import compare_distribution_packages
from relibrary.analysis.patch_compare import compare_patches_between_distros

app = Flask(__name__, static_folder='static', template_folder='templates')

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
COMPARISON_DIR = os.path.join(DATA_DIR, 'comparison')
DB_DIR = os.path.join(DATA_DIR, 'db')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(COMPARISON_DIR, exist_ok=True)
os.makedirs(DB_DIR, exist_ok=True)

DISTRIBUTIONS = ['Fedora', 'openEuler-24.03', 'Ubuntu-24.04', 'Debian']

@app.route('/')
def index():
    """主页"""
    return render_template('index.html', distributions=DISTRIBUTIONS)

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/distributions')
def get_distributions():
    return jsonify({
        'status': 'success',
        'data': DISTRIBUTIONS
    })

@app.route('/api/packages/<distribution>')
def get_packages(distribution):
    if distribution not in DISTRIBUTIONS:
        return jsonify({
            'status': 'error',
            'message': f'不支持的发行版: {distribution}'
        }), 400
    
    cache_file = os.path.join(DATA_DIR, 'packages', f"{distribution.lower().replace('-', '_')}_packages.json")
    if os.path.exists(cache_file):
        data = load_json(cache_file)
        if data:
            page = int(request.args.get('page', 1))
            page_size = int(request.args.get('page_size', 100))
            
            sorted_names = sorted(data.keys())
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_names = sorted_names[start_idx:end_idx]

            page_data = {name: data[name] for name in page_names}
            
            return jsonify({
                'status': 'success',
                'data': page_data,
                'pagination': {
                    'total': len(sorted_names),
                    'page': page,
                    'page_size': page_size,
                    'total_pages': (len(sorted_names) + page_size - 1) // page_size
                }
            })
    return jsonify({
        'status': 'error',
        'message': f'未找到{distribution}的软件包数据'
    }), 404

@app.route('/api/packages/search')
def search_packages():
    """搜索软件包"""
    query = request.args.get('q', '').lower()
    distribution = request.args.get('distribution')
    
    if not query:
        return jsonify({
            'status': 'error',
            'message': '请提供搜索关键词'
        }), 400
    
    if distribution and distribution not in DISTRIBUTIONS:
        return jsonify({
            'status': 'error',
            'message': f'不支持的发行版: {distribution}'
        }), 400
    
    distributions_to_search = [distribution] if distribution else DISTRIBUTIONS
    
    results = {}
    
    for dist in distributions_to_search:
        # 从缓存加载
        cache_file = os.path.join(DATA_DIR, 'packages', f"{dist.lower().replace('-', '_')}_packages.json")
        if os.path.exists(cache_file):
            data = load_json(cache_file)
            if not data:
                continue

            dist_results = {}
            for pkg_name, pkg_info in data.items():
                if query in pkg_name.lower():
                    dist_results[pkg_name] = pkg_info
                    continue
                
                description = pkg_info.get('description', '').lower()
                if query in description:
                    dist_results[pkg_name] = pkg_info
                    continue
                
                for binary in pkg_info.get('binaries', []):
                    if query in binary.lower():
                        dist_results[pkg_name] = pkg_info
                        break
            
            if dist_results:
                results[dist] = dist_results
    
    if results:
        return jsonify({
            'status': 'success',
            'data': results
        })
    else:
        return jsonify({
            'status': 'success',
            'message': '未找到匹配的软件包',
            'data': {}
        })

@app.route('/api/package/<distribution>/<package_name>')
def get_package_details(distribution, package_name):
    """获取软件包详情"""
    if distribution not in DISTRIBUTIONS:
        return jsonify({
            'status': 'error',
            'message': f'不支持的发行版: {distribution}'
        }), 400
    

    cache_file = os.path.join(DATA_DIR, 'packages', f"{distribution.lower().replace('-', '_')}_packages.json")
    if os.path.exists(cache_file):
        data = load_json(cache_file)
        if data and package_name in data:
            db_path = os.path.join(DB_DIR, f"{distribution.lower().replace('-', '_')}.db")
            patches = []
            
            if os.path.exists(db_path):
                db = PackageDatabase(db_path)
                patches = db.get_package_patches(package_name, distribution)
            
            package_info = data[package_name]
            package_info['patches'] = patches
            
            return jsonify({
                'status': 'success',
                'data': package_info
            })
    
    return jsonify({
        'status': 'error',
        'message': f'未找到软件包: {package_name}'
    }), 404

@app.route('/api/compare', methods=['POST'])
def compare_packages():
    """比较不同发行版的软件包"""
    data = request.json
    if not data:
        return jsonify({
            'status': 'error',
            'message': '请提供比较参数'
        }), 400
    
    distributions = data.get('distributions', [])
    if not distributions or len(distributions) < 2:
        return jsonify({
            'status': 'error',
            'message': '请提供至少两个发行版进行比较'
        }), 400
    
    for dist in distributions:
        if dist not in DISTRIBUTIONS:
            return jsonify({
                'status': 'error',
                'message': f'不支持的发行版: {dist}'
            }), 400
 
    try:
        result = compare_distribution_packages(
            distributions, 
            output_dir=COMPARISON_DIR,
            html_report=True
        )
        
        return jsonify({
            'status': 'success',
            'message': '比较完成',
            'data': {
                'report_url': f'/comparison/{distributions[0]}_vs_{distributions[1]}.html',
                'json_url': f'/comparison/enhanced_comparison.json',
                'summary': {
                    'compared_distributions': distributions
                }
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'比较失败: {str(e)}'
        }), 500

@app.route('/api/compare/patches', methods=['POST'])
def compare_patches():
    """比较不同发行版的补丁"""
    data = request.json
    if not data:
        return jsonify({
            'status': 'error',
            'message': '请提供比较参数'
        }), 400
    
    distributions = data.get('distributions', [])
    packages_json = data.get('packages_json')
    
    if not distributions or len(distributions) < 2:
        return jsonify({
            'status': 'error',
            'message': '请提供至少两个发行版进行比较'
        }), 400
    
    if not packages_json:
        return jsonify({
            'status': 'error',
            'message': '请提供包含软件包列表的JSON文件'
        }), 400

    for dist in distributions:
        if dist not in DISTRIBUTIONS:
            return jsonify({
                'status': 'error',
                'message': f'不支持的发行版: {dist}'
            }), 400

    packages_json_path = os.path.join(COMPARISON_DIR, packages_json)
    if not os.path.exists(packages_json_path):
        return jsonify({
            'status': 'error',
            'message': f'未找到软件包列表文件: {packages_json}'
        }), 404

    try:
        output_file = os.path.join(COMPARISON_DIR, "patch_comparison_report.json")
        result = compare_patches_between_distros(
            distributions, 
            packages_json_path,
            output_file
        )
        
        return jsonify({
            'status': 'success',
            'message': '补丁比较完成',
            'data': {
                'report_url': f'/comparison/patch_comparison_report.json',
                'summary': {
                    'compared_distributions': distributions,
                    'total_packages': len(result) if result else 0
                }
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'补丁比较失败: {str(e)}'
        }), 500

@app.route('/comparison/<path:filename>')
def serve_comparison_file(filename):
    """提供比较结果文件"""
    return send_from_directory(COMPARISON_DIR, filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)