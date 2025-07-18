import json
import csv

def json_to_csv(json_file, csv_file, fields=None):
    """
    将 JSON 文件转换为 CSV 文件
    :param json_file: 输入的 JSON 文件路径
    :param csv_file: 输出的 CSV 文件路径
    :param fields: 指定的字段列表（如果为 None，将自动使用 JSON 的所有键作为字段）
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)  
        if fields is None:
            if isinstance(data, dict):
                fields = list(next(iter(data.values())).keys())
            elif isinstance(data, list):
                fields = list(data[0].keys())
            else:
                raise ValueError("JSON 数据格式不支持转换为 CSV")

        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
  
            if isinstance(data, dict):
                for key, value in data.items():
                    writer.writerow(value)
            elif isinstance(data, list):
                for item in data:
                    writer.writerow(item)

        print(f"CSV 文件已生成：{csv_file}")
    except Exception as e:
        print(f"转换失败：{e}")

def main():
    json_file = input("请输入 JSON 文件的路径：").strip()
 
    if not json_file.endswith(".json"):
        print("请输入有效的 JSON 文件路径（以 .json 结尾）。")
        return
   
    csv_file = input("请输入输出 CSV 文件的路径（包括文件名）：").strip()

    if not csv_file.endswith(".csv"):
        print("请输入有效的 CSV 文件路径（以 .csv 结尾）。")
        return

    json_to_csv(json_file, csv_file)

if __name__ == "__main__":
    main()
