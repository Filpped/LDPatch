import json
import csv

def json_to_csv(json_file, csv_file, fields=None):
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)  
        if fields is None:
            if isinstance(data, dict):
                fields = list(next(iter(data.values())).keys())
            elif isinstance(data, list):
                fields = list(data[0].keys())
            else:
                raise ValueError("error")

        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
  
            if isinstance(data, dict):
                for key, value in data.items():
                    writer.writerow(value)
            elif isinstance(data, list):
                for item in data:
                    writer.writerow(item)

    except Exception as e:
        print("error")

def main():
    json_file = input("Json_file：").strip()
 
    if not json_file.endswith(".json"):
        return
   
    csv_file = input("csv_file：").strip()

    if not csv_file.endswith(".csv"):
        return

    json_to_csv(json_file, csv_file)

if __name__ == "__main__":
    main()
