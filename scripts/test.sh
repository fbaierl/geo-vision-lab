#!/bin/bash
# GeoVision Lab - Test Runner Script
# This script handles permission issues and runs tests correctly

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "▸ GeoVision Lab — Test Runner"
echo "=============================="
echo ""

# Step 1: Fix permission issues from Docker
echo "[1/3] Fixing cache permissions..."
sudo chown -R $USER:$USER .pytest_cache __pycache__ app/__pycache__ app/*/__pycache__ 2>/dev/null || true
sudo chmod -R u+rwX .pytest_cache __pycache__ app/__pycache__ app/*/__pycache__ 2>/dev/null || true
echo "      ✓ Permissions fixed"

# Step 2: Check virtual environment
echo "[2/3] Checking virtual environment..."
if [ ! -f ".venv/bin/python" ]; then
    echo "      ✗ Virtual environment not found!"
    echo "      Creating virtual environment..."
    python3 -m venv .venv
    echo "      ✓ Virtual environment created"
fi
echo "      ✓ Virtual environment ready"

# Step 3: Run tests
echo "[3/3] Running tests..."
echo ""

# Parse arguments
TEST_ARGS="${@:-tests/}"

# Activate venv and run
source .venv/bin/activate
python -m pytest $TEST_ARGS --cache-clear

echo ""
echo "▸ Tests completed!"
