# Qwen Development Guide

This guide provides essential information for working with Qwen models in the GeoVision Lab project.

## Qwen Model Overview

We use the Qwen 2.5 series (tagged as `qwen3.5` in our environment for internal versioning logic) to provide high-quality reasoning and analysis capabilities.

### Model Roles

| Role | Model Name | Description |
| :--- | :--- | :--- |
| **Main LLM** | `qwen3.5:4b` | Handling general application requests and transformations. |
| **Reasoning LLM** | `qwen3.5:4b` | Dedicated to complex reasoning tasks. Switchable to `9b` or `0.8b`. |
| **Reviewer LLM** | `qwen3.5:0.8b` | Efficient model used for QA and validation steps. |

### Available Reasoning Models
- `qwen3.5:9b`: Highest quality, requires more VRAM.
- `qwen3.5:4b`: Balanced performance and speed (Default).
- `qwen3.5:0.8b`: Lightest version, useful for low-resource environments.

---

## Docker Operations

The project relies on Docker to manage the model lifecycle via Ollama.

### Basic Commands

- **Start all services:**
  ```bash
  docker compose up -d
  ```

- **View service logs (including Ollama model loading):**
  ```bash
  docker compose logs -f ollama
  ```

- **Check loaded models in Ollama:**
  ```bash
  docker exec -it geovision-ollama ollama list
  ```

- **Pull models manually (if not pulled by compose):**
  ```bash
  docker exec -it geovision-ollama ollama pull qwen3.5:4b
  ```

---

## Testing with Docker

To ensure the models are integrating correctly with the application logic, run the test suite within the application container.

### Run All Tests
```bash
docker exec geovision-app pytest
```

### Run Specific Test File
```bash
docker exec geovision-app pytest tests/test_rag.py
```

### Run with Coverage
```bash
docker exec geovision-app pytest --cov=app tests/
```

---

## Code Quality & Linting

### Run Ruff After Each Task

**IMPORTANT**: After completing each coding task, always run ruff to lint and auto-fix issues:

```bash
# Auto-fix all fixable issues
.venv/bin/ruff check app/ tests/ --fix

# Verify no remaining issues
.venv/bin/ruff check app/ tests/
```

This ensures code quality and consistency across the project.

---

## Testing

### Run Tests After Each Task

**IMPORTANT**: After completing each coding task (and running ruff), always run the test suite to ensure nothing is broken:

```bash
# Run all tests
.venv/bin/pytest tests/ -v

# Run specific test file
.venv/bin/pytest tests/test_db_integration.py -v

# Run with coverage
.venv/bin/pytest tests/ --cov=app
```

**Expected outcome**: All tests should pass. If any test fails, fix the issue before committing.

---

## Development Tips

1. **Model Switching**: You can change the reasoning model at runtime using the `set_reasoning_model` method in `app/core/config.py` or by updating the `REASONING_LLM_MODEL_NAME` environment variable.
2. **GPU Acceleration**: Ensure you have the `nvidia-container-toolkit` installed if you want to use GPU acceleration with the `ollama` service. Check the `deploy` section in `docker-compose.yml`.
3. **Resource Monitoring**: Use **Dozzle** at [http://localhost:9999](http://localhost:9999) to monitor container logs and resource usage (CPU/Memory) when models are running.

---

## Unified Map Rendering

The application uses a **single unified map** to display all geographic locations instead of multiple small maps. This section documents the architecture and common pitfalls.

### Architecture

- **Single Map Container**: All locations are rendered on one large Leaflet map
- **Legend Panel**: Scrollable legend at the bottom showing all locations grouped by type
- **Boundary Fetching**: Country/region boundaries are fetched from Nominatim API
- **Custom Pane**: Boundaries render in a separate `boundaryPane` (zIndex: 600) above tiles

### Location Types

| Type | Rendering | Color |
|------|-----------|-------|
| **City** | Point marker | Cyan circle with glow |
| **Country** | Boundary polygon | Cyan stroke (#00ffff), Cyan fill (#0088aa) |
| **Region** | Boundary polygon | Amber stroke (#ffab00), Amber fill (#aa7700) |

### Common Bugs & Solutions

#### Bug: Legend Not Visible

**Symptoms**: Map renders but legend panel is missing or pushed out of view.

**Root Cause**: CSS flex properties causing map to expand and push legend out.

**Solution**:
```css
.unified-map-wrapper {
    display: flex;
    flex-direction: column;
    min-height: 500px;
}

.unified-map {
    flex: 1;
    min-height: 350px;
}

.map-legend {
    flex-shrink: 0;  /* Critical: prevents legend from shrinking */
    min-height: 80px;
    max-height: 180px;
    display: block;
}
```

**Prevention**: Always verify legend container has `flex-shrink: 0` and explicit min-height.

#### Bug: Country Borders Not Visible

**Symptoms**: Only city markers appear, country/region boundaries are invisible.

**Root Cause**: Dark mode CSS filter (`invert(1) hue-rotate(180deg)`) applied to all layers including boundaries.

**Solution**:
```css
/* Apply filter ONLY to tile layers, not overlays */
.leaflet-tile-pane,
.leaflet-layer {
    filter: invert(1) hue-rotate(180deg) brightness(0.85) contrast(1.1);
}

/* Boundaries render in separate pane, unaffected by tile filter */
.boundaryPane {
    z-index: 600;
    pointer-events: none;
}
```

**Prevention**: 
1. Always use a custom pane for boundaries: `map.createPane('boundaryPane')`
2. Set boundary colors to bright values (#00ffff, #ffab00) that survive dark mode filtering
3. Never apply CSS filters to overlay panes

#### Bug: Boundaries Render But Blend Into Background

**Symptoms**: Boundaries technically render but are invisible due to dark colors.

**Root Cause**: Fill colors too dark, or stroke weight too thin.

**Solution**: Use bright stroke colors with moderate fill opacity:
```javascript
style: () => ({
    color: '#00ffff',      // Bright cyan stroke
    weight: 3,             // Thick enough to see
    fillOpacity: 0.25,     // Semi-transparent fill
    fillColor: '#0088aa',  // Darker cyan fill
    opacity: 0.9
})
```

### Testing

Run the unified map rendering tests to verify correct implementation:

```bash
# Run all map rendering tests
.venv/bin/pytest tests/test_unified_map_rendering.py -v

# Run specific test category
.venv/bin/pytest tests/test_unified_map_rendering.py::TestUnifiedMapRendering -v
```

### Debug Logging

The map rendering function includes console logs for debugging:

```javascript
console.log('[renderUnifiedMap] Processing locations:', locations);
console.log('[renderUnifiedMap] Locations by type:', locationsByType);
console.log('[renderUnifiedMap] Building legend with HTML:', legendHTML.length, 'chars');
console.log('[renderUnifiedMap] Legend rendered, container has X entries');
```

Check browser console to verify:
1. Locations are being received with correct types
2. Legend HTML is being generated
3. Legend entries are being created

### Debug Button: View Raw Data

A **VIEW DATA** button is available in the map header for debugging:

**Features**:
- Click to view raw JSON location data
- Modal displays formatted JSON with syntax highlighting
- **COPY JSON** button to copy data to clipboard
- Click outside modal or **CLOSE** button to dismiss

**Use Cases**:
- Verify location coordinates and types
- Debug boundary fetching issues
- Copy location data for external tools
- Inspect relevance scores

**Location**: Top-right corner of the map header, next to the location count.

### Key Files

- **Frontend**: `static/index.html` - `renderUnifiedMap()` function
- **Styles**: `static/style.css` - `.unified-map-wrapper`, `.map-legend`
- **Tests**: `tests/test_unified_map_rendering.py`, `tests/test_location_extractor.py`
- **Backend**: `app/services/location_extractor.py` - Location extraction pipeline

---

## Location Disambiguation Pipeline

The platform uses a **pure tool-based approach** for location disambiguation with NO hardcoding and NO heuristics.

### Problem

When extracting locations from text, Nominatim may return incorrect matches:
- "IRA" → Town of Ira, New York (instead of Iran)
- "Middle East" → Baltimore neighborhood (instead of the geographic region)
- Country names matching towns in unrelated countries

### Solution: 3-Step Tool Pipeline

**Tools Used:**
1. **Hugging Face NER** (dslim/bert-base-NER) - Extract location names
2. **Nominatim** (OpenStreetMap) - Get ALL geocoding candidates
3. **Reviewer LLM** - Decide which candidates are correct for query context

**NO hardcoding, NO heuristics** - works for any country/region worldwide.

#### Step 1: NER Extraction
```python
locations = extract_locations_with_ner(text)
# Output: [{"name": "Iran", "type": "country", "label": "GPE"}, ...]
```

#### Step 2: Multi-Candidate Geocoding
```python
candidates = geocode_location("Iran")
# Returns ALL matches, not just first:
# [
#   {"name": "Iran", "country": "Iran", "type": "country", ...},
#   {"name": "Iran", "country": "USA", "type": "town", ...}
# ]
```

#### Step 3: LLM Selection (Sole Decision Maker)
```python
valid_locations = select_valid_locations(
    location_candidates,  # All candidates from step 2
    query="iran vs israel",
    response_text=response
)
# LLM reviews all candidates and selects correct ones
# Output: [{"name": "Iran", "country": "Iran", ...}]
```

### How It Works

**Example: Query "iran vs israel"**

1. **NER extracts**: ["IRA", "Tehran", "Tel Aviv", "Middle East", "Iran"]

2. **Geocoding gets ALL candidates**:
   ```
   IRA:
     1) Town of Ira, New York, USA (town)
     2) Ira, Vermont, USA (town)
   
   Tehran:
     1) Tehran, Iran (city)
     2) Tehran, Minnesota, USA (town)
   
   Iran:
     1) Iran (country)
     2) Iran, Texas, USA (town)
   ```

3. **LLM reviews in context**:
   - Sees "IRA" only has USA town options → EXCLUDE (wrong for Iran-Israel query)
   - Sees "Tehran" has Iran option → SELECT (matches context)
   - Sees "Iran" has country option → SELECT (matches context)

4. **Final output**: [Tehran→Iran, Iran→country]

### Key Design Principles

1. **NO HARDCODED COUNTRIES**
   - Works for Iran, France, Japan, Brazil - any country
   - No country lists, no mappings to maintain

2. **NO HEURISTICS**
   - No distance-based clustering
   - No type validation rules
   - No pattern matching

3. **LLM AS SOLE DECISION MAKER**
   - LLM has world knowledge of all countries/regions
   - Context-aware filtering
   - Can explain reasoning

4. **ALL CANDIDATES SHOWN**
   - LLM sees all geocoding options
   - Makes informed decision
   - Not limited to first match

5. **GRACEFUL DEGRADATION**
   - If LLM fails, fallback to first candidate
   - Better no locations than wrong locations

### Testing

```bash
# Run location extraction tests
.venv/bin/pytest tests/test_location_extractor.py -v

# Test specific components
.venv/bin/pytest tests/test_location_extractor.py::TestSelectValidLocations -v
```

### Debugging

Check logs for LLM decisions:
```
[LOCATION_EXTRACTOR] Found 5 location(s) via NER: ['IRA', 'Tehran', 'Tel Aviv', ...]
[LOCATION_EXTRACTOR] IRA: 2 candidate(s) found
[LOCATION_EXTRACTOR] Tehran: 2 candidate(s) found
[LOCATION_EXTRACTOR] Selected: Iran → ایران (country) (Iran country matches query context)
[LOCATION_EXTRACTOR] LLM selected 2/5 locations
```

### Why This Approach Works

| Aspect | Old Approach | New Approach |
|--------|-------------|--------------|
| **Country Coverage** | ~15 hardcoded countries | All countries worldwide |
| **Maintenance** | Add new countries manually | Zero maintenance |
| **Regional Queries** | Fails for non-hardcoded regions | Works for any region |
| **Decision Logic** | Hardcoded rules | LLM reasoning |
| **False Positives** | Possible (incomplete lists) | Minimal (LLM has world knowledge) |

---
