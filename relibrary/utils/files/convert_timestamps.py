import json
import datetime
import re
from dateutil import parser

def convert_timestamp(timestamp):
    # 如果已经是ISO格式，直接返回
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$', timestamp):
        return timestamp
    
    try:
        # 尝试解析时间戳
        dt = parser.parse(timestamp)
        # 转换为ISO格式
        return dt.isoformat()
    except:
        print(f"无法解析时间戳: {timestamp}")
        return timestamp

def process_json_file(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    def convert_dict(d):
        for key, value in d.items():
            if isinstance(value, dict):
                convert_dict(value)
            elif isinstance(value, str):
                # 检查是否是时间戳格式
                if re.match(r'^[A-Za-z]{3}\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4}\s+[+-]\d{4}$', value) or \
                   re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$', value):
                    d[key] = convert_timestamp(value)
    
    convert_dict(data)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

if __name__ == '__main__':
    input_file = 'data/patches/fo_introduced_times.json'
    output_file = 'data/patches/fo_introduced_times_converted.json'
    process_json_file(input_file, output_file)
    print("转换完成！") 