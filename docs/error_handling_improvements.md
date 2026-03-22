# Error Handling Improvements

## Summary

This document describes the error handling improvements made to make the agent flow more robust and provide better user feedback when errors occur.

## Changes Made

### 1. Frontend Error Display (`static/index.html`, `static/style.css`)

#### New Error Event Types
- **`error`**: General errors from any tool or service
- **`location_error`**: Specific errors from location extraction

#### UI Components
- **`addReasoningError()`** function: Displays errors in the Reasoning window
  - Shows tool name and error message
  - Red background with amber accent
  - Full error text in expandable content area

- **Error handling in stream processor**:
  - General errors displayed in chat AND reasoning window
  - Location errors show warning in maps legend
  - Maps loading indicator hidden on error

#### Styling
- New `.reasoning-step.phase-error` class
- Red border with light red background
- Error content styled for readability

### 2. Location Extractor Robustness (`app/services/location_extractor.py`)

#### Rate Limiting Handling
- **Exponential backoff**: 3 retries with increasing delays (2s, 4s, 6s)
- **Error tracking**: `geocoding_errors` list tracks all failures
- **Graceful degradation**: Returns empty list instead of raising exceptions
- **Detailed error messages**: Explains rate limiting and suggests self-hosted solution

#### Self-Hosted Nominatim Support
- **Environment variable**: `NOMINATIM_URL` for custom endpoint
- **Timeout configuration**: `NOMINATIM_TIMEOUT` (default: 10s)
- **Automatic fallback**: Uses public API if no custom URL configured

#### Error Categories
```python
GeocoderQuotaExceeded  # HTTP 429 - Rate limit
GeocoderTimedOut       # Timeout exceeded
GeocoderServiceError   # HTTP errors (502, 503, etc.)
```

### 3. Agent Flow Robustness (`app/agents/graph.py`)

#### Non-Failing Error Handling
- `extract_locations()` now **never raises exceptions**
- Returns empty list on failure (doesn't block entire flow)
- Errors logged for debugging
- Query response still delivered even if location extraction fails

#### Error Event Emission
```python
if not locations or len(locations) == 0:
    yield {
        "type": "location_error",
        "tool": "location_extractor",
        "content": "Location extraction completed but no locations were found..."
    }
```

#### Error Messages
User-friendly explanations for:
- No locations in text
- Rate limiting issues
- Service unavailability
- Continuation assurance ("query response is still valid")

### 4. Configuration (`.env.example`)

```bash
# Optional: Self-hosted Nominatim
NOMINATIM_URL=http://nominatim:8080/search
NOMINATIM_TIMEOUT=10
```

### 5. GitHub Issue Created

**File**: `.github/ISSUE_TEMPLATE/self-hosted-nominatim.md`

Complete implementation plan for self-hosted Nominatim including:
- Docker Compose configuration
- Resource requirements (8GB RAM recommended)
- Data import instructions
- Health checks
- Acceptance criteria

## Error Flow Examples

### Scenario 1: Rate Limiting (HTTP 429)

```
User Query: "What's happening in Iran?"
↓
Agent generates response
↓
Location Extractor finds "Iran", "Tehran", "Israel"
↓
Geocoding "Iran" → Success
Geocoding "Tehran" → Success  
Geocoding "Israel" → HTTP 429 (Rate limit)
  ↓
  Retry 1 (wait 2s) → HTTP 429
  Retry 2 (wait 4s) → HTTP 429
  Retry 3 (wait 6s) → HTTP 429
  ↓
  Error logged: "Nominatim rate limit exceeded"
  Error added to geocoding_errors list
  Returns [] for "Israel"
↓
Location Extractor returns: ["Iran", "Tehran"] (partial success)
↓
Frontend displays:
  - Map with Iran + Tehran markers
  - Error message in Reasoning window
  - Chat response delivered successfully
```

### Scenario 2: Complete Location Extraction Failure

```
User Query: "Explain quantum computing"
↓
Agent generates response (no locations mentioned)
↓
Location Extractor finds 0 locations
↓
Emits: {type: "location_error", content: "..."}
↓
Frontend displays:
  - Warning in Maps window: "⚠ Location extraction failed"
  - Error details in Reasoning window
  - Chat response delivered (no map)
```

## Benefits

### User Experience
- ✅ **No more silent failures** - users see what went wrong
- ✅ **Continued functionality** - errors don't block entire flow
- ✅ **Clear explanations** - error messages explain what happened
- ✅ **Visual feedback** - errors shown in context (Reasoning window)

### Developer Experience
- ✅ **Better debugging** - detailed error logging
- ✅ **Error tracking** - geocoding_errors list for analysis
- ✅ **Configurable** - environment variables for tuning
- ✅ **Migration path** - self-hosted Nominatim documented

### System Robustness
- ✅ **Graceful degradation** - partial success is OK
- ✅ **Retry logic** - transient errors handled automatically
- ✅ **Timeout protection** - no hanging requests
- ✅ **Cache protection** - failed requests cached to prevent retry storms

## Migration to Self-Hosted Nominatim

See `.github/ISSUE_TEMPLATE/self-hosted-nominatim.md` for complete implementation plan.

**Quick Start**:
```bash
# 1. Add to docker-compose.yml (see issue template)
# 2. Set environment variable:
echo "NOMINATIM_URL=http://nominatim:8080/search" >> .env

# 3. Restart stack
docker compose up -d nominatim
```

## Testing

### Test Rate Limiting Handling
```python
# Simulate multiple rapid requests
for i in range(20):
    extractor.geocode_location(f"test_location_{i}")
# Should see retries and graceful failure
```

### Test Error Display
1. Make query with many locations (triggers rate limiting)
2. Verify error appears in Reasoning window
3. Verify chat response still delivered
4. Verify partial map rendering (if some locations succeeded)

## Future Improvements

- [ ] Add error metrics/monitoring (count errors per type)
- [ ] Implement circuit breaker pattern for geocoding
- [ ] Add fallback geocoding service (e.g., Photon, Pelias)
- [ ] Cache warming on startup for common locations
- [ ] Rate limit prediction (avoid hitting limits)
