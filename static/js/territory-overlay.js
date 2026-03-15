/**
 * Territory Overlay Controller
 * 
 * Manages territory boundary visualization with faction control indicators.
 * Supports animated front lines for contested regions.
 */

class TerritoryOverlay {
    constructor(map) {
        this.map = map;
        this.layers = new Map();  // locationName -> layer
        this.visibleLayers = new Set();
        
        // Faction colors for territory control
        this.factionColors = {
            'neutral': '#00ffff',      // Cyan - neutral/uncontested
            'contested': '#ff4444',    // Red - active conflict zone
            'friendly': '#44ff44',     // Green - friendly control
            'hostile': '#ff44ff',      // Magenta - hostile control
            'unknown': '#888888'       // Gray - unknown status
        };
    }

    /**
     * Load territory boundary for a location
     */
    async loadTerritory(locationName) {
        try {
            const response = await fetch(`/geo/territory/${encodeURIComponent(locationName)}`);
            if (!response.ok) {
                if (response.status === 404) {
                    console.warn(`[TERRITORY] No boundary found for '${locationName}'`);
                    return null;
                }
                throw new Error(`HTTP ${response.status}`);
            }

            const geojson = await response.json();
            return this.addTerritory(geojson);
        } catch (error) {
            console.error(`[TERRITORY] Failed to load territory for '${locationName}':`, error);
            return null;
        }
    }

    /**
     * Add a territory GeoJSON feature to the map
     */
    addTerritory(geojson) {
        const locationName = geojson.properties?.name || 'Unknown';

        // Remove existing layer for this location
        if (this.layers.has(locationName)) {
            this.map.removeLayer(this.layers.get(locationName));
        }

        const faction = geojson.properties?.faction || 'neutral';
        const color = this.factionColors[faction] || this.factionColors.unknown;

        const layer = L.geoJSON(geojson, {
            style: (feature) => ({
                color: color,
                weight: 3,
                opacity: 0.9,
                fillOpacity: 0.25,
                dashArray: faction === 'contested' ? '10, 10' : null,
                lineCap: 'round'
            }),
            onEachFeature: (feature, layer) => {
                // Add popup with territory info
                const popupContent = `
                    <div style="font-family: 'Share Tech Mono', monospace;">
                        <strong style="color: ${color};">${locationName}</strong><br/>
                        Status: ${geojson.properties?.status || 'Unknown'}<br/>
                        Control: ${faction.toUpperCase()}
                    </div>
                `;
                layer.bindPopup(popupContent);
            }
        });

        // Store layer reference
        this.layers.set(locationName, layer);

        // Add to map if currently visible
        if (this.visibleLayers.has(locationName)) {
            layer.addTo(this.map);
            this.animateBorder(layer, faction === 'contested');
        }

        console.log(`[TERRITORY] Added territory: ${locationName}`);
        return layer;
    }

    /**
     * Animate border for contested territories
     */
    animateBorder(layer, animate = true) {
        layer.eachLayer(l => {
            const path = l.getElement();
            if (path) {
                if (animate) {
                    path.style.animation = 'territoryPulse 2s linear infinite';
                } else {
                    path.style.animation = '';
                }
            }
        });
    }

    /**
     * Show territory overlay
     */
    show(locationName) {
        if (locationName) {
            this.visibleLayers.add(locationName);
            const layer = this.layers.get(locationName);
            if (layer) {
                layer.addTo(this.map);
                this.animateBorder(layer, true);
            }
        } else {
            // Show all territories
            this.layers.forEach((layer, name) => {
                this.visibleLayers.add(name);
                layer.addTo(this.map);
            });
        }
    }

    /**
     * Hide territory overlay
     */
    hide(locationName) {
        if (locationName) {
            this.visibleLayers.delete(locationName);
            const layer = this.layers.get(locationName);
            if (layer) {
                this.map.removeLayer(layer);
            }
        } else {
            // Hide all territories
            this.visibleLayers.clear();
            this.layers.forEach(layer => {
                this.map.removeLayer(layer);
            });
        }
    }

    /**
     * Toggle territory visibility
     */
    toggle(locationName) {
        if (this.visibleLayers.has(locationName)) {
            this.hide(locationName);
            return false;
        } else {
            this.show(locationName);
            return true;
        }
    }

    /**
     * Check if a territory is visible
     */
    isVisible(locationName) {
        return this.visibleLayers.has(locationName);
    }

    /**
     * Update faction color scheme
     */
    setFactionColor(faction, color) {
        this.factionColors[faction] = color;
        // Re-render visible layers with new colors
        this.visibleLayers.forEach(name => {
            const layer = this.layers.get(name);
            if (layer) {
                this.map.removeLayer(layer);
                this.show(name);
            }
        });
    }

    /**
     * Clear all territory overlays
     */
    clear() {
        this.layers.forEach(layer => {
            this.map.removeLayer(layer);
        });
        this.layers.clear();
        this.visibleLayers.clear();
    }

    /**
     * Get all loaded territories
     */
    getTerritories() {
        return Array.from(this.layers.keys());
    }

    /**
     * Fit map bounds to a territory
     */
    fitToTerritory(locationName) {
        const layer = this.layers.get(locationName);
        if (layer) {
            try {
                this.map.fitBounds(layer.getBounds(), { padding: [50, 50] });
            } catch (e) {
                console.warn(`[TERRITORY] Could not fit bounds for '${locationName}'`);
            }
        }
    }
}

// Export for use in other modules
window.TerritoryOverlay = TerritoryOverlay;
