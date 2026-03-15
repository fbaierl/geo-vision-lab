/**
 * Heatmap Layer Controller
 * 
 * Manages heat map visualization for geographic intensity data.
 * Integrates with Leaflet.heat plugin for rendering.
 */

class HeatmapLayer {
    constructor(map) {
        this.map = map;
        this.heatLayer = null;
        this.data = null;
        this.isVisible = false;
        this.options = {
            radius: 25,
            blur: 15,
            maxZoom: 10,
            minOpacity: 0.4,
            gradient: {
                0.0: '#00ff00',  // Green - low intensity
                0.3: '#80ff00',  // Light green
                0.5: '#ffff00',  // Yellow - medium intensity
                0.7: '#ff8000',  // Orange
                0.9: '#ff2000',  // Red
                1.0: '#ff0000'   // Red - high intensity
            }
        };
    }

    /**
     * Load heat map data from API
     */
    async loadData(filters = {}) {
        try {
            const params = new URLSearchParams();
            if (filters.min_intensity) params.append('min_intensity', filters.min_intensity);
            if (filters.date_from) params.append('date_from', filters.date_from);
            if (filters.date_to) params.append('date_to', filters.date_to);

            const response = await fetch(`/geo/heatmap?${params}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            this.data = await response.json();
            console.log(`[HEATMAP] Loaded ${this.data.length} heat points`);
            return this.data;
        } catch (error) {
            console.error('[HEATMAP] Failed to load data:', error);
            return [];
        }
    }

    /**
     * Render heat map on the map
     */
    render(data = null) {
        if (data) {
            this.data = data;
        }

        if (!this.data || this.data.length === 0) {
            console.warn('[HEATMAP] No data to render');
            return;
        }

        // Remove existing layer
        if (this.heatLayer) {
            this.map.removeLayer(this.heatLayer);
        }

        // Convert to leaflet.heat format: [lat, lng, intensity]
        const heatPoints = this.data.map(point => [
            point.lat,
            point.lng,
            point.intensity
        ]);

        // Create heat layer
        this.heatLayer = L.heatLayer(heatPoints, this.options);
        
        if (this.isVisible) {
            this.heatLayer.addTo(this.map);
        }

        console.log('[HEATMAP] Rendered heat layer');
    }

    /**
     * Toggle heat map visibility
     */
    toggle() {
        this.isVisible = !this.isVisible;
        
        if (this.isVisible) {
            if (!this.heatLayer && this.data) {
                this.render();
            } else if (this.heatLayer) {
                this.heatLayer.addTo(this.map);
            }
        } else {
            if (this.heatLayer) {
                this.map.removeLayer(this.heatLayer);
            }
        }

        return this.isVisible;
    }

    /**
     * Show heat map
     */
    show() {
        this.isVisible = true;
        if (!this.heatLayer && this.data) {
            this.render();
        } else if (this.heatLayer) {
            this.heatLayer.addTo(this.map);
        }
    }

    /**
     * Hide heat map
     */
    hide() {
        this.isVisible = false;
        if (this.heatLayer) {
            this.map.removeLayer(this.heatLayer);
        }
    }

    /**
     * Update heat map options
     */
    setOptions(options) {
        this.options = { ...this.options, ...options };
        if (this.heatLayer) {
            this.map.removeLayer(this.heatLayer);
            this.heatLayer = null;
            this.render();
        }
    }

    /**
     * Get statistics about heat map data
     */
    getStats() {
        if (!this.data || this.data.length === 0) {
            return {
                count: 0,
                avgIntensity: 0,
                maxIntensity: 0,
                minIntensity: 0
            };
        }

        const intensities = this.data.map(p => p.intensity);
        return {
            count: this.data.length,
            avgIntensity: intensities.reduce((a, b) => a + b, 0) / intensities.length,
            maxIntensity: Math.max(...intensities),
            minIntensity: Math.min(...intensities)
        };
    }

    /**
     * Get location details for a point
     */
    getLocationAt(lat, lng) {
        if (!this.data) return null;

        // Find closest point
        let closest = null;
        let minDistance = Infinity;

        for (const point of this.data) {
            const distance = Math.sqrt(
                Math.pow(point.lat - lat, 2) + Math.pow(point.lng - lng, 2)
            );
            if (distance < minDistance && distance < 0.1) {
                minDistance = distance;
                closest = point;
            }
        }

        return closest;
    }

    /**
     * Clear heat map data and layer
     */
    clear() {
        if (this.heatLayer) {
            this.map.removeLayer(this.heatLayer);
            this.heatLayer = null;
        }
        this.data = null;
        this.isVisible = false;
    }
}

// Export for use in other modules
window.HeatmapLayer = HeatmapLayer;
