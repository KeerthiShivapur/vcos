with open('D:/vcos1/workspace/vcos/backend/app/core/ocsf_siem.py', 'r') as f:
    content = f.read()

# Fix the scan_record inner function to be async
old_code = '''        def scan_value(value: Any, field_path: str):
            if isinstance(value, str):
                matches = await self.scan_content(value, {**context, "field_name": field_path})
                if matches:
                    results[field_path] = matches
            elif isinstance(value, dict):
                for k, v in value.items():
                    scan_value(v, f"{field_path}.{k}" if field_path else k)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    scan_value(item, f"{field_path}[{i}]")

        for field_name, value in record.items():
            scan_value(value, field_name)'''

new_code = '''        async def scan_value(value: Any, field_path: str):
            if isinstance(value, str):
                matches = await self.scan_content(value, {**context, "field_name": field_path})
                if matches:
                    results[field_path] = matches
            elif isinstance(value, dict):
                for k, v in value.items():
                    await scan_value(v, f"{field_path}.{k}" if field_path else k)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    await scan_value(item, f"{field_path}[{i}]")

        for field_name, value in record.items():
            await scan_value(value, field_name)'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('D:/vcos1/workspace/vcos/backend/app/core/ocsf_siem.py', 'w') as f:
        f.write(content)
    print('Fixed scan_record')
else:
    print('Pattern not found')