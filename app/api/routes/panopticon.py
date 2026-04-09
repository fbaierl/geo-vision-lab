"""Panopticon 3D globe API — real-time global data visualization."""

import logging
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/panopticon", tags=["panopticon"])

# In-memory cache for OpenSky data
_cache = {
    "data": None,
    "timestamp": None,
    "ttl": 60,  # seconds
}

OPENSKY_API = "https://opensky-network.org/api/states/all"
OPENSKY_TIMEOUT = 30


async def fetch_opensky_states() -> dict:
    """Fetch all current aircraft states from the OpenSky Network API."""
    async with httpx.AsyncClient(timeout=OPENSKY_TIMEOUT) as client:
        response = await client.get(OPENSKY_API)
        response.raise_for_status()
        return response.json()


def transform_opensky_to_aircraft(states: dict) -> list[dict]:
    """Transform OpenSky states array into structured aircraft objects.

    OpenSky columns (index → field):
    0: icao24, 1: callsign, 2: country, 3: last_contact, 4: last_updated,
    5: longitude, 6: latitude, 7: baro_altitude, 8: on_ground, 9: velocity,
    10: true_track, 11: vertical_rate, 12: sensors, 13: geo_altitude,
    14: squawk, 15: alert, 16: spi, 17: position_source
    """
    aircraft_list = []
    if not states or "states" not in states:
        return aircraft_list

    for state in states["states"]:
        try:
            lon = state[5]
            lat = state[6]
            # Skip aircraft without valid position data
            if lon is None or lat is None:
                continue

            baro_alt = state[7]
            geo_alt = state[13]
            altitude = geo_alt if geo_alt is not None else baro_alt

            aircraft_list.append(
                {
                    "icao24": state[0] or "",
                    "callsign": (state[1] or "").strip(),
                    "country": state[2] or "Unknown",
                    "longitude": lon,
                    "latitude": lat,
                    "altitude": altitude if altitude is not None else 0,
                    "on_ground": bool(state[8]),
                    "velocity": state[9] if state[9] is not None else 0,
                    "heading": state[10] if state[10] is not None else 0,
                }
            )
        except (IndexError, TypeError) as exc:
            logger.debug("Skipping malformed OpenSky state entry: %s", exc)
            continue

    return aircraft_list


@router.get("/aircraft")
async def get_aircraft_positions():
    """Return current global aircraft positions from OpenSky Network.

    Responses are cached for 60 seconds to respect API rate limits.
    Returns structured aircraft objects with lat/lon/altitude/callsign.
    """
    now = time.time()

    # Return cached data if still valid
    if (
        _cache["data"] is not None
        and _cache["timestamp"] is not None
        and (now - _cache["timestamp"]) < _cache["ttl"]
    ):
        logger.debug(
            "Returning cached OpenSky data (%d aircraft, age=%.1fs)",
            len(_cache["data"]),
            now - _cache["timestamp"],
        )
        return {
            "aircraft": _cache["data"],
            "count": len(_cache["data"]),
            "cached": True,
            "timestamp": datetime.fromtimestamp(
                _cache["timestamp"], tz=timezone.utc
            ).isoformat(),
        }

    try:
        logger.info("Fetching fresh data from OpenSky Network API…")
        states = await fetch_opensky_states()
        aircraft = transform_opensky_to_aircraft(states)

        # Update cache
        _cache["data"] = aircraft
        _cache["timestamp"] = time.time()

        logger.info("Fetched %d aircraft with valid positions", len(aircraft))

        return {
            "aircraft": aircraft,
            "count": len(aircraft),
            "cached": False,
            "timestamp": datetime.fromtimestamp(
                _cache["timestamp"], tz=timezone.utc
            ).isoformat(),
        }

    except httpx.TimeoutException:
        logger.error("OpenSky API request timed out")
        # Return stale cache if available
        if _cache["data"] is not None:
            return {
                "aircraft": _cache["data"],
                "count": len(_cache["data"]),
                "cached": True,
                "stale": True,
                "timestamp": datetime.fromtimestamp(
                    _cache["timestamp"], tz=timezone.utc
                ).isoformat(),
                "error": "API timeout — returning cached data",
            }
        raise HTTPException(status_code=504, detail="OpenSky API request timed out")

    except httpx.HTTPStatusError as exc:
        logger.error("OpenSky API HTTP error: %s", exc)
        if _cache["data"] is not None:
            return {
                "aircraft": _cache["data"],
                "count": len(_cache["data"]),
                "cached": True,
                "stale": True,
                "timestamp": datetime.fromtimestamp(
                    _cache["timestamp"], tz=timezone.utc
                ).isoformat(),
                "error": f"API error {exc.response.status_code}",
            }
        raise HTTPException(
            status_code=502, detail=f"OpenSky API error: {exc.response.status_code}"
        )

    except Exception as exc:
        logger.error("Unexpected error fetching OpenSky data: %s", exc)
        if _cache["data"] is not None:
            return {
                "aircraft": _cache["data"],
                "count": len(_cache["data"]),
                "cached": True,
                "stale": True,
                "timestamp": datetime.fromtimestamp(
                    _cache["timestamp"], tz=timezone.utc
                ).isoformat(),
                "error": str(exc),
            }
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")
