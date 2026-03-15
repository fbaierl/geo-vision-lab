/**
 * Map Controller - Palantir-style Tactical Map
 *
 * Renders geocoded locations and directional connections from geo_ner extraction.
 * Features:
 *  - Dark/satellite CartoDB tiles
 *  - Pulsing glow markers per location role (aggressor/target/ally/neutral)
 *  - Animated bezier arrows via ConnectionOverlay
 *  - Map legend with connection type legend
 *  - Auto-fit bounds to show all elements
 */

class MapController {
    constructor() {
        this.currentMap = null;
        this.markers = [];
        this.overlay = null;
    }

    // ─────────────────────────────────────────────
    // Public API: called from SSE geo_locations event
    // ─────────────────────────────────────────────

    showResponseLocations(locations, connections, anchorEl = null) {
        const geocoded = (locations || []).filter(
            loc => loc.coordinates && loc.coordinates.length === 2
        );

        if (geocoded.length === 0 && (!connections || connections.length === 0)) {
            console.log('[MAP] No geocoded locations or connections to show');
            return;
        }

        console.log('[MAP] Rendering:', geocoded.length, 'locations,', (connections || []).length, 'connections');
        this._createMap(geocoded, connections || [], anchorEl);
    }

    // ─────────────────────────────────────────────
    // Internal: build the DOM + Leaflet map
    // ─────────────────────────────────────────────

    _createMap(locations, connections, anchorEl) {
        const mapId = 'geo-map-' + Date.now();
        const headerText = `TACTICAL MAP // ${locations.length} location${locations.length !== 1 ? 's' : ''} · ${connections.length} vector${connections.length !== 1 ? 's' : ''}`;
        
        let container;
        if (anchorEl) {
            anchorEl.innerHTML = ''; // Clear placeholder
            container = document.createElement('div');
            container.className = 'llm-map-container palantir-map-wrapper anchored';
            anchorEl.appendChild(container);
        } else {
            const messagesEl = document.getElementById('messages');
            if (!messagesEl) { console.error('[MAP] #messages not found'); return; }
            container = document.createElement('div');
            container.className = 'llm-map-container palantir-map-wrapper';
            messagesEl.appendChild(container);
        }

        container.innerHTML = `
            <div class="llm-map-header palantir-map-header">
                <span class="map-header-icon">▸</span>
                <span>${headerText}</span>
                <span class="map-status-dot"></span>
            </div>
            <div id="${mapId}" class="llm-map palantir-map" style="height:600px; width:100%;"></div>
            <div class="palantir-map-legend" id="legend-${mapId}"></div>
        `;
        if (!anchorEl) {
            const messagesEl = document.getElementById('messages');
            if (messagesEl) {
                messagesEl.appendChild(container);
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }
        } else {
            // If anchored in a tab, scrolling the main message list might still be good
            const messagesEl = document.getElementById('messages');
            if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
        }

        // Initialise Leaflet after DOM render
        setTimeout(() => this._initLeaflet(mapId, locations, connections), 100);
    }

    _initLeaflet(mapId, locations, connections) {
        const mapEl = document.getElementById(mapId);
        if (!mapEl) return;

        // Destroy any previous map on same element (safety)
        if (mapEl._leaflet_id) return;

        const map = L.map(mapId, {
            zoomControl: true,
            attributionControl: false,
            preferCanvas: true,
        }).setView([20, 0], 2);

        // Dark tactical tiles (CartoDB Dark Matter)
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 19,
        }).addTo(map);

        this.currentMap = map;
        this.overlay = new window.ConnectionOverlay(map);
        this.markers = [];

        // Force a resize check after a few frames to handle tab-switching layouts
        setTimeout(() => map.invalidateSize(), 200);

        const allBounds = [];

        // ── Draw markers ──
        locations.forEach(loc => {
            const [lat, lng] = loc.coordinates;
            if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return;

            const color = this._entityColor(loc);
            const icon = this._pulseIcon(color, loc.type);
            const marker = L.marker([lat, lng], { icon }).addTo(map);
            marker.bindPopup(this._locationPopup(loc), { className: 'palantir-popup' });
            this.markers.push(marker);
            allBounds.push([lat, lng]);
        });

        // ── Draw arrows ──
        (connections || []).forEach(conn => {
            if (!conn.from_coords || !conn.to_coords) return;
            this.overlay.addConnection({
                from: conn.from_coords,
                to: conn.to_coords,
                type: conn.type || 'threat',
                intensity: conn.intensity || 'medium',
                fromName: conn.from_name,
                toName: conn.to_name,
                description: conn.description || '',
            });
            allBounds.push(conn.from_coords, conn.to_coords);
        });

        // ── Fit bounds ──
        if (allBounds.length > 0) {
            try {
                if (allBounds.length === 1) {
                    map.setView(allBounds[0], 6);
                } else {
                    map.fitBounds(L.latLngBounds(allBounds), { padding: [50, 50], maxZoom: 7 });
                }
            } catch (e) {
                console.warn('[MAP] fitBounds failed:', e);
            }
        }

        // ── Legend ──
        this._buildLegend('legend-' + mapId, locations, connections);

        // ── Status bar update ──
        const statusEl = document.getElementById('f-status');
        if (statusEl) {
            statusEl.textContent = `// ${locations.length} Location${locations.length !== 1 ? 's' : ''} Mapped`;
            setTimeout(() => { statusEl.textContent = '// Standby'; }, 4000);
        }

        console.log(`[MAP] Palantir map rendered: ${locations.length} locations, ${connections.length} connections`);
    }

    // ─────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────

    /** Get a distinct color for an entity based on its name/role */
    _entityColor(loc) {
        // Core situational roles get priority colors
        const ROLE_COLORS = {
            aggressor:  '#ff3030',
            target:     '#ff9900',
            ally:       '#00ff88',
            staging:    '#cc44ff',
        };

        if (ROLE_COLORS[loc.role]) return ROLE_COLORS[loc.role];

        // Entity palette for "neutral" or variety
        const PALETTE = [
            '#00d4ff', // Cyan
            '#00ff88', // Neo-green
            '#ff00ff', // Magenta
            '#7700ff', // Indigo
            '#ffff00', // Yellow
            '#ff5500', // Bright Orange
            '#00ffcc', // Mint
            '#ffcc00', // Gold
        ];

        // Hash name to index
        const name = loc.name || 'unknown';
        let hash = 0;
        for (let i = 0; i < name.length; i++) {
            hash = name.charCodeAt(i) + ((hash << 5) - hash);
        }
        return PALETTE[Math.abs(hash) % PALETTE.length];
    }

    _pulseIcon(color, type) {
        const size = type === 'country' ? 16 : 12;
        return L.divIcon({
            className: 'palantir-marker-wrapper',
            html: `
                <div style="
                    position: relative;
                    width: ${size * 2.5}px;
                    height: ${size * 2.5}px;
                    pointer-events: none;
                ">
                    <!-- Core Pulse Dot -->
                    <div class="palantir-pulse" style="
                        position:absolute;
                        top: 50%; left: 50%;
                        transform: translate(-50%, -50%);
                        width:${size}px; height:${size}px;
                        background:${color};
                        border-radius:50%;
                        box-shadow: 0 0 12px ${color}, 0 0 24px ${color}60;
                        animation: palantirPulse 2s ease-in-out infinite;
                        z-index: 2;
                    "></div>
                    <!-- Outer Ring -->
                    <div class="palantir-pulse-ring" style="
                        position:absolute;
                        top: 50%; left: 50%;
                        width:${size * 2.5}px; height:${size * 2.5}px;
                        border:2px solid ${color};
                        border-radius:50%;
                        animation: palantirRing 2s ease-out infinite;
                        opacity:0.6;
                        z-index: 1;
                    "></div>
                </div>
            `,
            iconSize: [size * 2.5, size * 2.5],
            iconAnchor: [size * 1.25, size * 1.25],
        });
    }

    _locationPopup(loc) {
        const [lat, lng] = loc.coordinates;
        const roleLabel = (loc.role || 'neutral').toUpperCase();
        const color = this._entityColor(loc);
        return `
            <div class="palantir-popup-inner">
                <div class="popup-title" style="color:${color}">${loc.name}</div>
                <div class="popup-row"><span>TYPE:</span> ${loc.type || 'location'}</div>
                <div class="popup-row"><span>ROLE:</span> <span style="color:${color}">${roleLabel}</span></div>
                <div class="popup-row"><span>COORD:</span> ${lat.toFixed(4)}, ${lng.toFixed(4)}</div>
            </div>
        `;
    }

    _buildLegend(legendId, locations, connections) {
        const el = document.getElementById(legendId);
        if (!el) return;

        const types = [...new Set((connections || []).map(c => c.type || 'threat'))];
        const COLOR_MAP = {
            attack:   '#ff0000',
            threat:   '#ff0066',
            support:  '#00ff88',
            movement: '#00d4ff',
            blockade: '#cc44ff',
        };
        const LABEL_MAP = {
            attack:   'Attack Vector',
            threat:   'Threat Direction',
            support:  'Support Line',
            movement: 'Movement Route',
            blockade: 'Blockade/Containment',
        };

        let html = '';

        // Locations section
        if (locations && locations.length > 0) {
            html += `<div class="legend-title" style="margin-top:0">▸ POINTS OF INTEREST</div>`;
            html += `<div class="legend-poi-container" style="display:flex; flex-wrap:wrap; gap:10px; margin-bottom:12px; padding:5px 0;">`;
            locations.forEach(loc => {
                const color = this._entityColor(loc);
                html += `
                    <div class="legend-poi" style="display:flex; align-items:center; gap:5px; font-size:0.8rem; color:var(--white);">
                        <div style="width:8px; height:8px; border-radius:50%; background:${color}; box-shadow:0 0 5px ${color}"></div>
                        <span style="border-bottom:1px solid ${color}40">${loc.name}</span>
                    </div>
                `;
            });
            html += `</div>`;
        }

        // Vectors section
        if (types.length > 0) {
            html += `<div class="legend-title">▸ VECTOR LEGEND</div>`;
            html += types.map(t => `
                <div class="legend-row">
                    <svg width="28" height="6" style="vertical-align:middle; margin-right:6px;">
                        <line x1="0" y1="3" x2="24" y2="3"
                               stroke="${COLOR_MAP[t] || '#ffff00'}" stroke-width="2"
                               stroke-dasharray="5,3"/>
                        <polygon points="24,0 28,3 24,6" fill="${COLOR_MAP[t] || '#ffff00'}"/>
                    </svg>
                    <span>${LABEL_MAP[t] || t.toUpperCase()}</span>
                </div>
            `).join('');
        }

        el.innerHTML = html;
    }

    clearMarkers() {
        this.markers.forEach(m => { if (this.currentMap) this.currentMap.removeLayer(m); });
        this.markers = [];
        if (this.overlay) { this.overlay.clear(); this.overlay = null; }
    }
}

// Export
window.MapController = MapController;
window.geoMapController = new MapController();
console.log('[MAP] Palantir MapController initialized');
