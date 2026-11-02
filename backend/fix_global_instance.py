import codecs

with codecs.open('app/intelligence/canonical_digital_twin_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add the global instance at the end
old_end = '# Global instance\n'

new_end = '''# Global instance
canonical_digital_twin_service = CanonicalDigitalTwinService()'''

if old_end in content:
    content = content.replace(old_end, new_end)
    with codecs.open('app/intelligence/canonical_digital_twin_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added global instance')
else:
    print('Pattern not found')