with open('tests/acceptance/test_complete_company_e2e.py', 'r') as f:
    content = f.read()

# Find the if __name__ == '__main__': block
main_start = content.find('if __name__ == "__main__":')
print(f'main_start: {main_start}')

# Find the class start
class_start = content.find('class TestE2EJourneyIntegration:')
print(f'class_start: {class_start}')

# Find the actual class end - should be right before main
# Search backwards from main_start for class end
idx = content.rfind('    @pytest.mark.asyncio', class_start, main_start)
print(f'last pytest.mark.asyncio: {idx}')

# Find the end of that method
next_method = content.find('\n    async def test_', idx + 1)
if next_method == -1 or next_method > main_start:
    # Find the end of the class - should be before main
    for i in range(main_start - 1, class_start, -1):
        if content[i] == '\n' and i + 1 < len(content):
            next_char = content[i + 1]
            if next_char not in ' \t\n':
                print(f'Class ends at: {i + 1}')
                print(repr(content[i-50:i+50]))
                break