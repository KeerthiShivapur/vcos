with open('app/intelligence/canonical_integration_service.py', 'rb') as f:
    content = f.read()

idx = content.find(b'"""Get user')
if idx >= 0:
    chunk = content[idx:idx+200]
    # Count double quotes
    dq_positions = [i for i, b in enumerate(chunk) if b == 0x22]
    print('Double quote positions:', dq_positions)
    print('Total double quotes in chunk:', len(dq_positions))
    
    # Check the exact structure
    print('First 60 bytes ascii:', chunk[:60])
    print('Last 60 bytes ascii:', chunk[-60:])
    
    # Check if opening and closing triple quotes match
    # Should have 3 at start, 3 at end
    start_quotes = chunk[:3]
    end_quotes = chunk[-3:]
    print('Start quotes:', start_quotes)
    print('End quotes:', end_quotes)
    print('Start == b\"\"\"\"?', start_quotes == b'"""')
    print('End == b\"\"\"\"?', end_quotes == b'"""')