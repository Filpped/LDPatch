import json
import logging
import os

def load_json(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        return None

def save_json(data, file_path, indent=4):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except Exception as e:
        return False

def file_exists(file_path):
    return os.path.isfile(file_path)

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def get_file_content(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return content
    except Exception as e:
        return None 