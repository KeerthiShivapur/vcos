#!/bin/bash
# LiveKit Cluster Load Testing Script
# Tests WebRTC, signaling, and recording under load

set -euo pipefail

# Configuration
LIVEKIT_URL="${LIVEKIT_URL:-ws://livekit-server:7880}"
LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-your-api-key}"
LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-your-api-secret}"
ROOM_NAME="${ROOM_NAME:-load-test-room}"
NUM_PUBLISHERS="${NUM_PUBLISHERS:-100}"
NUM_SUBSCRIBERS="${NUM_SUBSCRIBERS:-100}"
DURATION="${DURATION:-300}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/livekit-load-test}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Function to run load test with LiveKit load tester
run_load_test() {
    local test_name=$1
    local publishers=$2
    local subscribers=$2
    local duration=$3
    
    log "Starting $test_name: $publishers publishers, $subscribers subscribers for ${duration}s"
    
    # Create room via API
    local room_resp=$(curl -s -X POST "https://api.vcos.io/api/v1/livekit/rooms" \
        -H "Authorization: Bearer $LIVEKIT_API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"$ROOM_NAME\", \"empty_timeout\": 300, \"max_participants\": 1000}")
    
    if [[ $? -ne 0 ]]; then
        error "Failed to create room"
        return 1
    fi
    
    # Run load test using LiveKit's load tester
    docker run --rm \
        --network host \
        -e LIVEKIT_URL="$LIVEKIT_URL" \
        -e LIVEKIT_API_KEY="$LIVEKIT_API_KEY" \
        -e LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" \
        -e ROOM_NAME="$ROOM_NAME" \
        -e NUM_PUBLISHERS=$publishers \
        -e NUM_SUBSCRIBERS=$subscribers \
        -e DURATION=$duration \
        -e VIDEO_SOURCE="synthetic" \
        -e VIDEO_WIDTH=1280 \
        -e VIDEO_HEIGHT=720 \
        -e VIDEO_FPS=30 \
        -e VIDEO_BITRATE=2500000 \
        -e AUDIO_BITRATE=128000 \
        ghcr.io/livekit/load-tester:latest \
        --publishers=$publishers \
        --subscribers=$subscribers \
        --duration=$duration \
        --room=$ROOM_NAME \
        --url=$LIVEKIT_URL \
        --api-key=$LIVEKIT_API_KEY \
        --api-secret=$LIVEKIT_API_SECRET \
        --video-source=synthetic \
        --video-width=1280 \
        --video-height=720 \
        --video-fps=30 \
        --video-bitrate=2500000 \
        --audio-bitrate=128000 \
        --output-dir=$OUTPUT_DIR/$test_name \
        2>&1 | tee $OUTPUT_DIR/$test_name.log
    
    local exit_code=${PIPESTATUS[0]}
    
    if [ $exit_code -eq 0 ]; then
        log "$test_name completed successfully"
    else
        error "$test_name failed with exit code $exit_code"
    fi
    
    return $exit_code
}

# Test 1: Baseline - 10 publishers, 10 subscribers
test_baseline() {
    run_load_test "baseline" 10 10 60
}

# Test 2: Scale up - 50 publishers, 50 subscribers
test_scale_up() {
    run_load_test "scale-50" 50 50 120
}

# Test 3: High load - 100 publishers, 100 subscribers
test_high_load() {
    run_load_test "high-load-100" 100 100 180
}

# Test 4: Stress - 200 publishers, 200 subscribers
test_stress() {
    run_load_test "stress-200" 200 200 300
}

# Test 5: Extreme - 500 publishers, 500 subscribers
test_extreme() {
    run_load_test "extreme-500" 500 500 600
}

# Test 6: Mixed - publishers != subscribers
test_mixed() {
    run_load_test "mixed-100pub-400sub" 100 400 180
}

# Test 7: Long duration - endurance test
test_endurance() {
    run_load_test "endurance-24h" 50 50 86400
}

# Test 8: Burst - rapid join/leave
test_burst() {
    log "Running burst test - rapid join/leave cycles"
    
    for i in {1..10}; do
        log "Burst cycle $i/10"
        
        # Rapid join
        docker run --rm --network host \
            -e LIVEKIT_URL="$LIVEKIT_URL" \
            -e LIVEKIT_API_KEY="$LIVEKIT_API_KEY" \
            -e LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" \
            -e ROOM_NAME="$ROOM_NAME-burst-$i" \
            -e NUM_PUBLISHERS=20 \
            -e NUM_SUBSCRIBERS=20 \
            -e DURATION=10 \
            ghcr.io/livekit/load-tester:latest \
            --publishers=20 --subscribers=20 --duration=10 \
            --url=$LIVEKIT_URL --api-key=$LIVEKIT_API_KEY --api-secret=$LIVEKIT_API_SECRET \
            --video-source=synthetic &
        
        sleep 2
    done
    
    wait
    log "Burst test completed"
}

# Test WebRTC quality under load
test_quality() {
    log "Running WebRTC quality test under load"
    
    docker run --rm --network host \
        -e LIVEKIT_URL="$LIVEKIT_URL" \
        -e LIVEKIT_API_KEY="$LIVEKIT_API_KEY" \
        -e LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" \
        -e ROOM_NAME="quality-test-room" \
        -e NUM_PUBLISHERS=10 \
        -e NUM_SUBSCRIBERS=10 \
        -e DURATION=120 \
        -e VIDEO_SOURCE="synthetic" \
        -e VIDEO_WIDTH=1920 \
        -e VIDEO_HEIGHT=1080 \
        -e VIDEO_FPS=30 \
        -e VIDEO_BITRATE=5000000 \
        -e AUDIO_BITRATE=128000 \
        -e ENABLE_QUALITY_METRICS=true \
        ghcr.io/livekit/load-tester:latest \
        --publishers=10 --subscribers=10 --duration=120 \
        --url=$LIVEKIT_URL --api-key=$LIVEKIT_API_KEY --api-secret=$LIVEKIT_API_SECRET \
        --video-source=synthetic \
        --video-width=1920 --video-height=1080 --video-fps=30 --video-bitrate=5000000 \
        --audio-bitrate=128000 \
        --enable-quality-metrics \
        --output-dir=$OUTPUT_DIR/quality-test \
        2>&1 | tee $OUTPUT_DIR/quality-test.log
}

# Test recording under load
test_recording() {
    log "Testing recording under load"
    
    # Enable auto-recording for the room
    curl -s -X POST "https://api.vcos.io/api/v1/livekit/rooms" \
        -H "Authorization: Bearer $LIVEKIT_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"name": "recording-test-room", "empty_timeout": 300, "max_participants": 200}' > /dev/null
    
    # Run load test with recording enabled
    docker run --rm --network host \
        -e LIVEKIT_URL="$LIVEKIT_URL" \
        -e LIVEKIT_API_KEY="$LIVEKIT_API_KEY" \
        -e LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" \
        -e ROOM_NAME="recording-test-room" \
        -e NUM_PUBLISHERS=50 \
        -e NUM_SUBSCRIBERS=50 \
        -e DURATION=180 \
        -e VIDEO_SOURCE="synthetic" \
        -e VIDEO_WIDTH=1280 \
        -e VIDEO_HEIGHT=720 \
        -e VIDEO_FPS=30 \
        -e VIDEO_BITRATE=2500000 \
        -e AUDIO_BITRATE=128000 \
        -e ENABLE_RECORDING=true \
        ghcr.io/livekit/load-tester:latest \
        --publishers=50 --subscribers=50 --duration=180 \
        --url=$LIVEKIT_URL --api-key=$LIVEKIT_API_KEY --api-secret=$LIVEKIT_API_SECRET \
        --video-source=synthetic --video-width=1280 --video-height=720 --video-fps=30 --video-bitrate=2500000 \
        --audio-bitrate=128000 --enable-recording \
        --output-dir=$OUTPUT_DIR/recording-test \
        2>&1 | tee $OUTPUT_DIR/recording-test.log
    
    # Check recording outputs
    ls -la $OUTPUT_DIR/recording-test/
}

# Test Egress under load
test_egress() {
    log "Testing egress (streaming out) under load"
    
    # Create egress request via API
    curl -s -X POST "https://api.vcos.io/api/v1/livekit/egress" \
        -H "Authorization: Bearer $LIVEKIT_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{
            "room_name": "egress-test-room",
            "output": {
                "type": "rtmp",
                "rtmp": {
                    "url": "rtmp://localhost:1935/live/test",
                    "video": {"bitrate": "2500k", "framerate": 30, "width": 1280, "height": 720},
                    "audio": {"bitrate": "128k", "sample_rate": 48000, "channels": 2}
                }
            }
        }' > /dev/null
    
    # Run load test with egress
    run_load_test "egress-test" 20 20 120
}

# Test SIP integration
test_sip() {
    log "Testing SIP integration"
    
    # This would require a SIP trunk - placeholder for now
    warn "SIP test requires SIP trunk configuration - skipping"
}

# Generate report
generate_report() {
    log "Generating load test report..."
    
    cat > $OUTPUT_DIR/report.md <<EOF
# LiveKit Load Test Report

**Test Date:** $(date)
**LiveKit URL:** $LIVEKIT_URL
**Room:** $ROOM_NAME

## Test Results

| Test | Publishers | Subscribers | Duration | Status |
|------|------------|-------------|----------|--------|
| Baseline | 10 | 10 | 60s | $([ -f $OUTPUT_DIR/baseline.log ] && echo "PASS" || echo "FAIL") |
| Scale 50 | 50 | 50 | 120s | $([ -f $OUTPUT_DIR/scale-50.log ] && echo "PASS" || echo "FAIL") |
| High Load 100 | 100 | 100 | 180s | $([ -f $OUTPUT_DIR/high-load-100.log ] && echo "PASS" || echo "FAIL") |
| Stress 200 | 200 | 200 | 300s | $([ -f $OUTPUT_DIR/stress-200.log ] && echo "PASS" || echo "FAIL") |
| Extreme 500 | 500 | 500 | 600s | $([ -f $OUTPUT_DIR/extreme-500.log ] && echo "PASS" || echo "FAIL") |
| Mixed 100/400 | 100 | 400 | 180s | $([ -f $OUTPUT_DIR/mixed-100pub-400sub.log ] && echo "PASS" || echo "FAIL") |
| Burst Test | 20x10 | 20x10 | 10s x10 | $([ -f $OUTPUT_DIR/burst.log ] && echo "PASS" || echo "FAIL") |
| Quality Test | 10 | 10 | 120s | $([ -f $OUTPUT_DIR/quality-test.log ] && echo "PASS" || echo "FAIL") |
| Recording Test | 50 | 50 | 180s | $([ -f $OUTPUT_DIR/recording-test.log ] && echo "PASS" || echo "FAIL") |
| Egress Test | 20 | 20 | 120s | $([ -f $OUTPUT_DIR/egress-test.log ] && echo "PASS" || echo "FAIL") |

## Key Metrics

### Connection Success Rate
$(grep -h "connection_success" $OUTPUT_DIR/*.log 2>/dev/null | tail -5 || echo "N/A")

### Message Latency (p50/p95/p99)
$(grep -h "latency" $OUTPUT_DIR/*.log 2>/dev/null | tail -5 || echo "N/A")

### Bandwidth Usage
$(grep -h "bandwidth" $OUTPUT_DIR/*.log 2>/dev/null | tail -5 || echo "N/A")

### Error Rates
$(grep -h "error" $OUTPUT_DIR/*.log 2>/dev/null | wc -l || echo "0") errors total

## Observations

$(cat $OUTPUT_DIR/observations.txt 2>/dev/null || echo "No observations recorded")

## Recommendations

1. Monitor connection count at scale
2. Monitor message latency percentiles
3. Monitor egress/recording resource usage
4. Configure HPA thresholds based on observed metrics

---
*Report generated on $(date)*
EOF

    log "Report generated: $OUTPUT_DIR/report.md"
}

# Main function
main() {
    case "${1:-all}" in
        baseline)
            test_baseline
            ;;
        scale)
            test_scale_up
            ;;
        high-load)
            test_high_load
            ;;
        stress)
            test_stress
            ;;
        extreme)
            test_extreme
            ;;
        mixed)
            test_mixed
            ;;
        endurance)
            test_endurance
            ;;
        burst)
            test_burst
            ;;
        quality)
            test_quality
            ;;
        recording)
            test_recording
            ;;
        egress)
            test_egress
            ;;
        sip)
            test_sip
            ;;
        all)
            test_baseline
            test_scale_up
            test_high_load
            test_stress
            test_extreme
            test_mixed
            test_burst
            test_quality
            test_recording
            test_egress
            generate_report
            ;;
        report)
            generate_report
            ;;
        *)
            echo "Usage: $0 {baseline|scale|high-load|stress|extreme|mixed|endurance|burst|quality|recording|egress|sip|all|report}"
            exit 1
            ;;
    esac
}

main "$@"