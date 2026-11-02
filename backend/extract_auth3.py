with open('app/models/execution_strategy.py', 'rb') as f:
    content = f.read()

idx = content.find(b'class CompanyAuthorization')
if idx >= 0:
    with open('output_auth3.txt', 'wb') as out:
        out.write(content[idx:idx+2000])
    print('Written')