#!/bin/bash
# Quick test script for OpenSentry - SMV Snapshot Mode

set -e

echo "========================================="
echo "OpenSentry - SMV Snapshot Mode Test"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test functions
check_command() {
    if command -v $1 &> /dev/null; then
        echo -e "${GREEN}✓${NC} $1 is installed"
        return 0
    else
        echo -e "${RED}✗${NC} $1 is not installed"
        return 1
    fi
}

test_api() {
    local endpoint=$1
    local expected_code=$2
    local description=$3

    echo -n "Testing $description... "

    response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000${endpoint})

    if [ "$response" = "$expected_code" ]; then
        echo -e "${GREEN}✓${NC} (HTTP $response)"
        return 0
    else
        echo -e "${RED}✗${NC} (Expected $expected_code, got $response)"
        return 1
    fi
}

# Check prerequisites
echo "1. Checking prerequisites..."
check_command docker || { echo "Please install Docker first"; exit 1; }
check_command docker-compose || check_command docker compose || { echo "Please install Docker Compose"; exit 1; }
echo ""

# Check if container is running
echo "2. Checking if OpenSentry container is running..."
if docker ps | grep -q "opensentry"; then
    echo -e "${GREEN}✓${NC} Container is running"
else
    echo -e "${YELLOW}!${NC} Container not found. Starting snapshot mode..."
    docker compose -f compose-snapshot.yaml up -d
    echo "Waiting 30 seconds for startup..."
    sleep 30
fi
echo ""

# Check container logs
echo "3. Checking container logs for snapshot mode..."
if docker logs opensentry-snapshot 2>&1 | grep -q "SNAPSHOT MODE"; then
    echo -e "${GREEN}✓${NC} Snapshot mode is active"
else
    echo -e "${YELLOW}!${NC} Could not confirm snapshot mode in logs"
fi
echo ""

# Test health endpoint
echo "4. Testing API endpoints..."
test_api "/health" "200" "Health check"
test_api "/api/snapshots/list" "200" "Snapshot list API"
test_api "/api/snapshots/latest" "200" "Latest snapshot API"
test_api "/video_feed" "503" "Video streaming (should be disabled)"
echo ""

# Check snapshot directory
echo "5. Checking snapshot storage..."
if [ -d "./snapshots" ]; then
    snapshot_count=$(find ./snapshots -name "*.jpg" 2>/dev/null | wc -l)
    echo -e "${GREEN}✓${NC} Snapshot directory exists"
    echo "  Found $snapshot_count snapshots"

    if [ $snapshot_count -gt 0 ]; then
        latest_snapshot=$(ls -t ./snapshots/*.jpg 2>/dev/null | head -1)
        echo "  Latest: $(basename $latest_snapshot)"
    else
        echo -e "${YELLOW}!${NC} No snapshots found yet (may need to wait for first capture)"
    fi
else
    echo -e "${YELLOW}!${NC} Snapshot directory not found"
fi
echo ""

# Check resource usage
echo "6. Checking resource usage..."
if command -v docker stats &> /dev/null; then
    echo "CPU and Memory usage (5 second sample):"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" opensentry-snapshot 2>/dev/null | tail -1
    echo ""

    cpu_usage=$(docker stats --no-stream --format "{{.CPUPerc}}" opensentry-snapshot 2>/dev/null | sed 's/%//')
    if (( $(echo "$cpu_usage < 30" | bc -l) )); then
        echo -e "${GREEN}✓${NC} CPU usage is within expected range for snapshot mode"
    else
        echo -e "${YELLOW}!${NC} CPU usage is higher than expected (may be warming up)"
    fi
fi
echo ""

# Test web UI
echo "7. Testing web UI..."
if curl -s http://localhost:5000 | grep -q "Latest Snapshot"; then
    echo -e "${GREEN}✓${NC} Snapshot gallery UI is accessible"
else
    echo -e "${YELLOW}!${NC} Could not verify snapshot gallery UI"
fi
echo ""

# Summary
echo "========================================="
echo "Test Summary"
echo "========================================="
echo ""
echo "If all tests passed, OpenSentry - SMV is working correctly!"
echo ""
echo "Access the snapshot gallery at:"
echo "  http://localhost:5000"
echo ""
echo "Default credentials:"
echo "  Username: admin"
echo "  Password: admin"
echo ""
echo "To view logs:"
echo "  docker logs -f opensentry-snapshot"
echo ""
echo "To stop:"
echo "  docker compose -f compose-snapshot.yaml down"
echo ""
