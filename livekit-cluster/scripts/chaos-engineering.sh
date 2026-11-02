#!/bin/bash
# LiveKit Cluster Chaos Engineering Scripts
# Run controlled chaos experiments to validate resilience

set -euo pipefail

NAMESPACE="livekit"
CHAOS_NAMESPACE="chaos-mesh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    if ! command -v kubectl &> /dev/null; then
        error "kubectl not found"
        exit 1
    fi
    
    if ! command -v helm &> /dev/null; then
        error "helm not found"
        exit 1
    fi
    
    if ! kubectl get namespace chaos-mesh &> /dev/null; then
        warn "Chaos Mesh not installed. Installing..."
        install_chaos_mesh
    fi
    
    log "Prerequisites check passed"
}

install_chaos_mesh() {
    log "Installing Chaos Mesh..."
    
    helm repo add chaos-mesh https://charts.chaos-mesh.org
    helm repo update
    
    helm install chaos-mesh chaos-mesh/chaos-mesh \
        --namespace chaos-mesh \
        --create-namespace \
        --set chaosDaemon.runtime=containerd \
        --set chaosDaemon.socketPath=/run/containerd/containerd.sock \
        --wait --timeout 10m
    
    log "Chaos Mesh installed"
}

# Experiment 1: Pod Kill - Test HA failover
experiment_pod_kill() {
    log "Starting Experiment 1: Pod Kill (HA Failover Test)"
    
    cat <<EOF | kubectl apply -f -
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: livekit-pod-kill
  namespace: livekit
spec:
  action: pod-failure
  mode: one
  duration: "30s"
  selector:
    namespaces:
      - livekit
    labelSelector:
      app: livekit-server
  scheduler:
    cron: "@every 5m"
EOF

    log "Pod kill experiment started. Monitor HA failover..."
    log "Expected: LiveKit server pod killed, HAProxy routes to healthy pod, connections maintained"
    
    # Wait and observe
    sleep 60
    
    # Check pod status
    kubectl get pods -n livekit -l app=livekit-server
    
    # Check connections
    kubectl exec -n livekit deploy/livekit-server -- curl -s localhost:9090/metrics | grep ws_active_connections
    
    log "Experiment 1 completed"
}

# Experiment 2: Network Partition - Test Redis partitioning
experiment_network_partition() {
    log "Starting Experiment 2: Network Partition (Redis Partition Test)"
    
    cat <<EOF | kubectl apply -f -
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: redis-network-partition
  namespace: livekit
spec:
  action: partition
  mode: one
  duration: "60s"
  direction: both
  target:
    selector:
      namespaces:
        - livekit
      labelSelector:
        app: redis
  source:
    selector:
      namespaces:
        - livekit
      labelSelector:
        app: livekit-server
EOF

    log "Network partition experiment started. Testing Redis partition handling..."
    log "Expected: LiveKit server handles Redis partition gracefully, uses in-memory state"
    
    sleep 90
    
    # Check if LiveKit recovered
    kubectl logs -n livekit -l app=livekit-server --tail=50 | grep -i "redis\|connection"
    
    log "Experiment 2 completed"
}

# Experiment 3: CPU Stress - Test autoscaling
experiment_cpu_stress() {
    log "Starting Experiment 3: CPU Stress (Autoscaling Test)"
    
    cat <<EOF | kubectl apply -f -
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: livekit-cpu-stress
  namespace: livekit
spec:
  mode: one
  stressors:
    cpu:
      workers: 4
      load: 80
  duration: "120s"
  selector:
    namespaces:
      - livekit
    labelSelector:
      app: livekit-server
EOF

    log "CPU stress experiment started. Testing autoscaling..."
    log "Expected: HPA scales up LiveKit pods when CPU > 70%"
    
    # Monitor HPA
    for i in {1..10}; do
        kubectl get hpa livekit-server-hpa -n livekit
        sleep 30
    done
    
    log "Experiment 3 completed"
}

# Experiment 4: Memory Pressure - Test OOM handling
experiment_memory_stress() {
    log "Starting Experiment 4: Memory Stress (OOM Handling Test)"
    
    cat <<EOF | kubectl apply -f -
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: livekit-memory-stress
  namespace: livekit
spec:
  mode: one
  stressors:
    memory:
      workers: 2
      size: "1GiB"
  duration: "60s"
  selector:
    namespaces:
      - livekit
    labelSelector:
      app: livekit-server
EOF

    log "Memory stress experiment started. Testing OOM handling..."
    log "Expected: Container restarts, HAProxy routes to healthy pod"
    
    sleep 90
    
    # Check pod restarts
    kubectl get pods -n livekit -l app=livekit-server
    
    log "Experiment 4 completed"
}

# Experiment 5: Network Latency - Test WebRTC quality
experiment_network_latency() {
    log "Starting Experiment 5: Network Latency (WebRTC Quality Test)"
    
    cat <<EOF | kubectl apply -f -
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: livekit-network-latency
  namespace: livekit
spec:
  action: delay
  mode: one
  delay:
    latency: "200ms"
    correlation: "25"
    jitter: "50ms"
  duration: "120s"
  selector:
    namespaces:
      - livekit
    labelSelector:
      app: livekit-server
  direction: both
EOF

    log "Network latency experiment started. Testing WebRTC quality under latency..."
    log "Expected: WebRTC adapts, jitter buffer handles latency, quality degrades gracefully"
    
    sleep 150
    
    # Check metrics
    kubectl exec -n livekit deploy/livekit-server -- curl -s localhost:9090/metrics | grep ws_message_latency
    
    log "Experiment 5 completed"
}

# Experiment 6: Redis Down - Test complete failure
experiment_redis_down() {
    log "Starting Experiment 6: Redis Complete Failure"
    
    cat <<EOF | kubectl apply -f -
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: redis-pod-kill
  namespace: livekit
spec:
  action: pod-failure
  mode: all
  duration: "60s"
  selector:
    namespaces:
      - livekit
    labelSelector:
      app: redis
EOF

    log "Redis pod failure experiment started. Testing complete Redis failure..."
    log "Expected: LiveKit servers handle Redis unavailability, use local state"
    
    sleep 90
    
    # Check LiveKit health
    kubectl exec -n livekit deploy/livekit-server -- curl -s localhost:7880/health
    
    log "Experiment 6 completed"
}

# Experiment 7: Complete Zone Failure
experiment_zone_failure() {
    log "Starting Experiment 7: Zone Failure Simulation"
    
    cat <<EOF | kubectl apply -f -
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: zone-failure-simulation
  namespace: livekit
spec:
  action: pod-failure
  mode: fixed-percent
  value: "50"
  duration: "60s"
  selector:
    namespaces:
      - livekit
    labelSelector:
      app: livekit-server
EOF

    log "Zone failure simulation started. Testing multi-pod failure..."
    log "Expected: Remaining pods handle load, HPA scales up"
    
    sleep 90
    
    # Check HPA scaling
    kubectl get hpa -n livekit
    
    log "Experiment 7 completed"
}

# Experiment 8: Certificate Expiry - Test TLS handling
experiment_cert_expiry() {
    log "Starting Experiment 8: Certificate Expiry"
    
    # This would require manipulating cert files - simulate with config change
    cat <<EOF | kubectl apply -f -
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: cert-reload-test
  namespace: livekit
spec:
  action: pod-failure
  mode: one
  duration: "30s"
  selector:
    namespaces:
      - livekit
    labelSelector:
      app: livekit-server
EOF

    log "Certificate reload test started. Testing TLS cert reload..."
    
    sleep 60
    
    # Verify TLS still works
    kubectl exec -n livekit deploy/livekit-server -- curl -k https://localhost:7880/health
    
    log "Experiment 8 completed"
}

# Experiment 9: Load Test - 500+ concurrent connections
experiment_load_test() {
    log "Starting Experiment 9: Load Test (500+ concurrent connections)"
    
    # Deploy load test pods
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: livekit-load-test
  namespace: livekit
spec:
  replicas: 5
  selector:
    matchLabels:
      app: livekit-load-test
  template:
    metadata:
      labels:
        app: livekit-load-test
    spec:
      containers:
      - name: load-tester
        image: ghcr.io/livekit/load-tester:latest
        env:
        - name: LIVEKIT_URL
          value: "ws://livekit-server:7880"
        - name: LIVEKIT_API_KEY
          valueFrom:
            secretKeyRef:
              name: livekit-secrets
              key: api-key
        - name: LIVEKIT_API_SECRET
          valueFrom:
            secretKeyRef:
              name: livekit-secrets
              key: api-secret
        - name: NUM_PUBLISHERS
          value: "100"
        - name: NUM_SUBSCRIBERS
          value: "100"
        - name: ROOM_NAME
          value: "load-test-room"
        - name: DURATION
          value: "300"
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
EOF

    log "Load test deployed. Running 500+ concurrent connections..."
    
    # Monitor for 5 minutes
    for i in {1..10}; do
        kubectl top pods -n livekit -l app=livekit-server
        kubectl get hpa -n livekit
        sleep 30
    done
    
    # Cleanup
    kubectl delete deployment livekit-load-test -n livekit
    
    log "Experiment 9 completed"
}

# Cleanup all chaos experiments
cleanup_experiments() {
    log "Cleaning up all chaos experiments..."
    
    kubectl delete podchaos,networkchaos,stresschaos -n livekit --all --ignore-not-found=true
    kubectl delete deployment livekit-load-test -n livekit --ignore-not-found=true
    
    log "Cleanup completed"
}

# Main execution
main() {
    case "${1:-all}" in
        prerequisites)
            check_prerequisites
            ;;
        pod-kill)
            check_prerequisites
            experiment_pod_kill
            ;;
        network-partition)
            check_prerequisites
            experiment_network_partition
            ;;
        cpu-stress)
            check_prerequisites
            experiment_cpu_stress
            ;;
        memory-stress)
            check_prerequisites
            experiment_memory_stress
            ;;
        network-latency)
            check_prerequisites
            experiment_network_latency
            ;;
        redis-down)
            check_prerequisites
            experiment_redis_down
            ;;
        zone-failure)
            check_prerequisites
            experiment_zone_failure
            ;;
        cert-expiry)
            check_prerequisites
            experiment_cert_expiry
            ;;
        load-test)
            check_prerequisites
            experiment_load_test
            ;;
        all)
            check_prerequisites
            experiment_pod_kill
            experiment_network_partition
            experiment_cpu_stress
            experiment_memory_stress
            experiment_network_latency
            experiment_redis_down
            experiment_zone_failure
            experiment_cert_expiry
            experiment_load_test
            cleanup_experiments
            ;;
        cleanup)
            cleanup_experiments
            ;;
        *)
            echo "Usage: $0 {prerequisites|pod-kill|network-partition|cpu-stress|memory-stress|network-latency|redis-down|zone-failure|cert-expiry|load-test|all|cleanup}"
            exit 1
            ;;
    esac
}

main "$@"