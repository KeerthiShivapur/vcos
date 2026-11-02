with open('app/intelligence/canonical_digital_twin_service.py', 'rb') as f:
    content = f.read()

# Add the global instance at the end
old_end = b'Global instance'
new_end = b'Global instance\ncanonical_digital_twin_service = CanonicalDigitalTwinService()'

if old_end in content:
    content = content.replace(old_end, new_end)
    with open('app/intelligence/canonical_digital_twin_service.py', 'wb') as f:
        f.write(content)
    print('Added global instance')
else:
    print('Pattern not found')
    # Debug
    idx = content.rfind(b'Global instance')
    print(content[idx:idx+50])