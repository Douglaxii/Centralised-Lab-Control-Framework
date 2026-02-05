/**
 * API Client for Flask Server
 * Handles all communication with the backend
 */

const API = {
    baseUrl: '',
    
    /**
     * Post JSON data to an endpoint
     */
    async post(endpoint, data) {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    /**
     * Get JSON data from an endpoint
     */
    async get(endpoint) {
        const response = await fetch(endpoint);
        return response.json();
    },
    
    // Control endpoints
    setRF(volts) {
        return this.post('/api/control/rf', { u_rf_volts: volts });
    },
    
    setDDS(freqKHz) {
        return this.post('/api/control/dds', { freq_khz: freqKHz });
    },
    
    setElectrodes(ec1, ec2, compH, compV) {
        return this.post('/api/control/electrodes', { ec1, ec2, comp_h: compH, comp_v: compV });
    },
    
    setPiezoSetpoint(voltage) {
        return this.post('/api/control/piezo/setpoint', { voltage });
    },
    
    setPiezoOutput(enable) {
        return this.post('/api/control/piezo/output', { enable });
    },
    
    toggleDevice(device, state) {
        return this.post(`/api/control/toggle/${device}`, { state });
    },
    
    // Safety endpoints
    toggleSafety(engage) {
        return this.post('/api/safety/toggle', { engage });
    },
    
    getSafetyStatus() {
        return this.get('/api/safety/status');
    },
    
    // Kill switch endpoints
    getKillSwitchStatus() {
        return this.get('/api/killswitch/status');
    },
    
    triggerKillSwitch(device) {
        return this.post('/api/killswitch/trigger', { device });
    },
    
    // Status
    getStatus() {
        return this.get('/api/status');
    }
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = API;
}
