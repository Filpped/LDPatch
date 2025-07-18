"""
文件操作工具模块，提供通用的文件读写功能
"""

import json
import logging
import os

def load_json(file_path):
    """
    读取JSON文件并返回内容
    
    Args:
        file_path: JSON文件路径
        
    Returns:
        dict: 加载的JSON数据
        
    Raises:
        Exception: 文件读取或解析出错时
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logging.info(f"成功加载JSON文件: {file_path}")
            return data
    except Exception as e:
        logging.error(f"读取JSON文件失败: {file_path} 错误: {e}")
        return None

def save_json(data, file_path, indent=4):
    """
    将数据保存为JSON文件
    
    Args:
        data: 要保存的数据
        file_path: 输出文件路径
        indent: JSON缩进空格数
        
    Returns:
        bool: 保存是否成功
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            logging.info(f"成功保存JSON文件: {file_path}")
        return True
    except Exception as e:
        logging.error(f"保存JSON文件失败: {file_path} 错误: {e}")
        return False

def file_exists(file_path):
    """
    检查文件是否存在
    
    Args:
        file_path: 文件路径
        
    Returns:
        bool: 文件是否存在
    """
    return os.path.isfile(file_path)

def ensure_dir(directory):
    """
    确保目录存在，如不存在则创建
    
    Args:
        directory: 目录路径
    """
    if not os.path.exists(directory):
        os.makedirs(directory)
        logging.info(f"创建目录: {directory}")

def get_file_content(file_path):
    """
    读取文件内容
    
    Args:
        file_path: 文件路径
        
    Returns:
        str: 文件内容，读取失败则返回None
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return content
    except Exception as e:
        logging.error(f"读取文件失败: {file_path} 错误: {e}")
        return None 