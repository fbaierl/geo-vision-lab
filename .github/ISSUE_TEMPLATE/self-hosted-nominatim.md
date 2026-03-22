---
name: 🗺️ Self-Hosted Nominatim
about: Implement self-hosted Nominatim service to avoid rate limiting
title: 'feat: Add self-hosted Nominatim service for geocoding'
labels: ['enhancement', 'infrastructure', 'geocoding']
assignees: ''
---

## Problem

The current implementation uses the public Nominatim API (`nominatim.openstreetmap.org`) for geocoding location names to coordinates. This service has strict rate limiting (1 request per second) and returns HTTP 429 errors when exceeded:

```
HTTP 429 - Too many requests
Error 54113 - Varnish cache server
```

This causes location extraction failures during active queries that geocode multiple locations.

## Proposed Solution

Add a self-hosted Nominatim service to the Docker Compose stack with:
- Local PostgreSQL database with PostGIS
- Pre-loaded OpenStreetMap data
- No rate limiting for local requests
- Automatic updates for OSM data

## Implementation Plan

### 1. Docker Compose Service

Add a new service to `docker-compose.yml`:

```yaml
services:
  nominatim:
    image: mediagis/nominatim:4.4
    container_name: geovision-nominatim
    restart: unless-stopped
    ports:
      - "8083:8080"
    environment:
      - PBF_PATH=/nominatim/data
      - PBF_URL=https://download.geofabrik.de/europe-latest.osm.pbf
      - REPLICATION_URL=https://download.geofabrik.de/europe-updates/
      - NOMINATIM_PASSWORD=geovision
      - IMPORT_STYLE=extratags
      - FLATNODE_FILE=/nominatim/data/flatnodes
    volumes:
      - nominatim-data:/var/lib/postgresql/14/main
      - nominatim-cache:/nominatim/data
    deploy:
      resources:
        limits:
          memory: 8G
        reservations:
          memory: 4G

volumes:
  nominatim-data:
  nominatim-cache:
```

### 2. Update Location Extractor

Modify `app/agents/tools/location_extractor.py`:

```python
# Current
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# New
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "http://nominatim:8080/search")
```

### 3. Environment Variables

Add to `.env.example`:

```env
# Nominatim geocoding service
NOMINATIM_URL=http://nominatim:8080/search
NOMINATIM_TIMEOUT=10
```

### 4. Health Check

Add health check to monitor Nominatim service:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/search?q=Berlin&format=json"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 120s
```

### 5. Documentation

Update README.md with:
- New service in architecture diagram
- Access URL: `http://localhost:8083`
- Resource requirements (8GB RAM recommended)
- Initial import time (~30-60 minutes for Europe)

## Resource Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 4 GB | 8 GB |
| Storage | 20 GB | 50 GB (SSD) |
| CPU | 2 cores | 4 cores |
| Initial Import | ~60 min | ~30 min |

## Alternative: Smaller Extracts

For development/testing, use smaller OSM extracts:
- Country-level: `germany-latest.osm.pbf`
- State-level: `california-latest.osm.pbf`
- Custom bounds: Geofabrik download server

## Benefits

- ✅ No rate limiting
- ✅ Faster response times (local network)
- ✅ Reliable availability
- ✅ Full control over data updates
- ✅ Better for development/testing

## Drawbacks

- ⚠️ Higher resource usage
- ⚠️ Initial data import time
- ⚠️ Maintenance overhead (updates)

## Acceptance Criteria

- [ ] Nominatim service runs in Docker Compose
- [ ] Location extractor uses local service
- [ ] No 429 errors during multi-location queries
- [ ] Health check monitors service status
- [ ] Documentation updated
- [ ] Graceful fallback to public API if local service unavailable

## References

- [Nominatim Docker Image](https://github.com/mediagis/nominatim-docker)
- [Nominatim Documentation](https://nominatim.org/release-docs/latest/)
- [Geofabrik Downloads](https://download.geofabrik.de/)
- [OpenStreetMap](https://www.openstreetmap.org)
