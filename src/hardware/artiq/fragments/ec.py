from ndscan.experiment import Fragment, ExpFragment, FloatParam, IntParam, BoolParam, FloatChannel, make_fragment_scan_exp
from artiq.experiment import *
from oitg.units import V, us, ms
import numpy as np
import json
import os
import time


class EndCaps(Fragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_device("zotino0")
        

        
        self.first_ec = True
        
    def host_setup(self):
        # load DAC-correction settings
        self.fit_data = self.load_settings()
        
        # Amplification per DAC channel (not accurate yet!)
        self.amps = [21.05, 21.1] # inc1, inc2
        self.voltages = []
        
    @kernel
    def device_setup(self) -> None:
        self.core.break_realtime()
        
        # FIX: Use correct assignment (=) not comparison (==)
        if self.first_ec:
            self.zotino0.init()
            delay(200*us) 
            self.first_ec = False
            
    @rpc
    def find_voltage(self, u_target, inc):
        # amplifier does not invert
        # u = -u_target
        u_out = u_target/inc
        return u_out
    
    @rpc
    def load_settings(self):
        """_summary_

        Raises:
            KeyError: _description_

        Returns:
            _type_: _description_
        """
        # Settings file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, "..", "..", "..", ".."))
        settings = os.path.join(project_root, "artiq", "Settings", "DAC", "2944_dac_diff_fits.json")
        
        with open(settings) as f:
            data = json.load(f)
            
        fit_data = []
        
        # extract fit data from first 6 channels
        for i in range(6):
            try:
                fit = data[f"voltages{i}"]
                fit_data.append(fit)
            except KeyError:
                raise KeyError(f"Fit-Daten für Channel{i} nicht gefunden!")
            
        return fit_data
    
    @rpc
    def correct_voltage(self, u_in, channel):
        """
        Korrigiert die gewünschte DAC-Ausgangsspannung, basierend auf den
        zuvor gefitteten linearen Abweichungen.

        Args:
            u_in (float): _description_
            channel (int): _description_

        Raises:
            ValueError: _description_

        Returns:
            float: _description_
        """

        m1, b1 = self.fit_data[channel]["m"], self.fit_data[channel]["b"]
        
        # inverse calibration
        corrected_u = (u_in - b1) / (1.0 + m1)
        
        #  DAC Range Check
        DAC_LIMIT = 10.0  # |V| < 10
        
        for val, name in [(corrected_u, "u_in")]:
            if abs(val) >= DAC_LIMIT:
                raise ValueError(
                    f"DAC Limit exceeded for channel {channel}!\n"
                    f"Corrected voltage = {val:.4f} V (|V| must be < 10.0)\n"
                    f"Desired value was: u_desired={u_in}, channel={channel}"
                )
                
        return corrected_u
    
    @rpc
    def calculate_ec_values(self, u_target1, u_target2) -> TTuple([TFloat, TFloat]):
        """
        Calculates target values per channel based on INPUT ARGUMENTS.
        Corrects the desired DAC output voltages based on the previously fitted linear deviations.

        Returns:
            tuple(float, float): all calculated values (cor_ec1, cor_ec2)
        """
        
        # Use arguments (u_target1, u_target2) instead of self.u_ec1.get()
        ec1 = self.find_voltage(u_target1, self.amps[0])
        ec2 = self.find_voltage(u_target2, self.amps[1])
        cor_ec1 = self.correct_voltage(ec1, 4)
        cor_ec2 = self.correct_voltage(ec2, 5)

        if hasattr(self, "monitoring") and self.monitoring_ec.get() == True:
            self.set_EC1.push(ec1)
            self.set_EC2.push(ec2)
            self.cor_EC1.push(cor_ec1)
            self.cor_EC2.push(cor_ec2)

        return cor_ec1, cor_ec2
    
    @kernel 
    def set_ec(self, u1_val, u2_val) -> None:
        """
        Sets the Endcaps to specific values passed as arguments.
        Usage: self.endcaps.set_ec(5.0*V, 10.0*V)
        """
        (v1, v2) = self.calculate_ec_values(u1_val, u2_val)
        self.core.break_realtime()
        self.zotino0.set_dac([v1, v2], [4, 5])
        delay(100*ms)

