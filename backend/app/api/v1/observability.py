from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from typing import Optional

from app.core.observability import (
    observability, logger, get_logger, get_observability,
    MetricType, AlertSeverity, SLI, SLO, AlertRule, Alert,
    get_observability
)
from app.api.deps import get_current_user
from app.models.organization import Organization
from app.models.user import User


router = APIRouter(prefix="/observability", tags=["observability"])


class MetricResponse(BaseModel):
    counters: Dict[str, float]
    gauges: Dict[str, float]
    histograms: Dict[str, Dict]
    summaries: Dict[str, Dict]


class SLIResponse(BaseModel):
    name: str
    description: str
    query: str
    target: float
    window: str
    labels: Dict[str, str]
    current_value: Optional[float] = None
    status: str = "unknown"


class SLOResponse(BaseModel):
    name: str
    description: str
    sli: SLIResponse
    target: float
    window: str
    alert_threshold: float
    error_budget_policy: Dict
    current_value: Optional[float] = None
    error_budget_remaining: Optional[float] = None
    status: str = "unknown"


class AlertRuleCreate(BaseModel):
    name: str
    description: str
    query: str
    condition: str
    threshold: float
    severity: str
    labels: Dict[str, str] = {}
    annotations: Dict[str, str] = {}
    for_duration: str = "5m"
    interval: str = "1m"
    enabled: bool = True


class AlertRuleResponse(BaseModel):
    id: str
    name: str
    description: str
    query: str
    condition: str
    threshold: float
    severity: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    for_duration: str
    interval: str
    enabled: bool


class AlertResponse(BaseModel):
    id: str
    rule_id: str
    name: str
    severity: str
    status: str
    starts_at: datetime
    ends_at: Optional[datetime]
    generator_url: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    fingerprint: str


class MetricsQuery(BaseModel):
    metric_names: List[str]
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    labels: Dict[str, str] = {}
    aggregation: str = "sum"
    interval: str = "1m"


@router.get("/metrics", response_model=Dict)
async def get_metrics(
    current_user: User = Depends(get_current_user),
):
    return observability.metrics_data


@router.post("/metrics/query")
async def query_metrics(
    query: MetricsQuery,
    current_user: User = Depends(get_current_user),
):
    return {"data": "query results would be here"}


@router.get("/sli", response_model=List[SLIResponse])
async def list_slis(
    current_user: User = Depends(get_current_user),
):
    return []


@router.post("/sli", status_code=status.HTTP_201_CREATED)
async def create_sli(
    sli: SLI,
    current_user: User = Depends(get_current_user),
):
    return {"success": True, "sli_name": sli.name}


@router.get("/slo", response_model=List[SLOResponse])
async def list_slos(
    current_user: User = Depends(get_current_user),
):
    return []


@router.post("/slo", status_code=status.HTTP_201_CREATED)
async def create_slo(
    slo: SLO,
    current_user: User = Depends(get_current_user),
):
    return {"success": True, "slo_name": slo.name}


@router.get("/slo/check", response_model=List[Dict])
async def check_slos(
    current_user: User = Depends(get_current_user),
):
    return await observability.check_slos()


@router.get("/alerts", response_model=List[AlertResponse])
async def list_alerts(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    alerts = observability.get_active_alerts()
    
    if status:
        alerts = [a for a in alerts if a.status == status]
    if severity:
        alerts = [a for a in alerts if a.severity == severity]
    
    return [
        AlertResponse(
            id=a.id,
            rule_id=a.rule_id,
            name=a.name,
            severity=a.severity,
            status=a.status,
            starts_at=a.starts_at,
            ends_at=a.ends_at,
            generator_url=a.generator_url,
            labels=a.labels,
            annotations=a.annotations,
            fingerprint=a.fingerprint,
        )
        for a in alerts[:limit]
    ]


@router.get("/alerts/history", response_model=List[AlertResponse])
async def get_alert_history(
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    history = observability.get_alert_history(limit)
    return [
        AlertResponse(
            id=a.id,
            rule_id=a.rule_id,
            name=a.name,
            severity=a.severity,
            status=a.status,
            starts_at=a.starts_at,
            ends_at=a.ends_at,
            generator_url=a.generator_url,
            labels=a.labels,
            annotations=a.annotations,
            fingerprint=a.fingerprint,
        )
        for a in history
    ]


@router.get("/alerts/rules", response_model=List[AlertRuleResponse])
async def list_alert_rules(
    current_user: User = Depends(get_current_user),
):
    return [
        AlertRuleResponse(
            id=rule.id,
            name=rule.name,
            description=rule.description,
            query=rule.query,
            condition=rule.condition,
            threshold=rule.threshold,
            severity=rule.severity,
            labels=rule.labels,
            annotations=rule.annotations,
            for_duration=rule.for_duration,
            interval=rule.interval,
            enabled=rule.enabled,
        )
        for rule in observability.alerts.rules.values()
    ]


@router.post("/alerts/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    rule: AlertRuleCreate,
    current_user: User = Depends(get_current_user),
):
    rule = AlertRule(
        id=str(uuid.uuid4()),
        name=rule.name,
        description=rule.description,
        query=rule.query,
        condition=rule.condition,
        threshold=rule.threshold,
        severity=rule.severity,
        labels=rule.labels,
        annotations=rule.annotations,
        for_duration=rule.for_duration,
        interval=rule.interval,
        enabled=rule.enabled,
    )
    observability.add_alert_rule(rule)
    
    return AlertRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        query=rule.query,
        condition=rule.condition,
        threshold=rule.threshold,
        severity=rule.severity,
        labels=rule.labels,
        annotations=rule.annotations,
        for_duration=rule.for_duration,
        interval=rule.interval,
        enabled=rule.enabled,
    )


@router.get("/alerts/rules/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
):
    if rule_id not in observability.alerts.rules:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    
    rule = observability.alerts.rules[rule_id]
    return AlertRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        query=rule.query,
        condition=rule.condition,
        threshold=rule.threshold,
        severity=rule.severity,
        labels=rule.labels,
        annotations=rule.annotations,
        for_duration=rule.for_duration,
        interval=rule.interval,
        enabled=rule.enabled,
    )


@router.patch("/alerts/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: str,
    updates: Dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    if rule_id not in observability.alerts.rules:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    
    rule = observability.alerts.rules[rule_id]
    for key, value in updates.items():
        if hasattr(rule, key):
            setattr(rule, key, value)
    
    return AlertRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        query=rule.query,
        condition=rule.condition,
        threshold=rule.threshold,
        severity=rule.severity,
        labels=rule.labels,
        annotations=rule.annotations,
        for_duration=rule.for_duration,
        interval=rule.interval,
        enabled=rule.enabled,
    )


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
):
    observability.remove_alert_rule(rule_id)
    return {"success": True}


@router.post("/alerts/{fingerprint}/resolve")
async def resolve_alert(
    fingerprint: str,
    current_user: User = Depends(get_current_user),
):
    observability.alerts.active_alerts.pop(fingerprint, None)
    return {"success": True}


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    current_user: User = Depends(get_current_user),
):
    trace = observability.tracer.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {"trace_id": trace_id, "spans": trace}


@router.get("/traces/active")
async def get_active_traces(
    current_user: User = Depends(get_current_user),
):
    return {"traces": observability.tracer.get_active_spans()}


@router.get("/logs")
async def get_logs(
    level: Optional[str] = Query(None),
    logger_name: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    return {"logs": list(observability.log_buffer)[-limit:]}


@router.post("/metrics/increment")
async def increment_counter(
    name: str = Body(...),
    value: float = Body(1.0),
    labels: Dict[str, str] = Body({}),
    current_user: User = Depends(get_current_user),
):
    observability.increment_counter(name, value, labels)
    return {"success": True}


@router.post("/metrics/gauge")
async def set_gauge(
    name: str = Body(...),
    value: float = Body(...),
    labels: Dict[str, str] = Body({}),
    current_user: User = Depends(get_current_user),
):
    observability.set_gauge(name, value, labels)
    return {"success": True}


@router.post("/metrics/histogram")
async def record_histogram(
    name: str = Body(...),
    value: float = Body(...),
    labels: Dict[str, str] = Body({}),
    current_user: User = Depends(get_current_user),
):
    observability.record_histogram(name, value, labels)
    return {"success": True}


@router.post("/metrics/summary")
async def record_summary(
    name: str = Body(...),
    value: float = Body(...),
    labels: Dict[str, str] = Body({}),
    current_user: User = Depends(get_current_user),
):
    observability.record_summary(name, value, labels)
    return {"success": True}


@router.post("/alerts/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    rule: AlertRuleCreate,
    current_user: User = Depends(get_current_user),
):
    rule = AlertRule(
        id=str(uuid.uuid4()),
        name=rule.name,
        description=rule.description,
        query=rule.query,
        condition=rule.condition,
        threshold=rule.threshold,
        severity=rule.severity,
        labels=rule.labels,
        annotations=rule.annotations,
        for_duration=rule.for_duration,
        interval=rule.interval,
        enabled=rule.enabled,
    )
    observability.add_alert_rule(rule)
    
    return AlertRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        query=rule.query,
        condition=rule.condition,
        threshold=rule.threshold,
        severity=rule.severity,
        labels=rule.labels,
        annotations=rule.annotations,
        for_duration=rule.for_duration,
        interval=rule.interval,
        enabled=rule.enabled,
    )


@router.get("/alerts/rules", response_model=List[AlertRuleResponse])
async def list_alert_rules(
    current_user: User = Depends(get_current_user),
):
    return [
        AlertRuleResponse(
            id=rule.id,
            name=rule.name,
            description=rule.description,
            query=rule.query,
            condition=rule.condition,
            threshold=rule.threshold,
            severity=rule.severity,
            labels=rule.labels,
            annotations=rule.annotations,
            for_duration=rule.for_duration,
            interval=rule.interval,
            enabled=rule.enabled,
        )
        for rule in observability.alerts.rules.values()
    ]


@router.get("/alerts/rules/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
):
    if rule_id not in observability.alerts.rules:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    
    rule = observability.alerts.rules[rule_id]
    return AlertRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        query=rule.query,
        condition=rule.condition,
        threshold=rule.threshold,
        severity=rule.severity,
        labels=rule.labels,
        annotations=rule.annotations,
        for_duration=rule.for_duration,
        interval=rule.interval,
        enabled=rule.enabled,
    )


@router.patch("/alerts/rules/{rule_id}")
async def update_alert_rule(
    rule_id: str,
    updates: Dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    if rule_id not in observability.alerts.rules:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    
    rule = observability.alerts.rules[rule_id]
    for key, value in updates.items():
        if hasattr(rule, key):
            setattr(rule, key, value)
    
    return {"success": True}


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
):
    observability.remove_alert_rule(rule_id)
    return {"success": True}


@router.post("/alerts/{fingerprint}/resolve")
async def resolve_alert(
    fingerprint: str,
    current_user: User = Depends(get_current_user),
):
    observability.alerts.active_alerts.pop(fingerprint, None)
    return {"success": True}


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    current_user: User = Depends(get_current_user),
):
    trace = observability.tracer.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {"trace_id": trace_id, "spans": trace}


@router.get("/traces/active")
async def get_active_traces(
    current_user: User = Depends(get_current_user),
):
    return {"traces": observability.tracer.get_active_spans()}


@router.get("/logs")
async def get_logs(
    level: Optional[str] = Query(None),
    logger_name: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    logs = list(observability.log_buffer)
    
    if level:
        logs = [l for l in logs if l["level"] == level]
    if logger_name:
        logs = [l for l in logs if l.get("logger") == logger_name]
    if start_time:
        logs = [l for l in logs if l["timestamp"] >= start_time.isoformat()]
    if end_time:
        logs = [l for l in logs if l["timestamp"] <= end_time.isoformat()]
    
    return {"logs": logs[-limit:]}