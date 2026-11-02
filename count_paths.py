import json
data = json.load(open(r'D:\vcos1\workspace\vcos\openapi.json'))
print(f'Total paths: {len(data["paths"])}')