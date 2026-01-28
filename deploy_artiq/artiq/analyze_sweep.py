"""
ARTIQ Sweep Analysis Module
Processes H5 files from ARTIQ scans and saves results as JSON.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import h5py
import numpy as np
import json
import os
from datetime import datetime
from scipy.optimize import curve_fit
from typing import Optional, Dict, Any, Tuple

from core import get_config, setup_logging, ExperimentContext

# Setup logging
logger = setup_logging(component="analysis")


def lorentzian(x, amp, x0, gamma, offset):
    """
    Lorentzian function for fitting.
    
    Args:
        x: Frequency values
        amp: Amplitude (peak height above offset)
        x0: Center frequency
        gamma: FWHM (Full Width at Half Maximum)
        offset: Background count rate
        
    Returns:
        Lorentzian values
    """
    return offset + amp * (gamma**2 / ((x - x0)**2 + gamma**2))


def analyze_h5_file(filepath: str, exp_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Read H5 file, fit data, and save JSON.
    
    Args:
        filepath: Path to H5 file
        exp_id: Optional experiment ID to associate with results
        
    Returns:
        Fit parameters dict or None if failed
    """
    config = get_config()
    filename = os.path.basename(filepath)
    logger.info(f"Analyzing: {filename} (exp: {exp_id})")

    try:
        with h5py.File(filepath, 'r') as f:
            # Extract Scan Data (ndscan format)
            rid_key = [k for k in f.keys() if "rid_" in k][0]
            dataset_base = f"ndscan.{rid_key}"
            
            # Read axis and channel data
            x_data = np.array(f[f"{dataset_base}.points.axis_0"])
            y_data = np.array(f[f"{dataset_base}.points.channel_points"])
            
            # Initial guess for fit
            p0 = [
                np.max(y_data) - np.min(y_data),
                x_data[np.argmax(y_data)],
                5000.0,  # 5 kHz default
                np.min(y_data)
            ]
            
            # Perform fitting
            fit_success = False
            fit_params = {}
            try:
                popt, pcov = curve_fit(lorentzian, x_data, y_data, p0=p0)
                fit_success = True
                fit_params = {
                    "amplitude": float(popt[0]),
                    "center_freq": float(popt[1]),
                    "fwhm": float(popt[2]),
                    "offset": float(popt[3]),
                    "center_freq_err": float(np.sqrt(pcov[1, 1])) if pcov[1, 1] >= 0 else None
                }
                logger.info(f"Fit successful: center={fit_params['center_freq']:.2f} Hz, "
                          f"FWHM={fit_params['fwhm']:.2f} Hz")
            except Exception as e:
                logger.warning(f"Fit failed: {e}")
                fit_params = {}

            # Construct output data
            timestamp = datetime.now()
            date_str = timestamp.strftime("%y%m%d")
            time_str = timestamp.strftime("%H%M%S")
            
            output_data = {
                "timestamp": timestamp.isoformat(),
                "exp_id": exp_id,
                "source_file": filename,
                "scan_settings": {
                    "span": float(np.max(x_data) - np.min(x_data)),
                    "points": len(x_data),
                    "start_freq": float(np.min(x_data)),
                    "stop_freq": float(np.max(x_data))
                },
                "fit_result": {
                    "success": fit_success,
                    "params": fit_params,
                    "model": "lorentzian"
                },
                "raw_data": {
                    "x_freq": x_data.tolist(),
                    "y_counts": y_data.tolist()
                }
            }

            # Save to JSON
            output_base = config.get_path('output_base')
            save_dir = Path(output_base) / date_str / "sweep_json"
            save_dir.mkdir(parents=True, exist_ok=True)
            
            json_filename = f"{time_str}_sweep"
            if exp_id:
                json_filename += f"_{exp_id}"
            json_filename += ".json"
            
            json_path = save_dir / json_filename
            
            with open(json_path, 'w') as jf:
                json.dump(output_data, jf, indent=4)
            
            logger.info(f"Saved analysis to: {json_path}")
            
            # If experiment context exists, update it
            if exp_id:
                try:
                    exp = ExperimentContext(exp_id=exp_id)
                    exp.add_result("sweep_analysis", {
                        "fit_params": fit_params,
                        "fit_success": fit_success,
                        "json_path": str(json_path)
                    })
                    exp.save()
                except Exception as e:
                    logger.warning(f"Could not update experiment context: {e}")
            
            return fit_params

    except Exception as e:
        logger.error(f"Error processing file {filename}: {e}", exc_info=True)
        return None


def analyze_latest_sweep(directory: Optional[str] = None, exp_id: Optional[str] = None) -> Optional[Dict]:
    """
    Analyze the most recent H5 file in the directory.
    
    Args:
        directory: Directory to search (default from config)
        exp_id: Optional experiment ID
        
    Returns:
        Fit parameters or None
    """
    if directory is None:
        config = get_config()
        directory = config.get_path('artiq_data')
    
    directory = Path(directory)
    if not directory.exists():
        logger.error(f"Directory not found: {directory}")
        return None
    
    # Find H5 files
    h5_files = list(directory.glob("*.h5"))
    if not h5_files:
        logger.warning(f"No H5 files found in {directory}")
        return None
    
    # Get most recent
    latest = max(h5_files, key=lambda p: p.stat().st_mtime)
    logger.info(f"Latest H5 file: {latest}")
    
    return analyze_h5_file(str(latest), exp_id)


def watch_for_new_files(directory: Optional[str] = None, poll_interval: float = 1.0):
    """
    Watch directory for new H5 files and analyze them.
    
    Args:
        directory: Directory to watch
        poll_interval: Polling interval in seconds
    """
    import time
    
    if directory is None:
        config = get_config()
        directory = config.get_path('artiq_data')
    
    directory = Path(directory)
    logger.info(f"Watching {directory} for new H5 files...")
    
    known_files = set(f.name for f in directory.glob("*.h5"))
    
    try:
        while True:
            time.sleep(poll_interval)
            
            current_files = set(f.name for f in directory.glob("*.h5"))
            new_files = current_files - known_files
            
            for filename in new_files:
                filepath = directory / filename
                logger.info(f"New file detected: {filename}")
                # Wait a moment to ensure write is complete
                time.sleep(0.5)
                analyze_h5_file(str(filepath))
            
            known_files = current_files
            
    except KeyboardInterrupt:
        logger.info("Watch stopped")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze ARTIQ sweep data")
    parser.add_argument("file", nargs="?", help="H5 file to analyze")
    parser.add_argument("--latest", action="store_true", help="Analyze latest file")
    parser.add_argument("--watch", action="store_true", help="Watch for new files")
    parser.add_argument("--exp-id", help="Experiment ID to associate")
    parser.add_argument("--dir", help="Directory to search/watch")
    
    args = parser.parse_args()
    
    if args.watch:
        watch_for_new_files(args.dir)
    elif args.latest:
        analyze_latest_sweep(args.dir, args.exp_id)
    elif args.file:
        analyze_h5_file(args.file, args.exp_id)
    else:
        parser.print_help()
