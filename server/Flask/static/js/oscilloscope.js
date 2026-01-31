/**
 * Oscilloscope-style Real-time Charting
 * Lightweight canvas-based scrolling charts for telemetry display
 */

class OscilloscopeChart {
    /**
     * Create an oscilloscope-style scrolling chart
     * @param {HTMLCanvasElement} canvas - The canvas element
     * @param {Object} options - Configuration options
     */
    constructor(canvas, options = {}) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        
        // Configuration
        this.options = {
            color: options.color || '#00ff00',
            lineWidth: options.lineWidth || 1.5,
            gridColor: options.gridColor || 'rgba(200, 200, 200, 0.3)',
            textColor: options.textColor || '#737373',
            backgroundColor: options.backgroundColor || '#ffffff',
            timeWindow: options.timeWindow || 60, // seconds to display
            showGrid: options.showGrid !== false,
            showValue: options.showValue !== false,
            valueDecimals: options.valueDecimals !== undefined ? options.valueDecimals : 2,
            unit: options.unit || '',
            label: options.label || '',
            yAxisPadding: options.yAxisPadding || 0.1, // 10% padding for auto-scale
            mode: options.mode || 'line', // 'line' or 'scatter'
            pointRadius: options.pointRadius || 3, // radius for scatter mode
            ...options
        };
        
        // Data buffer - stores {timestamp, value} points
        this.data = [];
        this.maxDataPoints = Math.ceil(this.options.timeWindow * 20); // 20Hz max buffer
        
        // Current display metrics
        this.currentValue = null;
        this.lastRenderTime = 0;
        this.yRange = { min: 0, max: 1 }; // Cached Y range
        
        // Handle high DPI displays
        this.dpr = window.devicePixelRatio || 1;
        this.resize();
        
        // Bind resize handler
        window.addEventListener('resize', () => this.resize());
    }
    
    /**
     * Resize canvas for high DPI displays
     */
    resize() {
        const rect = this.canvas.getBoundingClientRect();
        this.width = rect.width;
        this.height = rect.height;
        
        this.canvas.width = this.width * this.dpr;
        this.canvas.height = this.height * this.dpr;
        
        this.ctx.scale(this.dpr, this.dpr);
        
        // Chart area (with padding for labels)
        // Top padding for value display, bottom for time axis, left for Y labels
        this.padding = { 
            top: 28, 
            right: 15, 
            bottom: 22, 
            left: 60 
        };
        this.chartWidth = this.width - this.padding.left - this.padding.right;
        this.chartHeight = this.height - this.padding.top - this.padding.bottom;
    }
    
    /**
     * Add a new data point
     * @param {number} timestamp - Unix timestamp (seconds)
     * @param {number} value - The value to plot
     */
    addPoint(timestamp, value) {
        this.data.push({ t: timestamp, v: value });
        this.currentValue = value;
        
        // Remove old data outside the time window
        const cutoff = timestamp - this.options.timeWindow;
        while (this.data.length > 0 && this.data[0].t < cutoff) {
            this.data.shift();
        }
        
        // Limit buffer size
        if (this.data.length > this.maxDataPoints) {
            this.data = this.data.slice(-this.maxDataPoints);
        }
        
        // Update Y range cache
        this.updateYRange();
    }
    
    /**
     * Update cached Y-axis range based on current data
     */
    updateYRange() {
        if (this.data.length === 0) return;
        
        const values = this.data.map(p => p.v);
        let min = Math.min(...values);
        let max = Math.max(...values);
        
        // Add padding
        const range = max - min;
        const padding = range === 0 ? Math.abs(max) * 0.1 || 0.1 : range * this.options.yAxisPadding;
        
        this.yRange.min = min - padding;
        this.yRange.max = max + padding;
        
        // Ensure we don't have zero range
        if (this.yRange.max === this.yRange.min) {
            this.yRange.max += 0.1;
            this.yRange.min -= 0.1;
        }
    }
    
    /**
     * Get Y coordinate for a value
     */
    getY(value) {
        const range = this.yRange.max - this.yRange.min;
        if (range === 0) return this.padding.top + this.chartHeight / 2;
        
        const normalized = (value - this.yRange.min) / range;
        return this.padding.top + this.chartHeight * (1 - normalized);
    }
    
    /**
     * Get X coordinate for a timestamp
     */
    getX(timestamp, now) {
        const age = now - timestamp;
        const normalized = age / this.options.timeWindow;
        return this.padding.left + this.chartWidth * (1 - normalized);
    }
    
    /**
     * Format timestamp to HH:MM:SS
     */
    formatTime(timestamp) {
        const date = new Date(timestamp * 1000);
        return date.toTimeString().split(' ')[0]; // HH:MM:SS
    }
    
    /**
     * Format value for display
     */
    formatValue(value) {
        if (value === null || value === undefined) return '--';
        
        const absVal = Math.abs(value);
        if (absVal >= 1000000) {
            return (value / 1000000).toFixed(1) + 'M';
        } else if (absVal >= 1000) {
            return (value / 1000).toFixed(1) + 'k';
        } else if (absVal >= 1) {
            return value.toFixed(this.options.valueDecimals);
        } else if (absVal >= 0.001) {
            return value.toFixed(this.options.valueDecimals + 2);
        } else if (absVal > 0) {
            return value.toExponential(2);
        } else {
            return '0';
        }
    }
    
    /**
     * Draw grid lines and axis labels
     */
    drawGrid(now) {
        this.ctx.strokeStyle = this.options.gridColor;
        this.ctx.lineWidth = 1;
        this.ctx.font = '10px Inter, sans-serif';
        this.ctx.fillStyle = this.options.textColor;
        
        // Horizontal grid lines (5 lines) + Y-axis labels
        this.ctx.textAlign = 'right';
        this.ctx.textBaseline = 'middle';
        
        for (let i = 0; i <= 4; i++) {
            const y = this.padding.top + (this.chartHeight * i / 4);
            
            // Grid line
            this.ctx.beginPath();
            this.ctx.moveTo(this.padding.left, y);
            this.ctx.lineTo(this.padding.left + this.chartWidth, y);
            this.ctx.stroke();
            
            // Y-axis label
            const value = this.yRange.max - (this.yRange.max - this.yRange.min) * (i / 4);
            const label = this.formatValue(value);
            this.ctx.fillText(label, this.padding.left - 6, y);
        }
        
        // Vertical grid lines (time markers) - exactly at the edge of time window
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'top';
        
        // Draw time labels at specific intervals
        const timeSteps = 5; // Number of vertical lines
        for (let i = 0; i < timeSteps; i++) {
            const x = this.padding.left + (this.chartWidth * i / (timeSteps - 1));
            
            // Grid line
            this.ctx.beginPath();
            this.ctx.moveTo(x, this.padding.top);
            this.ctx.lineTo(x, this.padding.top + this.chartHeight);
            this.ctx.stroke();
            
            // Time label - calculate actual time for this position
            const timeOffset = this.options.timeWindow * (1 - i / (timeSteps - 1));
            const labelTime = now - timeOffset;
            const timeLabel = this.formatTime(labelTime);
            
            this.ctx.fillText(timeLabel, x, this.padding.top + this.chartHeight + 4);
        }
        
        // Draw axes
        this.ctx.strokeStyle = '#999999';
        this.ctx.lineWidth = 1;
        
        // Y-axis
        this.ctx.beginPath();
        this.ctx.moveTo(this.padding.left, this.padding.top);
        this.ctx.lineTo(this.padding.left, this.padding.top + this.chartHeight);
        this.ctx.stroke();
        
        // X-axis
        this.ctx.beginPath();
        this.ctx.moveTo(this.padding.left, this.padding.top + this.chartHeight);
        this.ctx.lineTo(this.padding.left + this.chartWidth, this.padding.top + this.chartHeight);
        this.ctx.stroke();
    }
    
    /**
     * Render the chart
     */
    render() {
        const now = Date.now() / 1000; // Current time in seconds
        const cutoff = now - this.options.timeWindow;
        
        // Clear canvas
        this.ctx.fillStyle = this.options.backgroundColor;
        this.ctx.fillRect(0, 0, this.width, this.height);
        
        // Update Y range before drawing
        this.updateYRange();
        
        // Draw grid
        if (this.options.showGrid) {
            this.drawGrid(now);
        }
        
        // Draw data - either as connected lines or scattered circles
        if (this.data.length >= 1) {
            // Filter to only visible points (within time window)
            const visiblePoints = [];
            for (const point of this.data) {
                if (point.t > cutoff && point.t <= now) {
                    visiblePoints.push(point);
                }
            }
            
            if (visiblePoints.length >= 1) {
                if (this.options.mode === 'scatter') {
                    // Scatter mode: draw circles at each point
                    this.ctx.fillStyle = this.options.color;
                    const radius = this.options.pointRadius;
                    
                    for (const point of visiblePoints) {
                        const x = this.getX(point.t, now);
                        const y = this.getY(point.v);
                        
                        this.ctx.beginPath();
                        this.ctx.arc(x, y, radius, 0, Math.PI * 2);
                        this.ctx.fill();
                    }
                } else {
                    // Line mode: connect consecutive points
                    if (visiblePoints.length >= 2) {
                        this.ctx.strokeStyle = this.options.color;
                        this.ctx.lineWidth = this.options.lineWidth;
                        this.ctx.lineJoin = 'round';
                        this.ctx.lineCap = 'round';
                        
                        this.ctx.beginPath();
                        
                        // Start at first visible point
                        let prevX = this.getX(visiblePoints[0].t, now);
                        let prevY = this.getY(visiblePoints[0].v);
                        this.ctx.moveTo(prevX, prevY);
                        
                        // Connect each point only to its immediate predecessor
                        for (let i = 1; i < visiblePoints.length; i++) {
                            const x = this.getX(visiblePoints[i].t, now);
                            const y = this.getY(visiblePoints[i].v);
                            this.ctx.lineTo(x, y);
                        }
                        
                        this.ctx.stroke();
                    }
                    
                    // Draw dot at the newest (last) point
                    const lastPoint = visiblePoints[visiblePoints.length - 1];
                    const lastX = this.getX(lastPoint.t, now);
                    const lastY = this.getY(lastPoint.v);
                    
                    this.ctx.fillStyle = this.options.color;
                    this.ctx.beginPath();
                    this.ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
                    this.ctx.fill();
                }
            }
        }
        
        // Draw label in top left
        this.ctx.font = '600 11px Inter, sans-serif';
        this.ctx.fillStyle = this.options.textColor;
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'top';
        this.ctx.fillText(this.options.label, this.padding.left + 5, 6);
        
        // Draw current value in top right (avoiding overlap)
        if (this.options.showValue && this.currentValue !== null) {
            this.ctx.font = 'bold 12px "Fira Code", monospace';
            this.ctx.fillStyle = this.options.color;
            this.ctx.textAlign = 'right';
            this.ctx.textBaseline = 'top';
            const valueText = this.formatValue(this.currentValue) + this.options.unit;
            this.ctx.fillText(valueText, this.width - 10, 6);
        }
        
        this.lastRenderTime = now;
    }
    
    /**
     * Start continuous rendering
     * @param {number} fps - Target frames per second
     */
    start(fps = 30) {
        this.stop();
        const interval = 1000 / fps;
        
        const loop = () => {
            this.render();
            this._animationId = setTimeout(() => {
                this._rafId = requestAnimationFrame(loop);
            }, interval);
        };
        
        loop();
    }
    
    /**
     * Stop continuous rendering
     */
    stop() {
        if (this._animationId) {
            clearTimeout(this._animationId);
            this._animationId = null;
        }
        if (this._rafId) {
            cancelAnimationFrame(this._rafId);
            this._rafId = null;
        }
    }
    
    /**
     * Clear all data
     */
    clear() {
        this.data = [];
        this.currentValue = null;
        this.render();
    }
}


/**
 * Telemetry Manager - Handles multiple oscilloscope charts and SSE connection
 */
class TelemetryManager {
    constructor() {
        this.charts = new Map();
        this.eventSource = null;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
    }
    
    /**
     * Register a chart for a telemetry channel
     */
    registerChart(channel, canvas, options) {
        const chart = new OscilloscopeChart(canvas, options);
        this.charts.set(channel, chart);
        return chart;
    }
    
    /**
     * Connect to the telemetry stream
     */
    connect() {
        if (this.eventSource) {
            this.eventSource.close();
        }
        
        this.eventSource = new EventSource('/api/telemetry/stream');
        
        this.eventSource.onopen = () => {
            console.log('Telemetry stream connected');
            this.reconnectDelay = 1000; // Reset delay
        };
        
        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleTelemetry(data);
            } catch (e) {
                console.error('Failed to parse telemetry:', e);
            }
        };
        
        this.eventSource.onerror = (error) => {
            console.error('Telemetry stream error:', error);
            this.eventSource.close();
            
            // Reconnect with exponential backoff
            setTimeout(() => {
                this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
                this.connect();
            }, this.reconnectDelay);
        };
    }
    
    /**
     * Handle incoming telemetry data
     */
    handleTelemetry(data) {
        const timestamp = data.timestamp || Date.now() / 1000;
        
        // Map telemetry channels to charts
        const channelMap = {
            'pmt': 'pmt',
            'laser_freq': 'laser_freq',
            'pressure': 'pressure',
            'pos_x': 'pos_x',
            'pos_y': 'pos_y',
            'sig_x': 'sig_x',
            'sig_y': 'sig_y'
        };
        
        for (const [dataKey, chartKey] of Object.entries(channelMap)) {
            if (data[dataKey] && this.charts.has(chartKey)) {
                const chart = this.charts.get(chartKey);
                const points = data[dataKey];
                
                // Handle array of points or single point
                if (Array.isArray(points)) {
                    for (const point of points) {
                        chart.addPoint(point.t, point.v);
                    }
                } else if (typeof points === 'number') {
                    chart.addPoint(timestamp, points);
                }
            }
        }
        
        // Dispatch custom event for UI updates
        window.dispatchEvent(new CustomEvent('telemetry', { detail: data }));
    }
    
    /**
     * Start all charts rendering
     */
    startAll(fps = 30) {
        for (const chart of this.charts.values()) {
            chart.start(fps);
        }
    }
    
    /**
     * Stop all charts rendering
     */
    stopAll() {
        for (const chart of this.charts.values()) {
            chart.stop();
        }
    }
    
    /**
     * Disconnect from stream
     */
    disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
}


// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { OscilloscopeChart, TelemetryManager };
}
