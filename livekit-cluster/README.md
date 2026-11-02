# LiveKit Cluster Deployment for VCOS

Production-ready LiveKit cluster with HA, recording, ingress/egress, and autoscaling.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        HAProxy (Load Balancer)                   │
│                    Port 443/80 + WebSocket Upgrade               │
└─────────────────────────┬───────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   ┌─────────┐       ┌─────────┐       ┌─────────┐
   │LiveKit 1│       │LiveKit 2│       │LiveKit 3│  ← StatefulSet (3 replicas)
   │Port 7880│       │Port 7880│       │Port 7880│
   └────┬────┘       └────┬────┘       └────┬────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
              ┌─────────────────────────┐
              │      Redis Cluster       │  ← Sentinel HA (3 nodes)
              │   (PubSub + Session)     │
              └───────────┬─────────────┘
                          ▼
              ┌─────────────────────────┐
              │    PostgreSQL Cluster    │  ← Primary + Replicas
              │   (Rooms, Recordings)    │
              └─────────────────────────┘
```

## Components

| Component | Replicas | Purpose |
|-----------|----------|---------|
| LiveKit Server | 3 | WebRTC signaling, room management |
| LiveKit Egress | 2 | Stream out (RTMP, HLS, file) |
| LiveKit Ingress | 2 | Stream in (WHIP, RTMP, SRT) |
| LiveKit Recorder | 2 | Record meetings to file/S3 |
| LiveKit SIP | 1 | PSTN integration |
| Redis Cluster | 3 (Sentinel) | PubSub, sessions, clustering |
| PostgreSQL | 1+ replicas | Persistent storage |
| Coturn | 2 | TURN/STUN for NAT traversal |
| HAProxy | 2 | Load balancer with sticky sessions |
| Prometheus + Grafana | 1 | Monitoring & alerting |

## Quick Start

### Development
```bash
cd D:\vcos1\workspace\vcos\livekit-cluster
docker-compose up -d
```

### Production (Kubernetes)
```bash
cd D:\vcos1\workspace\vcos\livekit-cluster\k8s

# Apply namespace and RBAC
kubectl apply -f namespace.yaml

# Apply secrets (update values first!)
kubectl create secret generic livekit-secrets -n livekit \
  --from-literal=redis-password="your-redis-password" \
  --from-literal=postgres-password="your-postgres-password" \
  --from-literal=aws-access-key="your-aws-key" \
  --from-literal=aws-secret-key="your-aws-secret" \
  --from-literal=api-key="your-api-key" \
  --from-literal=api-secret="your-api-secret" \
  --from-literal=turn-password="your-turn-password" \
  --from-literal=turn-secret="your-turn-secret" \
  --from-literal=srt-passphrase="your-srt-passphrase"

# Deploy LiveKit cluster
kubectl apply -f livekit-statefulset.yaml
kubectl apply -f egress-deployment.yaml
kubectl apply -f ingress-deployment.yaml
kubectl apply -f recorder-deployment.yaml
kubectl apply -f hpa.yaml
kubectl apply -f monitoring-rules.yaml
```

## Configuration

All configuration in `config/` directory:
- `livekit.yaml` - Main server config
- `egress.yaml` - Streaming out config
- `ingress.yaml` - Streaming in config
- `sip.yaml` - SIP/PSTN config
- `turnserver.conf` - Coturn TURN/STUN

## Monitoring

- **Prometheus**: http://prometheus:9090
- **Grafana**: http://grafana:3000 (admin/admin)
- **HAProxy Stats**: http://haproxy:8404/stats
- **LiveKit Metrics**: :9090/metrics on each component

## Key Features Implemented

| Feature | Status |
|---------|--------|
| HA LiveKit Server (3 replicas) | ✅ |
| Redis Sentinel HA | ✅ |
| PostgreSQL HA | ✅ |
| HAProxy with sticky sessions | ✅ |
| LiveKit Egress (RTMP, HLS, S3) | ✅ |
| LiveKit Ingress (WHIP, RTMP, SRT) | ✅ |
| Recording (local + S3) | ✅ |
| Coturn TURN/STUN with ephemeral creds | ✅ |
| HPA for all components | ✅ |
| Prometheus + Grafana monitoring | ✅ |
| Alerting rules | ✅ |
| Chaos engineering scripts | ✅ |
| Load testing scripts | ✅ |

## Scaling

| Component | Min | Max | Trigger |
|-----------|-----|-----|---------|
| LiveKit Server | 3 | 20 | CPU > 70%, Connections > 1500/pod |
| Egress | 2 | 10 | CPU > 60%, Queue > 5 |
| Ingress | 2 | 10 | CPU > 60%, Sessions > 20/pod |
| Recorder | 2 | 10 | CPU > 60%, Recordings > 3/pod |

## Testing

### Chaos Engineering
```bash
# Run all chaos experiments
./scripts/chaos-engineering.sh all

# Run specific experiment
./scripts/chaos-engineering.sh pod-kill
./scripts/chaos-engineering.sh network-partition
./scripts/chaos-engineering.sh cpu-stress
./scripts/chaos-engineering.sh load-test
```

### Load Testing
```bash
# Run all load tests
./scripts/load-test.sh all

# Run specific test
./scripts/load-test.sh baseline
./scripts/load-test.sh stress
./scripts/load-test.sh extreme
./scripts/load-test.sh quality
./scripts/load-test.sh recording
./scripts/load-test.sh egress
```

## API Integration

### Create Room
```bash
curl -X POST https://api.vcos.io/api/v1/livekit/rooms \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "meeting-room-1", "empty_timeout": 300, "max_participants": 100}'
```

### Start Egress
```bash
curl -X POST https://api.vcos.io/api/v1/livekit/egress \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "room_name": "meeting-room-1",
    "output": {
      "type": "rtmp",
      "rtmp": {
        "url": "rtmp://a.rtmp.youtube.com/live2/STREAM_KEY",
        "video": {"bitrate": "5000k", "framerate": 30, "width": 1920, "height": 1080},
        "audio": {"bitrate": "128k", "sample_rate": 48000, "channels": 2}
      }
    }
  }'
```

### Start Ingress
```bash
curl -X POST https://api.vcos.io/api/v1/livekit/ingress \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "rtmp://ingest.example.com/live/stream",
    "room_name": "ingress-room",
    "transcoding": {"enabled": true}
  }'
```

### Start Recording
```bash
curl -X POST https://api.vcos.io/api/v1/livekit/recordings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "room_name": "meeting-room-1",
    "output": {"type": "s3", "s3": {"bucket": "vcos-recordings", "region": "us-east-1"}}
  }'
```

## Security Checklist

- [ ] Update all default passwords in secrets
- [ ] Configure TLS certificates (Let's Encrypt or custom)
- [ ] Configure firewall rules (allow 7880, 7881, 50000-60000 UDP)
- [ ] Enable RBAC in Kubernetes
- [ ] Configure network policies
- [ ] Enable audit logging
- [ ] Set up backup for PostgreSQL and recordings
- [ ] Configure DNS for livekit.vcos.io, turn.vcos.io
- [ ] Set up external monitoring (Datadog, New Relic, etc.)

## Troubleshooting

### High Latency
```bash
# Check WebSocket latency
kubectl exec -n livekit deploy/livekit-server -- curl -s localhost:9090/metrics | grep ws_message_latency

# Check Redis latency
redis-cli --latency -h redis-cluster
```

### Connection Drops
```bash
# Check HAProxy logs
kubectl logs -n livekit deploy/haproxy

# Check WebSocket upgrade
curl -v -H "Upgrade: websocket" -H "Connection: Upgrade" http://livekit.vcos.io/ws/crdt/test
```

### Recording Failures
```bash
# Check recorder logs
kubectl logs -n livekit -l app=livekit-recorder

# Check S3 permissions
aws s3 ls s3://vcos-recordings/
```

## Support

- LiveKit Docs: https://docs.livekit.io/
- VCOS API: https://api.vcos.io/docs
- Issues: https://github.com/vcos/livekit-cluster/issues

## License

MIT License - VCOS Project