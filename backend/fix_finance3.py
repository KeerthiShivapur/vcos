import re

with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Find the FinanceAdapter class
class_start = content.find('class FinanceAdapter')
if class_start >= 0:
    # Find the next class
    next_class = content.find('class ', class_start + 20)
    if next_class < 0:
        next_class = len(content)
    finance_class = content[class_start:next_class]
    
    # Use regex to replace the provision method
    pattern = r'(            try:.*?except Exception as e:.*?return AdapterResult\(success=False, error=str\(e\)\))'
    replacement = '''            try:
                budgets = await self._create_budgets()
                vendors = await self._create_vendors()
                purchase_orders = await self._create_purchase_orders(vendors)
                await self.context.db.commit()
                return AdapterResult(
                    success=True,
                    data={
                        "budgets": [b.id for b in budgets],
                        "vendors": [v.id for v in vendors],
                        "purchase_orders": [po.id for po in purchase_orders],
                    },
                    invariants_verified=[
                        "PROPERTY_1_TENANT_OWNERSHIP",
                        "PROPERTY_5_PROVENANCE_VALID"
                    ]
                )
            except Exception as e:
                await self.context.db.rollback()
                return AdapterResult(success=False, error=str(e))'''
    
    new_finance_class = re.sub(pattern, replacement, finance_class, flags=re.DOTALL)
    
    if new_finance_class != finance_class:
        content = content[:class_start] + new_finance_class + content[class_start + len(finance_class):]
        with open('tests/acceptance/adapters.py', 'w') as f:
            f.write(content)
        print('Replaced provision method')
    else:
        print('Pattern not found')
else:
    print('FinanceAdapter class not found')