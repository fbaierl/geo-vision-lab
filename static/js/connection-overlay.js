/**
 * Connection Overlay for Leaflet Maps — Palantir Tactical Style
 *
 * Draws animated bezier arrows between locations to represent:
 * attack vectors, threat directions, support lines, movement routes, blockades.
 *
 * Animation: CSS "marching ants" stroke-dashoffset on SVG polylines.
 */

class ConnectionOverlay {
    constructor(map) {
        this.map = map;
        this.connections = [];
        this._animFrame = null;
        this._dashOffset = 0;
    }

    /**
     * Add a connection arrow between two coordinates.
     *
     * @param {Object} opts
     * @param {[number,number]} opts.from       [lat, lng] source
     * @param {[number,number]} opts.to         [lat, lng] destination
     * @param {string}          opts.type       attack|threat|support|movement|blockade
     * @param {string}          opts.intensity  high|medium|low
     * @param {string}          opts.fromName
     * @param {string}          opts.toName
     * @param {string}          opts.description
     */
    addConnection(opts) {
        const { from, to, type = 'threat', intensity = 'medium', fromName, toName, description } = opts;
        if (!from || !to || from.length !== 2 || to.length !== 2) {
            console.warn('[CONN] Invalid coords:', opts);
            return;
        }

        const color  = this._color(type, intensity);
        const weight = this._weight(intensity);
        const curve  = this._bezierPoints(from, to);

        // Dashed animated polyline
        const line = L.polyline(curve, {
            color,
            weight,
            opacity: 0.85,
            dashArray: '12, 8',
            lineCap: 'round',
            className: 'palantir-connection-line',
        }).addTo(this.map);

        line.bindPopup(this._popup(opts, color), { className: 'palantir-popup' });

        // Arrow marker at destination
        const arrow = this._arrowMarker(from, to, color, intensity);
        arrow.addTo(this.map);

        this.connections.push({ line, arrow, color, weight });

        if (!this._animFrame) this._startAnimation();
    }

    // ─────────────────────────────────────────────
    // Geometry helpers
    // ─────────────────────────────────────────────

    /** Generate bezier curve waypoints with a dramatic arc */
    _bezierPoints(from, to, steps = 40) {
        const [lat1, lng1] = from;
        const [lat2, lng2] = to;

        // Control point: perpendicular offset scaled by distance for a nice arc
        const dist = Math.sqrt((lat2 - lat1) ** 2 + (lng2 - lng1) ** 2);
        const offsetScale = Math.min(dist * 0.35, 8);

        const cpLat = (lat1 + lat2) / 2 + offsetScale * (lng2 - lng1) / dist;
        const cpLng = (lng1 + lng2) / 2 - offsetScale * (lat2 - lat1) / dist;

        const pts = [];
        for (let i = 0; i <= steps; i++) {
            const t = i / steps;
            const mt = 1 - t;
            pts.push([
                mt * mt * lat1 + 2 * mt * t * cpLat + t * t * lat2,
                mt * mt * lng1 + 2 * mt * t * cpLng + t * t * lng2,
            ]);
        }
        return pts;
    }

    /** Bearing angle (degrees) from source → destination */
    _bearing(from, to) {
        const [lat1, lng1] = from;
        const [lat2, lng2] = to;
        const dLng = (lng2 - lng1) * Math.PI / 180;
        const φ1   = lat1 * Math.PI / 180;
        const φ2   = lat2 * Math.PI / 180;
        const y = Math.sin(dLng) * Math.cos(φ2);
        const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(dLng);
        return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
    }

    /** Arrow SVG marker at the middle of the line */
    _arrowMarker(from, to, color, intensity) {
        const curve = this._bezierPoints(from, to);
        // Find middle point (index approx middle)
        const midIdx = Math.floor(curve.length / 2);
        const midPoint = curve[midIdx];
        const nextPoint = curve[midIdx + 1] || curve[curve.length - 1];
        
        // Calculate tangent at the middle
        const angle = this._bearing(midPoint, nextPoint);
        
        const sz = intensity === 'high' ? 28 : intensity === 'low' ? 18 : 22;
        
        const icon = L.divIcon({
            className: 'palantir-arrow-wrapper',
            html: `
                <svg width="${sz}" height="${sz}" viewBox="0 0 24 24"
                     style="transform:rotate(${angle - 90}deg);
                            transform-origin: center center;
                            filter:drop-shadow(0 0 6px ${color}) drop-shadow(0 0 12px ${color}40);
                            animation:palantirArrowPulse 1.5s ease-in-out infinite;
                            display: block;">
                    <polygon points="12,2 22,22 12,18 2,22" fill="${color}" opacity="0.95"/>
                </svg>
            `,
            iconSize: [sz, sz],
            iconAnchor: [sz / 2, sz / 2],
        });
        return L.marker(midPoint, { icon, interactive: false });
    }

    // ─────────────────────────────────────────────
    // Styling helpers
    // ─────────────────────────────────────────────

    _color(type, intensity) {
        const map = {
            attack:   { high: '#ff2020', medium: '#ff5533', low: '#ff7755' },
            threat:   { high: '#ff0077', medium: '#ff3388', low: '#ff66aa' },
            support:  { high: '#00ff88', medium: '#44ffaa', low: '#88ffcc' },
            movement: { high: '#00ccff', medium: '#44ddff', low: '#88eeff' },
            blockade: { high: '#cc44ff', medium: '#dd66ff', low: '#ee99ff' },
        };
        return (map[type] || map.threat)[intensity] || '#ffff00';
    }

    _weight(intensity) {
        return { high: 4, medium: 3, low: 2 }[intensity] || 3;
    }

    _popup(opts, color) {
        const { fromName, toName, type, intensity, description } = opts;
        const labels = {
            attack:   'ATTACK VECTOR',
            threat:   'THREAT DIRECTION',
            support:  'SUPPORT LINE',
            movement: 'MOVEMENT ROUTE',
            blockade: 'BLOCKADE / CONTAINMENT',
        };
        return `
            <div class="palantir-popup-inner">
                <div class="popup-title" style="color:${color}">${labels[type] || 'CONNECTION'}</div>
                <div class="popup-row"><span>FROM:</span> ${fromName || '—'}</div>
                <div class="popup-row"><span>TO:</span> ${toName || '—'}</div>
                <div class="popup-row"><span>INTENSITY:</span>
                    <span style="color:${color};text-transform:uppercase">${intensity}</span>
                </div>
                ${description ? `<div class="popup-row popup-desc">${description}</div>` : ''}
            </div>
        `;
    }

    // ─────────────────────────────────────────────
    // Animation — marching ants dash offset
    // ─────────────────────────────────────────────

    _startAnimation() {
        const step = () => {
            this._dashOffset = (this._dashOffset + 0.8) % 40;
            this.connections.forEach(({ line }) => {
                const el = line.getElement && line.getElement();
                if (el) el.style.strokeDashoffset = -this._dashOffset;
            });
            this._animFrame = requestAnimationFrame(step);
        };
        step();
    }

    stopAnimation() {
        if (this._animFrame) {
            cancelAnimationFrame(this._animFrame);
            this._animFrame = null;
        }
    }

    clear() {
        this.stopAnimation();
        this.connections.forEach(({ line, arrow }) => {
            this.map.removeLayer(line);
            this.map.removeLayer(arrow);
        });
        this.connections = [];
    }

    fitToConnections() {
        if (this.connections.length === 0) return;
        const pts = this.connections.flatMap(c => {
            const { from, to } = c.line.getLatLngs ? { from: null, to: null } : {};
            return [];
        });
        if (pts.length > 0) this.map.fitBounds(L.latLngBounds(pts), { padding: [50, 50] });
    }
}

window.ConnectionOverlay = ConnectionOverlay;
