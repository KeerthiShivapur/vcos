with open('app/intelligence/cohort_builder.py', 'rb') as f:
    content = f.read()
    for i, byte in enumerate(content):
        if byte < 32 and byte not in (9, 10, 13):  # control chars except tab, newline, CR
            print(f'Pos {i}: byte={byte} ({chr(byte) if byte < 128 else "?"})')
            # Show context
            start = max(0, i-20)
            end = min(len(content), i+20)
            print(f'  Context: {content[start:end]!r}')