from ndscan.experiment import Fragment, ExpFragment, FloatParam, IntParam, BoolParam, FloatChannel, make_fragment_scan_exp
from artiq.experiment import *
from oitg.units import V, us, ms
import numpy as np
import json
import os
import time

class Compensation(Fragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_device("zotino0")
        
        self.first = True
        
    def host_setup(self):
        self.fit_data = self.load_settings()
        # Amplification per DAC channel
        self.amps = [9.665, 0.5, 9.665, 0.5] # inc1, red1, inc2, red2
        
    @kernel
    def device_setup(self) -> None:
        self.core.break_realtime()
        if self.first == True:
            self.zotino0.init()
            delay(200*us) 
            self.first = False
    
    @rpc
    def find_voltages(self, u_target, inc, red):
        """
        Splits target voltage into coarse (inc) and fine (red) components.
        """
        u = -u_target # Inverting amplifier logic
        
        # Coarse calculation (0.1V steps)
        coarse = np.floor(abs(u) / inc * 10) / 10.0
        coarse *= np.sign(u)

        # Fine calculation (Remainder)
        fine_needed = u - inc * coarse
        fine = fine_needed / red

        return coarse, fine
    
    @rpc
    def load_settings(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, "..", "..", "..", ".."))
        settings = os.path.join(project_root, "artiq", "Settings", "DAC", "2944_dac_diff_fits.json")
        
        with open(settings) as f:
            data = json.load(f)
            
        fit_data = []
        for i in range(4):
            try:
                fit_data.append(data[f"voltages{i}"])
            except KeyError:
                raise KeyError(f"Fit data for Channel{i} not found!")
        return fit_data
    
    @rpc
    def correct_voltages(self, high, low, channelpair):
        """
        Applies linear calibration correction: v_dac = (v_ideal - b) / (1 + m)
        """
        m1, b1 = self.fit_data[channelpair]["m"], self.fit_data[channelpair]["b"]
        m2, b2 = self.fit_data[channelpair+1]["m"], self.fit_data[channelpair+1]["b"]
        
        corrected_high = (high - b1) / (1.0 + m1)
        corrected_low  = (low  - b2) / (1.0 + m2)
        
        DAC_LIMIT = 10.0
        for val, name in [(corrected_high, "High"), (corrected_low, "Low")]:
            if abs(val) >= DAC_LIMIT:
                raise ValueError(f"DAC Limit exceeded for {name} channel! Value: {val:.4f} V")
        
        return corrected_high, corrected_low
    
    @rpc
    def calculate_values(self, u_h_target, u_v_target) -> TTuple([TFloat, TFloat, TFloat, TFloat]):
        """
        Calculates DAC voltages based on INPUT ARGUMENTS (not dashboard params).
        """
        # 1. Split voltages based on the passed arguments
        coarse1, fine1 = self.find_voltages(u_h_target, self.amps[0], self.amps[1])
        coarse2, fine2 = self.find_voltages(u_v_target, self.amps[2], self.amps[3])
        
        # 2. Apply Calibration
        cor_c1, cor_f1 = self.correct_voltages(coarse1, fine1, 0)
        cor_c2, cor_f2 = self.correct_voltages(coarse2, fine2, 2)

        #3. Log results (Monitoring)
        if hasattr(self, "monitoring") and self.monitoring.get() == True:
            self.set_voltage.push(coarse1)
            self.set_voltage1.push(fine1)
            self.set_voltage2.push(coarse2)
            self.set_voltage3.push(fine2)
            self.cor_voltage.push(cor_c1)
            self.cor_voltage1.push(cor_f1)
            self.cor_voltage2.push(cor_c2)
            self.cor_voltage3.push(cor_f2)
            
        return cor_c1, cor_f1, cor_c2, cor_f2
    
    @kernel 
    def set_compensation(self, u_hor, u_ver) -> None:
        """
        Sets compensation to the specific values passed as arguments.
        Usage: self.comp.set_compensation(10*V, 5*V)
        """
        # Pass the arguments to the calculation RPC
        (v0, v1, v2, v3) = self.calculate_values(u_hor, u_ver)
        
        self.core.break_realtime()
        self.zotino0.set_dac([v0, v1, v2, v3], [0, 1, 2, 3])
        delay(100*ms)

