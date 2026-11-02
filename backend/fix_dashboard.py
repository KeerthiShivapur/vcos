with open('app/services/observability_service.py', 'r') as f:
    content = f.read()

# Fix the get_alert_dashboard method
old = '''        # Get correlations
        correlations = {}
        for alert in alerts:
            corrs = self._alert_engine.get_correlations(alert.id)
            if corrs:
                correlations[alert.id] = [
                    {
                        "correlated_alert_id": c.correlated_alert_id,
                        "type": c.correlation_type.value,
                        "confidence": c.confidence,
                    }
                    for c in corrs
                ]
        
        # Import AlertSeverity and AlertState lazily
            from app.services.alert_engine import AlertSeverity, AlertState
            return {
            "organization_id": organization_id,
            "total_alerts": len(alerts),
            "by_state": dict(by_state),
            "by_severity": {
                sev.value: len([a for a in alerts if a.severity == sev])
                for sev in AlertSeverity
            },
            "correlations": correlations,
            "active_aler'''

new = '''        # Get correlations
        correlations = {}
        for alert in alerts:
            corrs = self._alert_engine.get_correlations(alert.id)
            if corrs:
                correlations[alert.id] = [
                    {
                        "correlated_alert_id": c.correlated_alert_id,
                        "type": c.correlation_type.value,
                        "confidence": c.confidence,
                    }
                    for c in corrs
                ]
        
        # Import AlertSeverity and AlertState lazily
        from app.services.alert_engine import AlertSeverity, AlertState
        return {
            "organization_id": organization_id,
            "total_alerts": len(alerts),
            "by_state": dict(by_state),
            "by_severity": {
                sev.value: len([a for a in alerts if a.severity == sev])
                for sev in AlertSeverity
            },
            "correlations": correlations,
            "active_aler'''

content = content.replace(old, new)

with open('app/services/observability_service.py', 'w') as f:
    f.write(content)
print('Done')