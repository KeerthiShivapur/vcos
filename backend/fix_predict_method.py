import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the predict call to use derive_predictions
old_predict = '''        prediction = await predictive_intelligence_service.predict(
            db=db_session,
            organization_id=org.id
        )'''

new_predict = '''        # Use derive_predictions with a system caller
        from app.intelligence.company_context import CallerAccess
        system_caller = CallerAccess(
            organization_id=org.id,
            user_id="system",
            employee_id="system",
            org_wide=True,
        )
        prediction = await predictive_intelligence_service.derive_predictions(
            db=db_session,
            caller=system_caller,
        )'''

if old_predict in content:
    content = content.replace(old_predict, new_predict)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed predict call to derive_predictions')
else:
    print('Pattern not found')