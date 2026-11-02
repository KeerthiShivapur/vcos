# VCOS WebSocket Gateway

Standalone, horizontally scalable WebSocket gateway for VCOS real-time collaboration features.

## Features

- **Horizontal Scaling**: Multiple gateway instances with Redis PubSub synchronization
- **Sticky Sessions**: HAProxy with source IP affinity for WebSocket connections
- **Multi-protocol**: CRDT documents, WebRTC signaling, Presence
- **Rate Limiting**: Token bucket algorithm with Redis backend
- **Monitoring**: Prometheus metrics, Grafana dashboards, HAProxy stats
- **TURN/STUN**: Coturn server for NAT traversal
- **Health Checks**: Liveness/readiness probes for Kubernetes

## Architecture

```
                    ┌─────────────────┐
                    │    HAProxy      │
                    │  (Port 8000)    │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
   ┌─────────┐          ┌─────────┐          ┌─────────┐
   │Gateway 1│          │Gateway 2│          │Gateway 3│
   │Port 8001│          │Port 8001│          │Port 8001│
   └────┬────┘          └────┬────┘          └────┬────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                    ┌────────▼────────┐
                    │     Redis       │
                    │  (PubSub + RL)  │
                    └─────────────────┘
```

## Quick Start

### Development
```bash
cd D:\vcos1\workspace\vcos\websocket-gateway
docker-compose up -d
```

### Production
```bash
cd D:\vcos1\workspace\vcos\websocket-gateway
docker-compose -f docker-compose.yml up -d
```

## Configuration

Edit `config.yaml` for:
- Server settings (host, port, workers)
- Redis connection
- PubSub channels
- WebSocket timeouts
- JWT authentication
- Rate limiting
- Metrics/Tracing

## API Endpoints

### WebSocket Connections
- `ws://host:8000/ws/crdt/{document_id}?token=JWT` - CRDT document collaboration
- `ws://host:8000/ws/signaling/{call_id}?token=JWT` - WebRTC signaling
- `ws://host:8000/ws/presence/{organization_id}?token=JWT` - Presence updates

### REST API
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics

## WebSocket Message Formats

### CRDT Messages
```json
{
  "type": "operation",
  "payload": { "operation": {...} },
  "request_id": "optional"
}
{
  "type": "awareness",
  "payload": { "cursor": {...}, "selection": {...}, "status": "online" }
}
{
  "type": "sync",
  "payload": {}
}
```

### Signaling Messages
```json
{
  "type": "offer",
  "payload": { "sdp": "...", "target": "user-id" }
}
{
  "type": "answer",
  "payload": { "sdp": "..." }
}
{
  "type": "ice_candidate",
  "payload": { "candidate": "...", "target": "user-id" }
}
```

### Presence Messages
```json
{
  "type": "awareness",
  "payload": { "cursor": {"x": 100, "y": 200}, "status": "online" }
}
{
  "type": "status",
  "payload": { "status": "idle" }
}
```

## Authentication

JWT tokens must be passed as query parameter `token` or header `Authorization: Bearer <token>`.

Required claims:
- `sub` / `user_id` - User identifier
- `org_id` / `organization_id` - Organization identifier
- `exp` - Expiration timestamp
- `iat` - Issued at timestamp

## Rate Limiting

Default limits:
- Connections: 100 req/s, burst 200
- Messages: 1000 req/s, burst 1000

Configure in `config.yaml` under `rate_limit`.

## Monitoring

### Prometheus Metrics
Available at `GET /metrics` on port 9091.

Key metrics:
- `ws_active_connections` - Active connections by type
- `ws_messages_total` - Message throughput
- `ws_message_latency_seconds` - Message processing latency
- `ws_errors_total` - Error rates
- `ws_pubsub_latency_seconds` - PubSub delivery latency

### Grafana Dashboard
Import `grafana/dashboards/websocket-gateway.json` for pre-built dashboard.

### HAProxy Stats
Available at `http://localhost:8404/stats` (auth: admin/password).

## TURN/STUN Server

Coturn server runs on ports:
- 3478 (TCP/UDP) - TURN/STUN
- 5349 (TCP) - TURNS (TLS)
- 49152-65535 UDP - Media relay

Configure in `turnserver.conf`.

## Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vcos-websocket-gateway
  namespace: vcos
spec:
  replicas: 3
  selector:
    matchLabels:
      app: vcos-websocket-gateway
  template:
    metadata:
      labels:
        app: vcos-websocket-gateway
    spec:
      containers:
      - name: gateway
        image: vcos/websocket-gateway:latest
        ports:
        - containerPort: 8001
        - containerPort: 9091
        env:
        - name: REDIS_HOST
          value: "redis.vcos.svc.cluster.local"
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: vcos-secrets
              key: jwt-secret
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 20
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 10
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: vcos-websocket-gateway
  namespace: vcos
spec:
  type: ClusterIP
  ports:
  - port: 8001
    targetPort: 8001
    name: websocket
  - port: 9091
    targetPort: 9091
    name: metrics
  selector:
    app: vcos-websocket-gateway
```

## Scaling

Horizontal scaling is automatic with:
1. Multiple gateway replicas
2. Redis PubSub for cross-instance messaging
3. HAProxy sticky sessions (source IP)
4. Redis-backed connection state

Target: 5000 concurrent connections per gateway instance.

## Troubleshooting

### High Connection Count
- Check `ws_active_connections` metric
- Verify HAProxy sticky sessions working
- Check Redis connection count

### High Latency
- Check `ws_message_latency_seconds` metric
- Check Redis latency with `redis-cli --latency`
- Check network between gateways and Redis

### Connection Drops
- Check HAProxy logs for 502/503 errors
- Verify WebSocket upgrade headers
- Check ping/pong intervals (default 25s/20s)

### Rate Limiting
- Check `ws_rate_limited_total` metric
- Adjust `rate_limit` in config.yaml
- Check Redis keys: `vcos:ws:ratelimit:*`

## License

MIT License - VCOS Project