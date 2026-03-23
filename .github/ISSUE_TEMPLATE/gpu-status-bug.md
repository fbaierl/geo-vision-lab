---
name: Bug Report
description: Report a UI bug where GPU status is incorrectly displayed
title: "[BUG] Top panel always shows 'CPU ONLY' even when GPU is running"
labels: ["bug", "ui", "gpu"]
---

## Bug Description

The top panel status indicator always displays "CPU ONLY" even when the GPU is actively running and engaged. This is a UI bug that misleads users about the actual hardware acceleration status.

## Expected Behavior

The status panel should accurately reflect the GPU state:
- **"GPU Active"** - When a model is loaded and using GPU acceleration (VRAM > 0)
- **"GPU Standby"** - When GPU is available but no model is currently loaded (idle)
- **"CPU Only"** - When GPU is not available or not configured

## Current Behavior

The panel shows "CPU ONLY" in all cases where `gpu_engaged` is false, except when `reason === 'no_model_loaded'`. This causes incorrect display when:
- Ollama reports `size_vram: 0` even with GPU available
- Model is loaded but not actively using VRAM

## Root Cause Analysis

### Backend (`app/api/routes/health.py`)
The `/system/status` endpoint queries Ollama's `/api/ps` endpoint and returns:
```python
{
    "gpu_engaged": vram_bytes > 0,
    "reason": "gpu" if vram_bytes > 0 else "cpu_only"
}
```

**Problem**: Ollama returns `size_vram: 0` when the model is loaded but not using GPU acceleration, even if a GPU is physically present and configured.

### Frontend (`static/index.html` lines 877-885)
The display logic is:
```javascript
if (data.gpu_engaged) {
    gpuStatus.textContent = 'GPU Active';
} else if (data.reason === 'no_model_loaded') {
    gpuStatus.textContent = 'GPU Standby';
} else {
    gpuStatus.textContent = 'CPU Only';  // BUG: Shows for ANY non-gpu_engaged state
}
```

**Problem**: The logic doesn't distinguish between "GPU available but idle" vs "GPU unavailable".

## Proposed Solution

### 1. Enhanced Backend GPU Detection

Update `app/api/routes/health.py` to:
- Check if NVIDIA GPU is available at the system level
- Distinguish between three states:
  - **GPU Active**: Model loaded with VRAM > 0
  - **GPU Standby**: GPU available but no model loaded
  - **CPU Only**: GPU not available/configured

Example implementation:
```python
@router.get("/system/status")
async def system_status():
    """Return system status including GPU engagement from Ollama."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/ps")
            data = resp.json()
            models = data.get("models", [])
            
            if models:
                model_info = models[0]
                vram_bytes = model_info.get("size_vram", 0)
                return {
                    "gpu_engaged": vram_bytes > 0,
                    "gpu_available": True,  # GPU is configured
                    "model": model_info.get("name", "unknown"),
                    "reasoning_model": settings.REASONING_LLM_MODEL_NAME,
                    "reviewer_model": settings.REVIEWER_LLM_MODEL_NAME,
                    "vram_bytes": vram_bytes,
                    "reason": "gpu" if vram_bytes > 0 else "gpu_standby",
                }
            
            # No model currently loaded - check if GPU is available
            # Try to detect GPU availability
            gpu_available = await check_gpu_availability()
            return {
                "gpu_engaged": False,
                "gpu_available": gpu_available,
                "model": None,
                "reasoning_model": settings.REASONING_LLM_MODEL_NAME,
                "reviewer_model": settings.REVIEWER_LLM_MODEL_NAME,
                "vram_bytes": 0,
                "reason": "gpu_standby" if gpu_available else "cpu_only",
            }
    except Exception as e:
        return {
            "gpu_engaged": False,
            "gpu_available": False,
            "model": None,
            "reasoning_model": settings.REASONING_LLM_MODEL_NAME,
            "reviewer_model": settings.REVIEWER_LLM_MODEL_NAME,
            "vram_bytes": 0,
            "reason": str(e),
        }
```

### 2. Updated Frontend Logic

Update `static/index.html` to handle the new response format:
```javascript
if (data.gpu_engaged) {
    gpuPill.className = 'status-pill gpu-active';
    gpuStatus.textContent = 'GPU Active';
} else if (data.gpu_available || data.reason === 'gpu_standby') {
    gpuPill.className = 'status-pill gpu-standby';
    gpuStatus.textContent = 'GPU Standby';
} else {
    gpuPill.className = 'status-pill gpu-inactive';
    gpuStatus.textContent = 'CPU Only';
}
```

## Files to Modify

1. `app/api/routes/health.py` - Enhanced GPU detection logic
2. `static/index.html` - Fixed status display logic (lines 868-892)
3. `tests/test_rag.py` - Update tests for new status values

## Testing Checklist

- [ ] GPU status shows "GPU Active" when Ollama is using GPU (VRAM > 0)
- [ ] GPU status shows "GPU Standby" when GPU available but idle
- [ ] GPU status shows "CPU Only" only when GPU truly unavailable
- [ ] Status updates correctly when switching between models
- [ ] Status handles Ollama service restart gracefully

## Environment

- **OS**: Linux with NVIDIA GPU
- **Docker**: With NVIDIA Container Toolkit
- **Ollama**: Latest version with Qwen 3.5 models
- **Browser**: Any modern browser

## Additional Context

This bug affects user confidence in the system's GPU acceleration. Users may incorrectly believe GPU is not working when it actually is, leading to unnecessary troubleshooting or suboptimal performance configurations.
