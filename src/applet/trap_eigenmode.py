"""
Trap Eigenmode Calculation Experiment.

Calculates normal modes of trapped ions with asymmetric endcap voltages.
Uses the physics from trap_sim_asy module.

Inputs:
    u_rf: RF voltage amplitude [V]
    ec1: Endcap 1 voltage [V]  
    ec2: Endcap 2 voltage [V]
    masses: List of ion mass numbers (e.g., [9, 3] for Be-9 + He-3)

Outputs:
    - Eigenfrequencies in Hz
    - Mass-weighted eigenvectors
    - Z-equilibrium positions
    - 3D equilibrium coordinates
    - Eigenmode table (CSV)
    - Visualization plot (PNG)

Usage:
    python -m applet.experiments.trap_eigenmode
    # or via applet server API
"""

import sys
import time
import json
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Add analysis path for trap_sim_asy
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "analysis" / "eigenmodes"))

try:
    from trap_sim_asy import calculate_eigenmode, modes_dataframe, _format_df
    from trap_sim_asy import DEFAULT_TRAP_PARAMS
except ImportError as e:
    logging.error(f"Failed to import trap_sim_asy: {e}")
    raise

from .base_experiment import BaseExperiment, ExperimentStatus, ExperimentResult


@dataclass
class EigenmodeResult:
    """Container for eigenmode calculation results."""
    frequencies_hz: np.ndarray
    eigenvectors: np.ndarray
    z_equilibrium: np.ndarray
    coordinates: np.ndarray
    dataframe: pd.DataFrame
    trap_params: Dict[str, Any]
    ion_masses: List[int]
    crystal_angle_deg: Optional[float] = None


class TrapEigenmodeExperiment(BaseExperiment):
    """
    Calculate eigenmodes for trapped ions.
    
    This experiment calculates the normal modes of vibration for ions
    in a Paul trap with asymmetric endcap voltages.
    
    Parameters:
        u_rf: RF voltage [V] (typically 100-500V)
        ec1: Endcap 1 voltage [V] (typically 0-50V)
        ec2: Endcap 2 voltage [V] (typically 0-50V)
        masses: List of mass numbers (e.g., [9, 3] for Be+/HD+)
        
    Optional:
        theta_deg: Rotation angle [degrees]
        z_offset_um: Z offset [micrometers]
        rf_mhz: RF frequency [MHz] (default: 35.8515)
    """
    
    def __init__(
        self,
        manager_host: str = "localhost",
        manager_port: int = 5557,
        data_dir: str = "data/experiments"
    ):
        super().__init__(
            name="trap_eigenmode",
            manager_host=manager_host,
            manager_port=manager_port,
            data_dir=data_dir
        )
        
        # Default parameters
        self.u_rf: float = 200.0
        self.ec1: float = 10.0
        self.ec2: float = 10.0
        self.masses: List[int] = [9, 3]
        self.rf_mhz: float = DEFAULT_TRAP_PARAMS['rf_mhz']
        
        # Results
        self.eigenmode_result: Optional[EigenmodeResult] = None
    
    def parse_masses(self, masses_input) -> List[int]:
        """
        Parse ion masses from various input formats.
        
        Supports:
            - List of integers: [9, 3]
            - Comma-separated string: "9,3"
            - Space-separated string: "9 3"
            - JSON string: "[9, 3]"
        """
        if isinstance(masses_input, list):
            return [int(m) for m in masses_input]
        
        if isinstance(masses_input, str):
            # Try JSON first
            try:
                parsed = json.loads(masses_input)
                if isinstance(parsed, list):
                    return [int(m) for m in parsed]
            except json.JSONDecodeError:
                pass
            
            # Try comma-separated
            if ',' in masses_input:
                return [int(m.strip()) for m in masses_input.split(',')]
            
            # Try space-separated
            return [int(m.strip()) for m in masses_input.split()]
        
        raise ValueError(f"Cannot parse masses: {masses_input}")
    
    def calculate_eigenmodes(self) -> EigenmodeResult:
        """
        Calculate eigenmodes using trap_sim_asy.
        
        Returns:
            EigenmodeResult with all calculation results
        """
        self.logger.info("="*60)
        self.logger.info("TRAP EIGENMODE CALCULATION")
        self.logger.info("="*60)
        self.logger.info(f"RF Voltage: {self.u_rf} V")
        self.logger.info(f"EC1: {self.ec1} V")
        self.logger.info(f"EC2: {self.ec2} V")
        self.logger.info(f"Ion masses: {self.masses} u")
        self.logger.info(f"RF frequency: {self.rf_mhz} MHz")
        
        # Calculate eigenmodes
        freqs_hz, eigenvectors, z_eq, coords = calculate_eigenmode(
            u_rf=self.u_rf,
            ec1=self.ec1,
            ec2=self.ec2,
            masses=self.masses,
            rf_mhz=self.rf_mhz,
            verbose=False
        )
        
        # Create DataFrame
        df = modes_dataframe(freqs_hz, eigenvectors)
        
        # Calculate crystal angle for 2-ion case
        crystal_angle = None
        if len(self.masses) >= 2:
            dx = coords[0][0] - coords[1][0]
            dy = coords[0][1] - coords[1][1]
            dz = coords[0][2] - coords[1][2]
            crystal_angle = np.arctan(np.sqrt(dx**2 + dy**2) / abs(dz)) * 360 / (2*np.pi)
        
        result = EigenmodeResult(
            frequencies_hz=freqs_hz,
            eigenvectors=eigenvectors,
            z_equilibrium=z_eq,
            coordinates=coords,
            dataframe=df,
            trap_params={
                'u_rf': self.u_rf,
                'ec1': self.ec1,
                'ec2': self.ec2,
                'rf_mhz': self.rf_mhz,
                'r_0': DEFAULT_TRAP_PARAMS['r_0'],
                'z_0': DEFAULT_TRAP_PARAMS['z_0'],
                'kappa': DEFAULT_TRAP_PARAMS['kappa'],
                'chi': DEFAULT_TRAP_PARAMS['chi']
            },
            ion_masses=self.masses.copy(),
            crystal_angle_deg=crystal_angle
        )
        
        return result
    
    def save_eigenmode_table(self, result: EigenmodeResult) -> str:
        """
        Save eigenmode table to CSV file.
        
        Returns:
            Path to saved CSV file
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        masses_str = "-".join(map(str, result.ion_masses))
        filename = f"eigenmode_{masses_str}_{int(result.trap_params['u_rf'])}V_{timestamp}.csv"
        filepath = self.data_dir / filename
        
        # Save DataFrame
        result.dataframe.to_csv(filepath, index=False)
        self.logger.info(f"Eigenmode table saved to: {filepath}")
        
        return str(filepath)
    
    def create_visualization(self, result: EigenmodeResult) -> str:
        """
        Create and save eigenmode visualization.
        
        Returns:
            Path to saved PNG file
        """
        df_fmt = _format_df(result.dataframe)
        rows, cols = df_fmt.shape
        
        # Calculate figure size
        fig_w = max(8.0, cols * 1.0)
        fig_h = max(4.0, rows * 0.5 + 2)
        
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        ax.axis("off")
        
        masses_str = " ".join(map(str, result.ion_masses))
        title = (
            f"Normal modes for ions: {masses_str}\n"
            f"U_RF={result.trap_params['u_rf']} V, "
            f"EC1={result.trap_params['ec1']} V, "
            f"EC2={result.trap_params['ec2']} V, "
            f"Ω={result.trap_params['rf_mhz']:.2f} MHz"
        )
        if result.crystal_angle_deg is not None:
            title += f", θ_crystal={result.crystal_angle_deg:.1f}°"
        
        ax.set_title(title, fontsize=10)
        
        # Create table
        tbl = ax.table(
            cellText=df_fmt.values,
            colLabels=df_fmt.columns,
            loc="center",
            cellLoc='center'
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        tbl.scale(1.2, 1.5)
        
        # Color header
        for i in range(len(df_fmt.columns)):
            tbl[(0, i)].set_facecolor('#40466e')
            tbl[(0, i)].set_text_props(weight='bold', color='white')
        
        # Alternate row colors
        for i in range(1, len(df_fmt) + 1):
            for j in range(len(df_fmt.columns)):
                if i % 2 == 0:
                    tbl[(i, j)].set_facecolor('#f0f0f0')
        
        fig.tight_layout()
        
        # Save
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        masses_slug = "-".join(map(str, result.ion_masses))
        filename = f"eigenmode_{masses_slug}_{int(result.trap_params['u_rf'])}V_{timestamp}.png"
        filepath = self.data_dir / filename
        
        plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        self.logger.info(f"Visualization saved to: {filepath}")
        return str(filepath)
    
    def print_results(self, result: EigenmodeResult):
        """Print results to console/log."""
        self.logger.info("\n" + "="*60)
        self.logger.info("RESULTS")
        self.logger.info("="*60)
        
        self.logger.info(f"\nZ-equilibrium positions [µm]: {result.z_equilibrium * 1e6}")
        self.logger.info(f"\nCartesian coordinates [µm]:")
        for i, coord in enumerate(result.coordinates):
            self.logger.info(f"  Ion {i+1}: ({coord[0]*1e6:.3f}, {coord[1]*1e6:.3f}, {coord[2]*1e6:.3f})")
        
        if result.crystal_angle_deg is not None:
            self.logger.info(f"\nCrystal angle with z-axis: {result.crystal_angle_deg:.2f}°")
        
        self.logger.info(f"\nMode frequencies [kHz]:")
        for i, freq in enumerate(result.frequencies_hz):
            self.logger.info(f"  Mode {i}: {freq/1e3:.3f} kHz")
        
        self.logger.info(f"\nEigenmode table:\n{result.dataframe.to_string(index=False)}")
    
    def run(self) -> ExperimentResult:
        """
        Execute trap eigenmode calculation.
        
        Returns:
            ExperimentResult with success status and data
        """
        try:
            self.set_status(ExperimentStatus.RUNNING)
            self.set_progress(10)
            
            # Validate inputs
            if not self.masses or len(self.masses) == 0:
                return ExperimentResult(
                    success=False,
                    error="No ion masses specified"
                )
            
            if self.u_rf <= 0:
                return ExperimentResult(
                    success=False,
                    error=f"Invalid RF voltage: {self.u_rf}"
                )
            
            self.set_progress(30)
            
            # Calculate eigenmodes
            self.logger.info("Calculating eigenmodes...")
            self.eigenmode_result = self.calculate_eigenmodes()
            
            self.set_progress(60)
            
            # Print results
            self.print_results(self.eigenmode_result)
            
            self.set_progress(80)
            
            # Save outputs
            csv_path = self.save_eigenmode_table(self.eigenmode_result)
            png_path = self.create_visualization(self.eigenmode_result)
            
            # Record data
            self.record_data("frequencies_hz", self.eigenmode_result.frequencies_hz.tolist())
            self.record_data("frequencies_khz", (self.eigenmode_result.frequencies_hz / 1e3).tolist())
            self.record_data("z_equilibrium_um", (self.eigenmode_result.z_equilibrium * 1e6).tolist())
            self.record_data("coordinates_um", (self.eigenmode_result.coordinates * 1e6).tolist())
            self.record_data("trap_params", self.eigenmode_result.trap_params)
            self.record_data("ion_masses", self.eigenmode_result.ion_masses)
            self.record_data("crystal_angle_deg", self.eigenmode_result.crystal_angle_deg)
            self.record_data("csv_path", csv_path)
            self.record_data("png_path", png_path)
            
            # Store DataFrame as dict for JSON serialization
            self.record_data("eigenmode_table", self.eigenmode_result.dataframe.to_dict(orient='records'))
            
            self.set_progress(100)
            
            # Summary message
            masses_str = "+".join([f"{m}u" for m in self.masses])
            msg = (
                f"Eigenmode calculation complete for {masses_str} at "
                f"{self.u_rf}V RF. "
                f"Axial mode: {self.eigenmode_result.frequencies_hz[0]/1e3:.1f} kHz"
            )
            
            self.logger.info(msg)
            
            return ExperimentResult(
                success=True,
                data=self.data,
                message=msg
            )
            
        except ValueError as e:
            self.logger.error(f"Invalid parameters: {e}")
            return ExperimentResult(
                success=False,
                error=str(e),
                message="Invalid parameters - check RF voltage and endcap values"
            )
        except Exception as e:
            self.logger.exception("Eigenmode calculation failed")
            return ExperimentResult(
                success=False,
                error=str(e),
                message="Calculation failed"
            )


# Command-line entry point
def main():
    """Run trap eigenmode experiment from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Trap Eigenmode Calculation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -u 200 -e1 10 -e2 10 -m 9 3
  %(prog)s -u 350 --ec1 15 --ec2 15 --masses 9 9 3
  %(prog)s -u 200 -e1 10 -e2 10 -m 9,3 --theta 5.0
        """
    )
    
    parser.add_argument("-u", "--u-rf", type=float, default=200.0,
                        help="RF voltage [V] (default: 200)")
    parser.add_argument("-e1", "--ec1", type=float, default=10.0,
                        help="Endcap 1 voltage [V] (default: 10)")
    parser.add_argument("-e2", "--ec2", type=float, default=10.0,
                        help="Endcap 2 voltage [V] (default: 10)")
    parser.add_argument("-m", "--masses", nargs='+', type=int, default=[9, 3],
                        help="Ion mass numbers in amu (default: 9 3)")

    parser.add_argument("--rf-mhz", type=float, default=DEFAULT_TRAP_PARAMS['rf_mhz'],
                        help=f"RF frequency [MHz] (default: {DEFAULT_TRAP_PARAMS['rf_mhz']})")
    parser.add_argument("--data-dir", default="data/experiments",
                        help="Output directory (default: data/experiments)")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and configure experiment
    exp = TrapEigenmodeExperiment(data_dir=args.data_dir)
    exp.u_rf = args.u_rf
    exp.ec1 = args.ec1
    exp.ec2 = args.ec2
    exp.masses = args.masses
    exp.rf_mhz = args.rf_mhz
    
    print("="*60)
    print("TRAP EIGENMODE CALCULATION")
    print("="*60)
    print(f"RF Voltage: {args.u_rf} V")
    print(f"EC1: {args.ec1} V")
    print(f"EC2: {args.ec2} V")
    print(f"Ion masses: {args.masses} u")
    print("="*60)
    
    # Run experiment
    result = exp.run()
    
    print("\n" + "="*60)
    if result.success:
        print("RESULT: SUCCESS")
        print(f"Message: {result.message}")
        print(f"\nOutput files:")
        print(f"  CSV: {result.data.get('csv_path', 'N/A')}")
        print(f"  PNG: {result.data.get('png_path', 'N/A')}")
    else:
        print("RESULT: FAILED")
        print(f"Error: {result.error}")
    print("="*60)
    
    return 0 if result.success else 1


if __name__ == "__main__":
    exit(main())
