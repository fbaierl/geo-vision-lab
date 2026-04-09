/**
 * Panopticon 3D Globe — Real-time global aircraft visualization
 * Uses globe.gl (Three.js wrapper) for interactive 3D globe rendering
 *
 * Phase 1: Core globe + aircraft. Data fetches only when user zooms in
 * past a threshold to avoid aggressive OpenSky API rate limiting.
 */

import { escapeHtml } from './utils.js';

let globeInstance = null;
let aircraftData = [];
let isInitialized = false;
let dataFetchedForZoom = false; // Track whether we fetched for current zoom level

// Configuration
const CONFIG = {
    zoomFetchThreshold: 100, // Altitude in km below which we fetch (globe camera altitude)
    apiUrl: '/api/panopticon/aircraft',
    colors: {
        ground: '#88c0d0',
        lowAltitude: '#5ec0ff',
        highAltitude: '#3daee9',
        background: '#0d0f14',
        atmosphere: '#3daee9',
    },
};

/**
 * Initialize the panopticon globe
 * @param {HTMLElement} container - The DOM container for the globe
 */
export async function initPanopticon(container) {
    if (!container) {
        console.error('Panopticon: container not found');
        return;
    }

    if (isInitialized) return;

    // Show loading state
    showLoading(container);

    try {
        // Load globe.gl if not available
        if (typeof window.Globe !== 'function') {
            await loadGlobeGL();
        }

        // Wait for container to have dimensions
        await waitForDimensions(container);

        // Initialize globe — new Globe(container) with options
        globeInstance = new window.Globe(container, { animateIn: true })
            .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-dark.jpg')
            .bumpImageUrl('https://unpkg.com/three-globe/example/img/earth-topology.png')
            .backgroundColor(CONFIG.colors.background)
            .atmosphereColor(CONFIG.colors.atmosphere)
            .atmosphereAltitude(0.15)
            .pointAltitude(0.01)
            .pointColor((d) => getAircraftColor(d))
            .pointRadius(0.3)
            .pointResolution(12)
            .pointsMerge(false)
            .onPointHover(onAircraftHover)
            .pointLabel((d) => buildTooltip(d))
            .pointsData([]); // Start empty

        // Controls
        globeInstance.controls().autoRotate = true;
        globeInstance.controls().autoRotateSpeed = 0.5;
        globeInstance.controls().enableDamping = true;
        globeInstance.controls().dampingFactor = 0.05;

        // Monitor zoom changes — fetch aircraft when user zooms in close enough
        globeInstance.controls().addEventListener('change', onCameraChange);

        isInitialized = true;
        hideLoading(container);

        // Set up resize observer
        setupResizeObserver(container);

    } catch (error) {
        console.error('Panopticon: init error', error);
        showError(container, `Failed to initialize: ${error.message}`);
    }
}

/**
 * Wait for container to have non-zero dimensions
 */
function waitForDimensions(container) {
    return new Promise((resolve, reject) => {
        if (container.offsetWidth > 0 && container.offsetHeight > 0) {
            resolve();
            return;
        }

        let attempts = 0;
        const maxAttempts = 120; // ~2 seconds at 60fps

        function check() {
            attempts++;
            if (container.offsetWidth > 0 && container.offsetHeight > 0) {
                resolve();
                return;
            }
            if (attempts >= maxAttempts) {
                reject(new Error('Container never got dimensions'));
                return;
            }
            requestAnimationFrame(check);
        }

        requestAnimationFrame(check);
    });
}

/**
 * Load globe.gl from CDN (UMD build)
 */
function loadGlobeGL() {
    return new Promise((resolve, reject) => {
        if (typeof window.Globe === 'function') {
            resolve();
            return;
        }
        const script = document.createElement('script');
        script.src = 'https://unpkg.com/globe.gl@2/dist/globe.gl.min.js';
        script.onload = () => {
            if (typeof window.Globe === 'function') {
                resolve();
            } else {
                reject(new Error(`globe.gl loaded but Globe is not a function, got: ${typeof window.Globe}`));
            }
        };
        script.onerror = () => reject(new Error('Failed to load globe.gl'));
        document.head.appendChild(script);
    });
}

/**
 * Called on every camera change (zoom/pan/rotate)
 * Fetches aircraft data when user zooms in close enough.
 */
function onCameraChange() {
    if (!globeInstance || !isInitialized) return;

    const altitude = globeInstance.pointOfView()?.altitude;
    if (altitude === undefined) return;

    // altitude is in globe "units" — lower = zoomed in
    // Default globe scale: ~200 is fully zoomed out, ~50 is close to surface
    const shouldFetch = altitude < CONFIG.zoomFetchThreshold;

    if (shouldFetch && !dataFetchedForZoom) {
        dataFetchedForZoom = true;
        fetchAndRenderAircraft();

        // Stop auto-rotation when data is fetched
        if (globeInstance.controls().autoRotate) {
            globeInstance.controls().autoRotate = false;
        }
    } else if (!shouldFetch) {
        // Reset flag so we fetch again next time they zoom in
        dataFetchedForZoom = false;

        // If they zoom back out far enough, clear points
        if (altitude > CONFIG.zoomFetchThreshold * 1.5 && aircraftData.length > 0) {
            aircraftData = [];
            globeInstance.pointsData([]);
            updateStatusBar({ count: 0, cached: true });
        }
    }
}

/**
 * Fetch aircraft data from API
 */
async function fetchAndRenderAircraft() {
    try {
        const response = await fetch(CONFIG.apiUrl, { signal: AbortSignal.timeout(15000) });

        if (!response.ok) {
            throw new Error(`API ${response.status}`);
        }

        const data = await response.json();
        aircraftData = data.aircraft || [];

        if (globeInstance) {
            globeInstance.pointsData(aircraftData);
        }

        updateStatusBar(data);

        if (data.error) {
            console.warn('Panopticon API:', data.error);
        }

    } catch (error) {
        if (error.name === 'AbortError') {
            console.warn('Panopticon: request timed out');
        } else {
            console.error('Panopticon: fetch error', error);
        }
        showErrorState('Failed to fetch');
    }
}

/**
 * Hover handler
 */
function onAircraftHover(d) {
    // globe.gl handles tooltip via pointLabel
}

/**
 * Build tooltip HTML
 */
function buildTooltip(d) {
    if (!d || !d.icao24) return '';

    const callsign = d.callsign || 'N/A';
    const altitude = d.altitude != null ? `${Math.round(d.altitude).toLocaleString()} ft` : 'N/A';
    const speed = d.velocity != null ? `${Math.round(d.velocity * 1.944)} kts` : 'N/A';
    const heading = d.heading != null ? `${Math.round(d.heading)}°` : 'N/A';
    const status = d.on_ground ? 'On Ground' : 'Airborne';

    return `
        <div class="panopticon-tooltip">
            <div class="tooltip-callsign">${escapeHtml(callsign) || d.icao24}</div>
            <div class="tooltip-row"><span class="tooltip-label">ICAO24:</span><span class="tooltip-value">${escapeHtml(d.icao24)}</span></div>
            <div class="tooltip-row"><span class="tooltip-label">Status:</span><span class="tooltip-value">${status}</span></div>
            <div class="tooltip-row"><span class="tooltip-label">Altitude:</span><span class="tooltip-value">${altitude}</span></div>
            <div class="tooltip-row"><span class="tooltip-label">Speed:</span><span class="tooltip-value">${speed}</span></div>
            <div class="tooltip-row"><span class="tooltip-label">Heading:</span><span class="tooltip-value">${heading}</span></div>
        </div>
    `;
}

/**
 * Color aircraft by altitude
 */
function getAircraftColor(d) {
    if (d.on_ground) return CONFIG.colors.ground;
    return (d.altitude || 0) < 10000 ? CONFIG.colors.lowAltitude : CONFIG.colors.highAltitude;
}

/**
 * Update status bar
 */
function updateStatusBar(data) {
    const countEl = document.getElementById('panopticon-aircraft-count');
    const timeEl = document.getElementById('panopticon-timestamp');

    if (countEl) {
        countEl.textContent = `${data.count || 0} aircraft`;
        countEl.style.color = '';
    }
    if (timeEl && data.timestamp) {
        timeEl.textContent = `Updated: ${new Date(data.timestamp).toLocaleTimeString()}`;
    }
}

function showErrorState(msg) {
    const countEl = document.getElementById('panopticon-aircraft-count');
    if (countEl) {
        countEl.textContent = msg;
        countEl.style.color = '#e53935';
    }
}

/**
 * Show loading
 */
function showLoading(container) {
    container.innerHTML = `
        <div class="panopticon-loading">
            <div class="spinner"></div>
            <div class="loading-text">Initializing Panopticon...</div>
        </div>
    `;
}

function hideLoading(container) {
    container.querySelector('.panopticon-loading')?.remove();
}

function showError(container, msg) {
    container.innerHTML = `
        <div class="panopticon-error-state">
            <div class="error-icon">⚠</div>
            <div class="error-text">${escapeHtml(msg)}</div>
        </div>
    `;
}

/**
 * Resize observer
 */
function setupResizeObserver(container) {
    const obs = new ResizeObserver(() => {
        if (globeInstance?.renderer()) {
            globeInstance.renderer().setSize(container.offsetWidth, container.offsetHeight);
        }
    });
    obs.observe(container);
}

/**
 * Cleanup
 */
export function cleanupPanopticon() {
    if (globeInstance) {
        globeInstance.renderer()?.dispose();
        globeInstance = null;
    }
    aircraftData = [];
    isInitialized = false;
    dataFetchedForZoom = false;
}
