/**
 * Time Slider Controller
 * 
 * Provides temporal analysis controls for filtering heat map data by date range.
 * Supports playback animation through time periods.
 */

class TimeSlider {
    constructor(map, heatmapLayer, options = {}) {
        this.map = map;
        this.heatmapLayer = heatmapLayer;
        this.options = {
            containerId: options.containerId || 'time-slider-container',
            animationSpeed: options.animationSpeed || 1000,  // ms per step
            ...options
        };

        this.currentTimeIndex = 0;
        this.timeSteps = [];
        this.isPlaying = false;
        this.animationInterval = null;
        this.element = null;

        this.onTimeChange = options.onTimeChange || null;
    }

    /**
     * Initialize the time slider UI
     */
    init(timeData) {
        this.timeSteps = this.processTimeData(timeData);
        this.render();
        this.bindEvents();
        return this;
    }

    /**
     * Process time data from heat map locations
     */
    processTimeData(heatmapData) {
        if (!heatmapData || heatmapData.length === 0) {
            return [];
        }

        // Extract all unique dates from the data
        const allDates = new Set();
        heatmapData.forEach(point => {
            if (point.first_mention) allDates.add(point.first_mention);
            if (point.last_mention) allDates.add(point.last_mention);
        });

        // Sort dates chronologically
        const sortedDates = Array.from(allDates).sort();

        // Create time steps (group by month if too many dates)
        if (sortedDates.length > 20) {
            return this.groupByMonth(sortedDates);
        }

        return sortedDates.map(date => ({
            date: date,
            label: this.formatDateLabel(date)
        }));
    }

    /**
     * Group dates by month for cleaner timeline
     */
    groupByMonth(dates) {
        const months = new Map();
        dates.forEach(date => {
            const monthKey = date.substring(0, 7);  // YYYY-MM
            if (!months.has(monthKey)) {
                months.set(monthKey, []);
            }
            months.get(monthKey).push(date);
        });

        return Array.from(months.entries()).map(([month, dates]) => ({
            date: month,
            label: this.formatMonthLabel(month),
            dates: dates
        }));
    }

    /**
     * Format date for display
     */
    formatDateLabel(date) {
        if (!date) return '--';
        try {
            const d = new Date(date);
            return d.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            });
        } catch {
            return date;
        }
    }

    /**
     * Format month label for display
     */
    formatMonthLabel(month) {
        try {
            const [year, monthNum] = month.split('-');
            const d = new Date(parseInt(year), parseInt(monthNum) - 1);
            return d.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short'
            });
        } catch {
            return month;
        }
    }

    /**
     * Render the time slider UI
     */
    render() {
        // Remove existing slider if present
        if (this.element) {
            this.element.remove();
        }

        // Create slider container
        this.element = document.createElement('div');
        this.element.id = this.options.containerId;
        this.element.className = 'tactical-time-slider';

        const timeRange = this.getTimeRange();

        this.element.innerHTML = `
            <div class="time-slider-header">
                <span class="time-label">▸ TEMPORAL ANALYSIS</span>
                <span class="current-time-display" id="time-current">${timeRange.start || '--'}</span>
            </div>
            <div class="time-slider-controls">
                <button class="time-btn" id="time-first" title="First">⏮</button>
                <button class="time-btn" id="time-prev" title="Previous">◀</button>
                <button class="time-btn" id="time-play" title="Play">▶</button>
                <button class="time-btn" id="time-pause" title="Pause" style="display:none;">⏸</button>
                <button class="time-btn" id="time-next" title="Next">▶</button>
                <button class="time-btn" id="time-last" title="Last">⏭</button>
            </div>
            <div class="time-slider-track">
                <input type="range" 
                       id="time-range" 
                       min="0" 
                       max="${this.timeSteps.length - 1}" 
                       value="0"
                       step="1" />
                <div class="time-markers" id="time-markers"></div>
            </div>
            <div class="time-slider-footer">
                <span class="time-range-start">${timeRange.start || '--'}</span>
                <span class="time-step-counter">Step <span id="time-step-num">1</span> of ${this.timeSteps.length}</span>
                <span class="time-range-end">${timeRange.end || '--'}</span>
            </div>
        `;

        // Add to DOM
        const chatArea = document.getElementById('chat-area');
        if (chatArea) {
            chatArea.appendChild(this.element);
        }

        // Render time markers
        this.renderMarkers();

        console.log('[TIME SLIDER] Initialized with', this.timeSteps.length, 'time steps');
    }

    /**
     * Render time markers below slider
     */
    renderMarkers() {
        const markersContainer = document.getElementById('time-markers');
        if (!markersContainer) return;

        markersContainer.innerHTML = '';

        // Show subset of markers to avoid clutter
        const step = Math.ceil(this.timeSteps.length / 10);
        this.timeSteps.forEach((step, index) => {
            if (index % step === 0 || index === this.timeSteps.length - 1) {
                const marker = document.createElement('div');
                marker.className = 'time-marker';
                marker.style.left = `${(index / (this.timeSteps.length - 1)) * 100}%`;
                marker.textContent = step.label;
                markersContainer.appendChild(marker);
            }
        });
    }

    /**
     * Get time range from steps
     */
    getTimeRange() {
        if (this.timeSteps.length === 0) {
            return { start: null, end: null };
        }
        return {
            start: this.timeSteps[0].label,
            end: this.timeSteps[this.timeSteps.length - 1].label
        };
    }

    /**
     * Bind event listeners
     */
    bindEvents() {
        const rangeInput = document.getElementById('time-range');
        const playBtn = document.getElementById('time-play');
        const pauseBtn = document.getElementById('time-pause');
        const prevBtn = document.getElementById('time-prev');
        const nextBtn = document.getElementById('time-next');
        const firstBtn = document.getElementById('time-first');
        const lastBtn = document.getElementById('time-last');

        if (rangeInput) {
            rangeInput.addEventListener('input', (e) => {
                this.goToStep(parseInt(e.target.value));
            });
        }

        if (playBtn) {
            playBtn.addEventListener('click', () => this.play());
        }

        if (pauseBtn) {
            pauseBtn.addEventListener('click', () => this.pause());
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', () => this.step(-1));
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => this.step(1));
        }

        if (firstBtn) {
            firstBtn.addEventListener('click', () => this.goToStep(0));
        }

        if (lastBtn) {
            lastBtn.addEventListener('click', () => this.goToStep(this.timeSteps.length - 1));
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT') return;  // Don't interfere with text input

            switch (e.key) {
                case 'ArrowLeft':
                    this.step(-1);
                    break;
                case 'ArrowRight':
                    this.step(1);
                    break;
                case ' ':
                    e.preventDefault();
                    this.togglePlayPause();
                    break;
            }
        });
    }

    /**
     * Go to specific time step
     */
    goToStep(index) {
        if (index < 0) index = 0;
        if (index >= this.timeSteps.length) index = this.timeSteps.length - 1;

        this.currentTimeIndex = index;
        const step = this.timeSteps[index];

        // Update UI
        const rangeInput = document.getElementById('time-range');
        const currentDisplay = document.getElementById('time-current');
        const stepNum = document.getElementById('time-step-num');

        if (rangeInput) rangeInput.value = index;
        if (currentDisplay) currentDisplay.textContent = step.label;
        if (stepNum) stepNum.textContent = index + 1;

        // Apply time filter to heatmap
        this.applyTimeFilter(step);

        // Notify callback
        if (this.onTimeChange) {
            this.onTimeChange(step);
        }
    }

    /**
     * Step forward or backward
     */
    step(direction) {
        this.goToStep(this.currentTimeIndex + direction);
    }

    /**
     * Apply time filter to heatmap
     */
    applyTimeFilter(step) {
        if (!this.heatmapLayer) return;

        // Filter heatmap data by date
        const filteredData = this.heatmapLayer.data?.filter(point => {
            // Include points that were mentioned before or during this time
            return point.last_mention && point.last_mention <= step.date;
        }) || [];

        this.heatmapLayer.render(filteredData);
    }

    /**
     * Start playback animation
     */
    play() {
        if (this.isPlaying) return;

        this.isPlaying = true;
        this.updatePlayPauseButtons();

        this.animationInterval = setInterval(() => {
            if (this.currentTimeIndex >= this.timeSteps.length - 1) {
                this.goToStep(0);  // Loop back to start
            } else {
                this.step(1);
            }
        }, this.options.animationSpeed);

        console.log('[TIME SLIDER] Playback started');
    }

    /**
     * Pause playback
     */
    pause() {
        this.isPlaying = false;
        this.updatePlayPauseButtons();

        if (this.animationInterval) {
            clearInterval(this.animationInterval);
            this.animationInterval = null;
        }

        console.log('[TIME SLIDER] Playback paused');
    }

    /**
     * Toggle play/pause
     */
    togglePlayPause() {
        if (this.isPlaying) {
            this.pause();
        } else {
            this.play();
        }
    }

    /**
     * Update play/pause button visibility
     */
    updatePlayPauseButtons() {
        const playBtn = document.getElementById('time-play');
        const pauseBtn = document.getElementById('time-pause');

        if (playBtn && pauseBtn) {
            playBtn.style.display = this.isPlaying ? 'none' : 'inline-block';
            pauseBtn.style.display = this.isPlaying ? 'inline-block' : 'none';
        }
    }

    /**
     * Show the time slider
     */
    show() {
        if (this.element) {
            this.element.style.display = 'block';
        }
    }

    /**
     * Hide the time slider
     */
    hide() {
        if (this.element) {
            this.element.style.display = 'none';
        }
        this.pause();
    }

    /**
     * Toggle visibility
     */
    toggle() {
        if (this.element && this.element.style.display === 'none') {
            this.show();
        } else {
            this.hide();
        }
    }

    /**
     * Destroy the time slider
     */
    destroy() {
        this.pause();
        if (this.element) {
            this.element.remove();
            this.element = null;
        }
    }
}

// Export for use in other modules
window.TimeSlider = TimeSlider;
