with open('app/models/company_actions.py', 'rb') as f:
    content = f.read()

idx = content.find(b'class CompanyAction')
if idx >= 0:
    with open('output_action.txt', 'wb') as out:
        out.write(content[idx:idx+2000])
    print('Written')