/**
 * Cluster Analysis Controller
 * 
 * Visualizes location clusters showing co-occurring geographic entities.
 * Draws connection lines between related locations with strength indicators.
 */

class ClusterAnalysis {
    constructor(map) {
        this.map = map;
        this.clusters = [];
        this.clusterGroup = null;
        this.markerClusterGroup = null;
        this.isVisible = false;
        
        // Visual styling
        this.styles = {
            connectionColor: '#00ffff',  // Cyan
            connectionWeight: 2,
            connectionOpacity: 0.6,
            clusterHullColor: '#00ffff',
            clusterHullFillOpacity: 0.15,
            markerColor: '#00ffff'
        };
    }

    /**
     * Load cluster data from API
     */
    async loadClusters(query = null) {
        try {
            const params = query ? `?query=${encodeURIComponent(query)}` : '';
            const response = await fetch(`/geo/clusters${params}`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            this.clusters = await response.json();
            console.log(`[CLUSTER] Loaded ${this.clusters.length} location clusters`);
            
            if (this.isVisible) {
                this.render();
            }
            
            return this.clusters;
        } catch (error) {
            console.error('[CLUSTER] Failed to load clusters:', error);
            return [];
        }
    }

    /**
     * Render cluster visualization
     */
    render() {
        this.clear();

        if (!this.clusters || this.clusters.length === 0) {
            console.warn('[CLUSTER] No clusters to render');
            return;
        }

        // Create layer group for all clusters
        this.clusterGroup = L.layerGroup();

        this.clusters.forEach((cluster, index) => {
            this.renderCluster(cluster, index);
        });

        if (this.isVisible) {
            this.clusterGroup.addTo(this.map);
        }

        console.log('[CLUSTER] Rendered cluster visualization');
    }

    /**
     * Render a single cluster
     */
    renderCluster(cluster, index) {
        const { center, related_locations, connections } = cluster;

        // Add center marker
        const centerMarker = this.createLocationMarker(
            center.lat,
            center.lng,
            center.name,
            true  // Is center
        );
        this.clusterGroup.addLayer(centerMarker);

        // Add related location markers
        related_locations.forEach(loc => {
            const marker = this.createLocationMarker(
                loc.lat,
                loc.lng,
                loc.name,
                false,
                loc.strength
            );
            this.clusterGroup.addLayer(marker);
        });

        // Draw connection lines
        connections.forEach(conn => {
            const polyline = L.polyline([conn.from, conn.to], {
                color: this.styles.connectionColor,
                weight: this.styles.connectionWeight,
                opacity: Math.min(1, this.styles.connectionOpacity + (conn.strength * 0.1)),
                dashArray: '5, 5',
                lineCap: 'round'
            });

            // Add popup showing connection strength
            polyline.bindPopup(`
                <div style="font-family: 'Share Tech Mono', monospace;">
                    <strong>Connection Strength:</strong> ${conn.strength}<br/>
                    <em>Co-mentioned in ${conn.strength} documents</em>
                </div>
            `);

            this.clusterGroup.addLayer(polyline);
        });

        // Draw cluster hull (boundary polygon)
        const hullPoints = [
            [center.lat, center.lng],
            ...related_locations.map(loc => [loc.lat, loc.lng])
        ];

        const hull = this.computeConvexHull(hullPoints);
        if (hull && hull.length >= 3) {
            const hullPolygon = L.polygon(hull, {
                color: this.styles.clusterHullColor,
                weight: 1,
                fillOpacity: this.styles.clusterHullFillOpacity,
                dashArray: '3, 3'
            });

            hullPolygon.bindPopup(`
                <div style="font-family: 'Share Tech Mono', monospace;">
                    <strong>Cluster ${index + 1}</strong><br/>
                    ${related_locations.length + 1} locations<br/>
                    ${connections.length} connections
                </div>
            `);

            this.clusterGroup.addLayer(hullPolygon);
        }
    }

    /**
     * Create a location marker
     */
    createLocationMarker(lat, lng, name, isCenter = false, strength = 0) {
        const iconSize = isCenter ? 20 : 12;
        const pulseSize = isCenter ? 30 : 16;

        const icon = L.divIcon({
            className: 'cluster-marker',
            html: `
                <div class="marker-pulse" style="
                    width: ${pulseSize}px;
                    height: ${pulseSize}px;
                    background: rgba(0, 255, 255, 0.3);
                    border-radius: 50%;
                    position: absolute;
                    top: -${pulseSize / 2}px;
                    left: -${pulseSize / 2}px;
                    animation: markerPulse 2s infinite;
                "></div>
                <div style="
                    width: ${iconSize}px;
                    height: ${iconSize}px;
                    background: ${this.styles.markerColor};
                    border-radius: 50%;
                    border: 2px solid #fff;
                    box-shadow: 0 0 10px ${this.styles.markerColor};
                "></div>
            `,
            iconSize: [iconSize, iconSize],
            iconAnchor: [iconSize / 2, iconSize / 2]
        });

        const marker = L.marker([lat, lng], { icon });
        
        marker.bindPopup(`
            <div style="font-family: 'Share Tech Mono', monospace;">
                <strong>${name}</strong><br/>
                ${isCenter ? '<em>Cluster Center</em>' : `Strength: ${strength}`}<br/>
                <small>${lat.toFixed(4)}, ${lng.toFixed(4)}</small>
            </div>
        `);

        return marker;
    }

    /**
     * Compute convex hull of points using Graham scan
     */
    computeConvexHull(points) {
        if (points.length < 3) return points;

        // Convert to array for sorting
        const pts = points.map(p => ({ x: p[0], y: p[1] }));

        // Find the lowest point (or leftmost in case of tie)
        let start = 0;
        for (let i = 1; i < pts.length; i++) {
            if (pts[i].x < pts[start].x || 
                (pts[i].x === pts[start].x && pts[i].y < pts[start].y)) {
                start = i;
            }
        }

        const startPt = pts[start];
        
        // Sort points by polar angle with respect to start point
        pts.splice(start, 1);
        pts.sort((a, b) => {
            const angleA = Math.atan2(a.x - startPt.x, a.y - startPt.y);
            const angleB = Math.atan2(b.x - startPt.x, b.y - startPt.y);
            return angleA - angleB;
        });

        // Add start point back at the end
        pts.push(startPt);

        // Graham scan
        const hull = [startPt, pts[0]];
        
        for (let i = 1; i < pts.length; i++) {
            while (hull.length > 1) {
                const top = hull[hull.length - 1];
                const nextToTop = hull[hull.length - 2];
                
                // Cross product to determine turn direction
                const cross = (top.x - nextToTop.x) * (pts[i].y - nextToTop.y) -
                             (top.y - nextToTop.y) * (pts[i].x - nextToTop.x);
                
                if (cross > 0) {
                    hull.pop();
                } else {
                    break;
                }
            }
            hull.push(pts[i]);
        }

        // Convert back to lat/lng format
        return hull.map(p => [p.x, p.y]);
    }

    /**
     * Toggle cluster visibility
     */
    toggle() {
        this.isVisible = !this.isVisible;
        
        if (this.isVisible) {
            if (!this.clusterGroup && this.clusters.length > 0) {
                this.render();
            } else if (this.clusterGroup) {
                this.clusterGroup.addTo(this.map);
            }
        } else {
            if (this.clusterGroup) {
                this.map.removeLayer(this.clusterGroup);
            }
        }

        return this.isVisible;
    }

    /**
     * Show cluster visualization
     */
    show() {
        this.isVisible = true;
        if (!this.clusterGroup && this.clusters.length > 0) {
            this.render();
        } else if (this.clusterGroup) {
            this.clusterGroup.addTo(this.map);
        }
    }

    /**
     * Hide cluster visualization
     */
    hide() {
        this.isVisible = false;
        if (this.clusterGroup) {
            this.map.removeLayer(this.clusterGroup);
        }
    }

    /**
     * Clear all clusters
     */
    clear() {
        if (this.clusterGroup) {
            this.map.removeLayer(this.clusterGroup);
            this.clusterGroup = null;
        }
    }

    /**
     * Fit map bounds to show all clusters
     */
    fitToClusters() {
        if (!this.clusterGroup) return;

        const bounds = this.clusterGroup.getBounds();
        if (bounds.isValid()) {
            this.map.fitBounds(bounds, { padding: [50, 50] });
        }
    }

    /**
     * Get cluster at specific coordinates
     */
    getClusterAt(lat, lng, radius = 0.5) {
        for (const cluster of this.clusters) {
            const distance = Math.sqrt(
                Math.pow(cluster.center.lat - lat, 2) + 
                Math.pow(cluster.center.lng - lng, 2)
            );
            if (distance < radius) {
                return cluster;
            }
        }
        return null;
    }

    /**
     * Get statistics about clusters
     */
    getStats() {
        if (!this.clusters || this.clusters.length === 0) {
            return {
                clusterCount: 0,
                totalLocations: 0,
                totalConnections: 0,
                avgConnectionsPerCluster: 0
            };
        }

        const totalLocations = this.clusters.reduce(
            (sum, c) => sum + c.related_locations.length + 1, 0
        );
        const totalConnections = this.clusters.reduce(
            (sum, c) => sum + c.connections.length, 0
        );

        return {
            clusterCount: this.clusters.length,
            totalLocations,
            totalConnections,
            avgConnectionsPerCluster: totalConnections / this.clusters.length
        };
    }
}

// Export for use in other modules
window.ClusterAnalysis = ClusterAnalysis;
