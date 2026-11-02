with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Remove traceback printing
content = content.replace(
    '''except Exception as e:
            await self.context.db.rollback()
            import traceback
            print(f'Exception in provision: {traceback.format_exc()}')
            return AdapterResult(success=False, error=str(e))''',
    '''except Exception as e:
            await self.context.db.rollback()
            return AdapterResult(success=False, error=str(e))'''
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Removed traceback printing')