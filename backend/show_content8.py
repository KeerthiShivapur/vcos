with open('benchmarks/gate35d_query_plans.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('for i in range(sizes["knowledge"])')
if idx != -1:
    end_idx = content.find('\n\n', idx)
    if end_idx == -1:
        end_idx = idx + 300
    print(repr(content[idx:end_idx]))