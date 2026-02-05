/**
 * Two-Phase BO Visualizer - Gantt Chart Module
 * 
 * Visualizes experimental timing parameters as a Gantt chart.
 * Used to verify optimizer is exploring valid timing sequences.
 */

(function() {
    'use strict';

    /**
     * Render a Gantt chart for pulse sequence visualization
     * 
     * @param {string} containerId - DOM element ID to render into
     * @param {Object} data - Gantt data with rows and timing info
     * @param {Object} options - Rendering options
     */
    function renderGanttChart(containerId, data, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`Gantt container #${containerId} not found`);
            return;
        }

        const config = {
            rowHeight: 40,
            barHeight: 28,
            labelWidth: 120,
            timeAxisHeight: 30,
            maxTime: data.maxTime || 1000,
            colors: {
                oven: { bg: 'linear-gradient(90deg, #f59e0b, #d97706)', border: '#b45309' },
                pi: { bg: 'linear-gradient(90deg, #ef4444, #dc2626)', border: '#991b1b' },
                cooling: { bg: 'linear-gradient(90deg, #3b82f6, #2563eb)', border: '#1d4ed8' },
                rf: { bg: 'linear-gradient(90deg, #10b981, #059669)', border: '#047857' },
                ejection: { bg: 'linear-gradient(90deg, #8b5cf6, #7c3aed)', border: '#5b21b6' },
                hd: { bg: 'linear-gradient(90deg, #ec4899, #db2777)', border: '#9d174d' }
            },
            ...options
        };

        // Clear container
        container.innerHTML = '';

        // Create main wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'gantt-wrapper';
        wrapper.style.cssText = `
            display: flex;
            flex-direction: column;
            height: 100%;
            font-family: 'Segoe UI', system-ui, sans-serif;
        `;

        // Create chart area (rows + timeline)
        const chartArea = document.createElement('div');
        chartArea.className = 'gantt-chart-area';
        chartArea.style.cssText = `
            flex: 1;
            overflow-y: auto;
            padding-right: 8px;
        `;

        // Render rows
        if (data.rows && data.rows.length > 0) {
            data.rows.forEach((row, index) => {
                const rowEl = createGanttRow(row, config, index);
                chartArea.appendChild(rowEl);
            });
        } else {
            chartArea.innerHTML = '<div class="text-gray-500 text-center py-8">No timing data available</div>';
        }

        // Create time axis
        const timeAxis = createTimeAxis(config);

        wrapper.appendChild(chartArea);
        wrapper.appendChild(timeAxis);
        container.appendChild(wrapper);

        // Animate bars entrance
        animateBars(chartArea);

        // Add resize listener
        window.addEventListener('resize', () => {
            updateBarPositions(chartArea, config);
        });
    }

    /**
     * Create a single Gantt row
     */
    function createGanttRow(row, config, index) {
        const rowEl = document.createElement('div');
        rowEl.className = 'gantt-row';
        rowEl.style.cssText = `
            display: flex;
            align-items: center;
            height: ${config.rowHeight}px;
            margin-bottom: 8px;
            position: relative;
        `;

        // Label
        const label = document.createElement('div');
        label.className = 'gantt-label';
        label.textContent = row.label;
        label.style.cssText = `
            width: ${config.labelWidth}px;
            font-size: 0.75rem;
            color: #9ca3af;
            flex-shrink: 0;
            font-weight: 500;
        `;

        // Timeline track
        const track = document.createElement('div');
        track.className = 'gantt-track';
        track.style.cssText = `
            flex: 1;
            height: ${config.barHeight}px;
            position: relative;
            background: rgba(55, 65, 81, 0.3);
            border-radius: 4px;
            overflow: hidden;
        `;

        // Add grid lines to track
        addGridLines(track, config);

        // Bars
        if (row.bars && row.bars.length > 0) {
            row.bars.forEach(bar => {
                const barEl = createGanttBar(bar, config);
                track.appendChild(barEl);
            });
        }

        rowEl.appendChild(label);
        rowEl.appendChild(track);

        return rowEl;
    }

    /**
     * Create a Gantt bar element
     */
    function createGanttBar(bar, config) {
        const barEl = document.createElement('div');
        barEl.className = `gantt-bar gantt-bar-${bar.type}`;
        
        const colorConfig = config.colors[bar.type] || config.colors.oven;
        const startPct = (bar.start / config.maxTime) * 100;
        const durationPct = (bar.duration / config.maxTime) * 100;

        barEl.style.cssText = `
            position: absolute;
            left: ${startPct}%;
            width: ${durationPct}%;
            height: 100%;
            background: ${colorConfig.bg};
            border: 1px solid ${colorConfig.border};
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.65rem;
            font-weight: 500;
            color: white;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            padding: 0 4px;
            transition: all 0.3s ease;
            cursor: pointer;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        `;

        barEl.textContent = bar.label || '';

        // Tooltip
        barEl.title = `${bar.type.toUpperCase()}: ${bar.start.toFixed(1)}ms - ${(bar.start + bar.duration).toFixed(1)}ms (${bar.duration.toFixed(1)}ms)`;

        // Hover effect
        barEl.addEventListener('mouseenter', () => {
            barEl.style.filter = 'brightness(1.2)';
            barEl.style.zIndex = '10';
        });
        barEl.addEventListener('mouseleave', () => {
            barEl.style.filter = 'brightness(1)';
            barEl.style.zIndex = '1';
        });

        return barEl;
    }

    /**
     * Add vertical grid lines to track
     */
    function addGridLines(track, config) {
        const numGridLines = 10;
        for (let i = 0; i <= numGridLines; i++) {
            const line = document.createElement('div');
            const leftPct = (i / numGridLines) * 100;
            line.style.cssText = `
                position: absolute;
                left: ${leftPct}%;
                top: 0;
                bottom: 0;
                width: 1px;
                background: rgba(75, 85, 99, 0.3);
                pointer-events: none;
            `;
            track.appendChild(line);
        }
    }

    /**
     * Create time axis
     */
    function createTimeAxis(config) {
        const axis = document.createElement('div');
        axis.className = 'gantt-time-axis';
        axis.style.cssText = `
            display: flex;
            margin-left: ${config.labelWidth}px;
            padding-top: 8px;
            border-top: 1px solid rgba(75, 85, 99, 0.5);
            height: ${config.timeAxisHeight}px;
        `;

        const numTicks = 5;
        for (let i = 0; i <= numTicks; i++) {
            const tick = document.createElement('div');
            const timeMs = (i / numTicks) * config.maxTime;
            tick.style.cssText = `
                flex: 1;
                text-align: center;
                font-size: 0.65rem;
                color: #6b7280;
                position: relative;
            `;
            tick.textContent = formatTime(timeMs);

            // Add tick marker
            const marker = document.createElement('div');
            marker.style.cssText = `
                position: absolute;
                top: -10px;
                left: 50%;
                transform: translateX(-50%);
                width: 1px;
                height: 6px;
                background: #6b7280;
            `;
            tick.appendChild(marker);

            axis.appendChild(tick);
        }

        return axis;
    }

    /**
     * Format time value for display
     */
    function formatTime(ms) {
        if (ms >= 1000) {
            return `${(ms / 1000).toFixed(1)}s`;
        }
        return `${Math.round(ms)}ms`;
    }

    /**
     * Update bar positions on resize
     */
    function updateBarPositions(chartArea, config) {
        // Bars are positioned with percentages, so they auto-update
        // This function is for any additional resize handling if needed
    }

    /**
     * Animate bars entrance
     */
    function animateBars(container) {
        const bars = container.querySelectorAll('.gantt-bar');
        bars.forEach((bar, index) => {
            bar.style.opacity = '0';
            bar.style.transform = 'scaleX(0)';
            bar.style.transformOrigin = 'left';
            
            setTimeout(() => {
                bar.style.transition = 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
                bar.style.opacity = '1';
                bar.style.transform = 'scaleX(1)';
            }, index * 100);
        });
    }

    /**
     * Validate timing parameters
     * Returns warnings if timings appear unsafe
     */
    function validateTimings(params) {
        const warnings = [];
        
        const ovenDuration = params.oven_duration_ms || params.oven_duration || 500;
        const piDuration = params.pi_laser_duration_ms || params.pi_duration || 200;
        const piStart = params.pi_laser_start_ms || params.pi_start || 100;
        
        // Check PI laser duration (should be minimized to reduce patch charges)
        if (piDuration > 500) {
            warnings.push({
                type: 'warning',
                message: 'PI laser duration is high - may cause excessive patch charging'
            });
        }
        
        // Check if PI laser is within oven cycle
        if (piStart > ovenDuration) {
            warnings.push({
                type: 'error',
                message: 'PI laser starts after oven cycle ends - ionization may fail'
            });
        }
        
        // Check if durations are reasonable
        if (ovenDuration < 100) {
            warnings.push({
                type: 'warning',
                message: 'Oven duration is very short'
            });
        }
        
        return warnings;
    }

    /**
     * Create a warning display element
     */
    function createWarningDisplay(warnings) {
        if (!warnings || warnings.length === 0) return null;
        
        const container = document.createElement('div');
        container.className = 'gantt-warnings';
        container.style.cssText = `
            margin-top: 12px;
            padding: 8px 12px;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 6px;
        `;
        
        warnings.forEach(warning => {
            const item = document.createElement('div');
            item.style.cssText = `
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 0.75rem;
                color: ${warning.type === 'error' ? '#ef4444' : '#f59e0b'};
                margin-bottom: 4px;
            `;
            
            const icon = warning.type === 'error' ? 'fa-exclamation-circle' : 'fa-exclamation-triangle';
            item.innerHTML = `<i class="fa-solid ${icon}"></i> ${warning.message}`;
            
            container.appendChild(item);
        });
        
        return container;
    }

    // Expose API
    window.renderGanttChart = renderGanttChart;
    window.validateTimings = validateTimings;
    window.createWarningDisplay = createWarningDisplay;
    window.animateGanttBars = animateBars;

    // Auto-animate on render if data-animate attribute is present
    document.addEventListener('DOMContentLoaded', () => {
        const animatedContainers = document.querySelectorAll('[data-animate-gantt]');
        animatedContainers.forEach(container => {
            animateBars(container);
        });
    });

})();
