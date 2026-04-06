/**
 * Map rendering module - handles Leaflet map initialization and location rendering
 */

let mapInstance = null;
let mapMarkers = [];

export function getMapInstance() {
    return mapInstance;
}

export function getMapMarkers() {
    return mapMarkers;
}

export function renderMap(locations, container) {
    if (!container) return;

    // Properly remove existing map
    if (mapInstance) {
        mapInstance.remove();
        mapInstance = null;
    }
    mapMarkers = [];

    // Clear container
    container.innerHTML = '';

    if (!locations || locations.length === 0) return;

    // Sort by relevance
    const sortedLocations = [...locations].sort((a, b) =>
        (b.relevance || 0.5) - (a.relevance || 0.5)
    );

    // Small delay to ensure container is visible and sized
    setTimeout(() => {
        if (container.offsetWidth === 0 || container.offsetHeight === 0) {
            console.warn('Map container has no dimensions, waiting...');
            setTimeout(() => initMap(), 100);
            return;
        }
        initMap();
    }, 50);

    function initMap() {
        // Create map
        mapInstance = L.map(container, {
            zoomControl: true,
            attributionControl: true,
            fadeAnimation: true,
            zoomAnimation: true
        });

        // Add dark tile layer
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
            subdomains: 'abcd',
            maxZoom: 19
        }).addTo(mapInstance);

        // Create boundary pane
        mapInstance.createPane('boundaryPane');
        mapInstance.getPane('boundaryPane').style.zIndex = 600;
        mapInstance.getPane('boundaryPane').style.pointerEvents = 'none';

        const bounds = [];

        // Process locations
        sortedLocations.forEach((loc, idx) => {
            const isPrimary = idx === 0;
            const color = isPrimary ? '#3daee9' : (idx < 3 ? '#5ec0ff' : '#88c0d0');
            const size = isPrimary ? 16 : 12;

            // Add marker
            const icon = L.divIcon({
                className: 'map-marker',
                html: `<div style="width:${size}px; height:${size}px; background:${color}; border-radius:50%; box-shadow:0 0 12px ${color}, 0 0 20px ${color}; border:2px solid white;"></div>`,
                iconSize: [size, size]
            });

            const marker = L.marker([loc.lat, loc.lon], { icon: icon }).addTo(mapInstance);
            marker.bindPopup(`<b>${loc.name}</b><br>Type: ${loc.type}<br>Relevance: ${(loc.relevance || 0.5).toFixed(2)}`);
            bounds.push([loc.lat, loc.lon]);
            mapMarkers.push({ marker, loc, color });
        });

        // Fit map to bounds
        if (bounds.length > 0) {
            setTimeout(() => {
                try {
                    const group = L.featureGroup(bounds.map(b => L.marker(b)));
                    mapInstance.fitBounds(group.getBounds(), { padding: [50, 50] });
                } catch (e) {
                    if (bounds.length === 1 && Array.isArray(bounds[0])) {
                        mapInstance.setView(bounds[0], 6);
                    }
                }
            }, 50);
        }

        // Build legend
        buildMapLegend(sortedLocations);
    }
}

function buildMapLegend(locations) {
    const legend = document.getElementById('map-legend');
    if (!legend) return;

    function escapeHtml(s) {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    let html = '<span style="font-weight: 600; color: var(--accent-bright);">Locations:</span> ';
    locations.forEach((loc, idx) => {
        const color = idx === 0 ? '#3daee9' : (idx < 3 ? '#5ec0ff' : '#88c0d0');
        html += `<span class="map-legend-item" data-idx="${idx}" style="display: inline-flex; align-items: center; gap: 6px; margin-left: 10px; cursor: pointer; padding: 2px 6px; border-radius: 4px; transition: background 0.15s;" onmouseover="this.style.background='var(--bg-hover)'" onmouseout="this.style.background='transparent'">
            <span style="width: 8px; height: 8px; background: ${color}; border-radius: 50%; box-shadow: 0 0 6px ${color};"></span>
            <span style="font-size: 0.75rem; color: var(--text);">${escapeHtml(loc.name)}</span>
        </span>`;
    });

    legend.innerHTML = html;

    // Add click handlers to focus on location
    legend.querySelectorAll('.map-legend-item').forEach((item, idx) => {
        item.addEventListener('click', () => {
            if (mapMarkers[idx] && mapInstance) {
                const { marker, loc } = mapMarkers[idx];
                mapInstance.setView([loc.lat, loc.lon], 10);
                marker.openPopup();
            }
        });
    });
}
