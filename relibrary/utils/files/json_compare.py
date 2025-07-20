import json
import logging
from relibrary.utils.files.file_operations import load_json, save_json

def compare_json_objects(json1, json2):

    diff = {}

    for key in json1:
        if key not in json2:
            diff[key] = {'status': 'only_in_json1', 'value': json1[key]}
        elif json1[key] != json2[key]:
            diff[key] = {'status': 'different', 'json1_value': json1[key], 'json2_value': json2[key]}

    for key in json2:
        if key not in json1:
            diff[key] = {'status': 'only_in_json2', 'value': json2[key]}

    return diff

def compare_json_files(file1, file2, output_file=None):
 
    json1 = load_json(file1)
    if json1 is None:
        return None
    
    json2 = load_json(file2)
    if json2 is None:
        return None
 
    diff = compare_json_objects(json1, json2)

    if output_file:
        save_json(diff, output_file)
    
    return diff

def summarize_diff(diff):
    summary = {
        'only_in_json1': 0,
        'only_in_json2': 0,
        'different': 0,
        'total_keys': len(diff)
    }
    
    different_keys = []
    only_in_json1_keys = []
    only_in_json2_keys = []
    
    for key, info in diff.items():
        status = info.get('status')
        if status == 'only_in_json1':
            summary['only_in_json1'] += 1
            only_in_json1_keys.append(key)
        elif status == 'only_in_json2':
            summary['only_in_json2'] += 1
            only_in_json2_keys.append(key)
        elif status == 'different':
            summary['different'] += 1
            different_keys.append(key)
    
    summary['different_keys'] = different_keys
    summary['only_in_json1_keys'] = only_in_json1_keys
    summary['only_in_json2_keys'] = only_in_json2_keys
    
    return summary

if __name__ == "__main__":

    file1 = "patch_comparison_report_v1.json"
    file2 = "patch_comparison_report_v2.json"
    output_file = "diff.json"
    
    diff = compare_json_files(file1, file2, output_file)
    if diff:
        summary = summarize_diff(diff)