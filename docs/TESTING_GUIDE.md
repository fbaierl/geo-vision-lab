# GeoVision Lab — Testing Guide

This guide explains how to run tests correctly and avoid common permission issues.

---

## Quick Start (Recommended)

**Use the helper script** — it handles permissions automatically:

```bash
# Run all tests
./scripts/test.sh

# Run specific test file
./scripts/test.sh tests/test_reasoning_tools.py

# Run with pytest arguments
./scripts/test.sh tests/ -v --cov=app
```

---

## Manual Testing

### Prerequisites

1. **Activate the virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

2. **Ensure dependencies are installed:**
   ```bash
   pip install -r requirements.txt
   ```

---

## ⚠️ Common Issue: Permission Denied Errors

If you see errors like:
```
PytestCacheWarning: cache could not write path ... Permission denied
[Errno 13] Permission denied: '__pycache__/...'
```

This happens because cache directories were created by Docker containers running as `root`.

### Solution: Fix Permissions

Run these commands **before** running tests:

```bash
# Fix ownership of cache directories
sudo chown -R $USER:$USER .pytest_cache __pycache__ app/__pycache__ 2>/dev/null

# Or remove them entirely (they will be regenerated)
sudo rm -rf .pytest_cache __pycache__ app/__pycache__
```

---

## Running Tests

### Prerequisites

1. **Activate the virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

2. **Ensure dependencies are installed:**
   ```bash
   pip install -r requirements.txt
   ```

### Test Commands

#### Run All Tests
```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

#### Run Specific Test File
```bash
source .venv/bin/activate
python -m pytest tests/test_reasoning_tools.py -v
```

#### Run Tests with Coverage
```bash
source .venv/bin/activate
python -m pytest tests/ --cov=app --cov-report=term-missing
```

#### Run Tests Without Cache (Clean Run)
```bash
source .venv/bin/activate
python -m pytest tests/ -v --cache-clear
```

---

## Test Structure

| Test File | Purpose |
|-----------|---------|
| `tests/test_reasoning_tools.py` | Tests for vector_search, web_search, duckduckgo_search tools |
| `tests/test_db_integration.py` | End-to-end database integration tests |

---

## Running Tests in Docker (Alternative)

If you prefer running tests in an isolated container environment:

```bash
docker compose run --rm app python -m pytest tests/ -v
```

This ensures a clean environment but is slower than local testing.

---

## Troubleshooting

### Issue: `pydantic_core.ValidationError: GPU_COUNT`

This happens when environment variables from Docker leak into your local environment.

**Solution:** Run tests without Docker environment variables:
```bash
unset GPU_COUNT
source .venv/bin/activate
python -m pytest tests/ -v
```

### Issue: Module Not Found Errors

**Solution:** Ensure you're using the virtual environment Python:
```bash
# Wrong
python -m pytest  # May use system Python

# Correct
.venv/bin/python -m pytest  # Uses venv Python
```

### Issue: Database Connection Errors

Some tests require PostgreSQL with pgvector. Either:

1. **Run Docker containers:**
   ```bash
   docker compose up postgres -d
   ```

2. **Or skip DB tests:**
   ```bash
   python -m pytest tests/ -v -k "not db_integration"
   ```

---

## Quick Reference

| Task | Command |
|------|---------|
| Fix permissions | `sudo chown -R $USER:$USER .pytest_cache __pycache__ app/__pycache__` |
| Clean cache | `rm -rf .pytest_cache __pycache__ app/__pycache__` |
| Run all tests | `source .venv/bin/activate && python -m pytest tests/ -v` |
| Run single file | `source .venv/bin/activate && python -m pytest tests/test_reasoning_tools.py -v` |
| Run with coverage | `source .venv/bin/activate && python -m pytest tests/ --cov=app` |
| Clean test run | `source .venv/bin/activate && python -m pytest tests/ -v --cache-clear` |

---

## For AI Agents

If you're an AI assistant working on this project, use the helper script:

```bash
./scripts/test.sh tests/ -v
```

Or run these commands manually:

```bash
# 1. Fix any permission issues from Docker
sudo chown -R $USER:$USER .pytest_cache __pycache__ app/__pycache__ 2>/dev/null || true

# 2. Activate venv
source .venv/bin/activate

# 3. Run tests with clean cache
python -m pytest tests/ -v --cache-clear
```

This prevents permission-related test failures.
