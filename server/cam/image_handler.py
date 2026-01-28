# -*- coding: utf-8 -*-

import numpy as np
import os
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
# from dcimgnp import * # Optional: Keep if you use DCIMG files, otherwise comment out
import cv2
import time
from datetime import datetime
from numba import jit

# --- 1. GAUSSIAN MODEL FOR HORIZONTAL PROFILE ---
def gaussian_1d(x, x0, sigma, A, offset):
    """
    1D Gaussian model for horizontal intensity profile.
    """
    return offset + A * np.exp(-((x - x0) ** 2) / (2 * sigma ** 2))


# --- 2. SHM MODEL FOR VERTICAL PROFILE ---
def shm_1d(y, y0, R, A, offset):
    """
    1D SHM (Simple Harmonic Motion) probability model for vertical intensity profile.
    This represents the probability distribution of a particle in a harmonic potential.
    """
    epsilon = 1e-10
    result = np.zeros_like(y, dtype=float)
    for i, y_val in enumerate(y):
        y_diff = y_val - y0
        if y_diff ** 2 < R ** 2:
            denom = np.sqrt(R ** 2 - y_diff ** 2)
            if denom < epsilon:
                denom = epsilon
            result[i] = A / denom + offset
        else:
            result[i] = offset
    return result


# --- 3. MAIN CLASS ---
class Image_Handler:
    initial_guess = (100, 100, 3, 6, 10, 2)  # x0, y0, sigma_x, R_y, A, offset
    debug_save_path = "Y:/Stein/Server/Debug"
    
    def __init__(self, filename, xstart, xfinish, ystart, yfinish, analysis, radius=20, debug=False):
        self.filename = filename
        self.xstart = xstart
        self.xfinish = xfinish
        self.ystart = ystart
        self.yfinish = yfinish
        self.analysis = analysis
        self.radius = radius
        self.debug = debug
        
        # Prepare Data
        self.img_array = self.prepare_img_array()
        
        # Ensure ROI is within bounds
        if self.img_array is not None:
            self.operation_array = self.img_array[xstart:xfinish, ystart:yfinish]
            self.h, self.w = self.operation_array.shape
            self.x_grid, self.y_grid = np.meshgrid(np.arange(self.w), np.arange(self.h))
        else:
            self.operation_array = None
            self.atom_count = 0
            return

        # Metadata
        now = datetime.now()
        self.right_now = now.strftime("%Y-%m-%d_%H-%M-%S")
        self.Date = self.right_now.split("_")[0]
        
        self.Popt = []
        self.Perr = []
        self.atom_count = 0
        self.Centers = [[], []]  # Centers in original image coordinates
        self.Settings_list = []
        self.annotated_frame = None  # Will store the annotated image

        # --- ANALYSIS PIPELINE ---
        if self.analysis >= 1:
            self.img_rgb, self.thresh, self.contours, self.Centers_roi = self.cv_count_fast()
            # Convert Centers from ROI to original image coordinates
            self.Centers = [
                [c + ystart for c in self.Centers_roi[0]],  # x positions (column index)
                [c + xstart for c in self.Centers_roi[1]]   # y positions (row index)
            ]
            
            if self.analysis >= 2:
                self.Popt, self.Perr = self.fit_profiles()
                
            # Create annotated frame if ions detected
            if self.atom_count > 0:
                self.annotated_frame = self.create_annotated_frame()

        self.create_Settings()
        
    def prepare_img_array(self):
        """
        FIXED: Now detects file extension to handle JPG/PNG vs legacy DAT files.
        """
        if not os.path.exists(self.filename):
            print(f"Error: File not found {self.filename}")
            return None

        ext = os.path.splitext(self.filename)[1].lower()

        # 1. Handle Standard Images (JPG, PNG, TIF, BMP)
        if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff']:
            img = cv2.imread(self.filename, cv2.IMREAD_GRAYSCALE)
            if img is None:
                print(f"Error loading image: {self.filename}")
                return None
            return np.uint8(img)

        # 2. Handle Legacy DAT files (Text based)
        elif ext == '.dat':
            try:
                img_line_list = []
                with open(self.filename, "r") as img_data:
                    for line in img_data:
                        temp = [int(x) for x in line.split()]
                        img_line_list.append(temp)
                return np.uint8(np.array(img_line_list))
            except Exception as e:
                print(f"Error reading DAT file: {e}")
                return None
        
        # 3. Handle HEX files
        elif ext == '.hex':
             try:
                with open(self.filename, 'rb') as f:
                    hexdata = f.read()
                hexlist_int = [int.from_bytes(hexdata[i:i+2], byteorder='little') for i in range(0, len(hexdata), 2)]
                # Assuming 200x200 for HEX as per original code, adjust if needed
                img_array_hex = np.array(hexlist_int).reshape((200, 200)) 
                return np.uint8(img_array_hex)
             except Exception as e:
                print(f"Error reading HEX file: {e}")
                return None

        else:
            print(f"Unsupported file format: {ext}")
            return None

    def fast_filter(self, img, sigma=3):
        return cv2.GaussianBlur(img, (0, 0), sigmaX=sigma, sigmaY=sigma)

    def fit_profiles(self, base_window=30, min_window=20):
        """
        Fits horizontal (Gaussian) and vertical (SHM) intensity profiles for each detected ion.
        Uses adaptive window sizing based on estimated profile width for better accuracy.
        
        Parameters:
            base_window: Base half-window size for profile extraction
            min_window: Minimum window size to ensure sufficient data
        """
        popt_list = []
        perr_list = []
        
        if self.atom_count == 0:
            return [], []

        for i in range(self.atom_count):
            # Centers are in original image coordinates
            cx_orig = self.Centers[0][i]  # x position in original image
            cy_orig = self.Centers[1][i]  # y position in original image
            
            # Convert to ROI coordinates for extracting the profile
            cx_roi = cx_orig - self.ystart
            cy_roi = cy_orig - self.xstart
            
            # Initial window for parameter estimation
            x_min_init = max(0, int(cx_roi - base_window))
            x_max_init = min(self.w, int(cx_roi + base_window))
            y_min_init = max(0, int(cy_roi - base_window))
            y_max_init = min(self.h, int(cy_roi + base_window))
            
            roi_data_init = self.operation_array[y_min_init:y_max_init, x_min_init:x_max_init]
            
            if roi_data_init.size < 25:
                popt_list.append(np.zeros(8))
                perr_list.append(np.zeros(8))
                continue

            # --- HORIZONTAL PROFILE (Gaussian fit) ---
            x_indices_init = np.arange(x_min_init, x_max_init)
            horizontal_profile_init = np.sum(roi_data_init, axis=0)
            
            local_min_h = np.min(horizontal_profile_init)
            local_max_h = np.max(horizontal_profile_init)
            local_amp_h = local_max_h - local_min_h
            x_center_est = x_indices_init[np.argmax(horizontal_profile_init)]
            
            # More accurate sigma estimation using second moment
            if local_amp_h > 0:
                normalized = (horizontal_profile_init - local_min_h) / local_amp_h
                valid_mask = normalized > 0.1  # Use points above 10% of peak
                if np.sum(valid_mask) > 3:
                    x_valid = x_indices_init[valid_mask]
                    w_valid = normalized[valid_mask]
                    sigma_x_est = np.sqrt(np.sum(w_valid * (x_valid - x_center_est) ** 2) / np.sum(w_valid))
                    sigma_x_est = max(sigma_x_est, 0.5)
                else:
                    sigma_x_est = 2.0
            else:
                sigma_x_est = 2.0
            
            # Adaptive window: use 4 sigma on each side for good coverage (99.99% of Gaussian)
            fit_window_x = max(min_window, int(4 * sigma_x_est + 2))
            x_min = max(0, int(cx_roi - fit_window_x))
            x_max = min(self.w, int(cx_roi + fit_window_x))
            
            # Re-extract data with adaptive window
            y_min = max(0, int(cy_roi - base_window))
            y_max = min(self.h, int(cy_roi + base_window))
            roi_data = self.operation_array[y_min:y_max, x_min:x_max]
            x_indices = np.arange(x_min, x_max)
            horizontal_profile = np.sum(self.operation_array[y_min:y_max, x_min:x_max], axis=0)
            
            # Recalculate with actual window
            local_min_h = np.min(horizontal_profile)
            local_max_h = np.max(horizontal_profile)
            local_amp_h = local_max_h - local_min_h
            
            # Bounds: sigma upper bound is now based on actual window size
            # Allow sigma up to half the window (covers 99.99% of Gaussian at 4 sigma)
            sigma_upper_bound = fit_window_x / 2.0
            
            try:
                popt_h, pcov_h = curve_fit(
                    gaussian_1d, x_indices, horizontal_profile,
                    p0=[x_center_est, sigma_x_est, local_amp_h, local_min_h],
                    bounds=([x_min, 0.2, 0, 0], [x_max, sigma_upper_bound, local_max_h * 10, local_max_h]),
                    maxfev=2000,
                    method='lm' if len(x_indices) > 4 else 'trf'  # Use Levenberg-Marquardt for more data points
                )
                perr_h = np.sqrt(np.diag(pcov_h))
            except Exception:
                popt_h = np.array([cx_roi, sigma_x_est, local_amp_h, local_min_h])
                perr_h = np.zeros(4)
            
            # --- VERTICAL PROFILE (SHM fit) ---
            # Adaptive window for vertical based on estimated R
            y_indices_init = np.arange(y_min_init, y_max_init)
            vertical_profile_init = np.sum(roi_data_init, axis=1)
            
            local_min_v = np.min(vertical_profile_init)
            local_max_v = np.max(vertical_profile_init)
            local_amp_v = local_max_v - local_min_v
            y_center_est = y_indices_init[np.argmax(vertical_profile_init)]
            
            # More accurate R estimation using second moment
            # For SHM distribution: <y^2> = R^2 / 2, so R = sqrt(2 * <y^2>)
            if local_amp_v > 0:
                normalized_v = (vertical_profile_init - local_min_v) / local_amp_v
                valid_mask_v = normalized_v > 0.1
                if np.sum(valid_mask_v) > 3:
                    y_valid = y_indices_init[valid_mask_v]
                    w_valid = normalized_v[valid_mask_v]
                    y_variance = np.sum(w_valid * (y_valid - y_center_est) ** 2) / np.sum(w_valid)
                    R_est = np.sqrt(2 * y_variance)
                    R_est = max(R_est, 0.5)
                else:
                    R_est = 4.0
            else:
                R_est = 4.0
            
            # Adaptive window: use 2R + margin for SHM profile
            fit_window_y = max(min_window, int(2.5 * R_est + 3))
            y_min = max(0, int(cy_roi - fit_window_y))
            y_max = min(self.h, int(cy_roi + fit_window_y))
            
            y_indices = np.arange(y_min, y_max)
            vertical_profile = np.sum(self.operation_array[y_min:y_max, x_min_init:x_max_init], axis=1)
            
            local_min_v = np.min(vertical_profile)
            local_max_v = np.max(vertical_profile)
            local_amp_v = local_max_v - local_min_v
            
            # Bounds: R upper bound based on window (should be less than half window)
            R_upper_bound = fit_window_y / 2.0
            
            try:
                popt_v, pcov_v = curve_fit(
                    shm_1d, y_indices, vertical_profile,
                    p0=[y_center_est, R_est, local_amp_v, local_min_v],
                    bounds=([y_min, 0.2, 0, 0], [y_max, R_upper_bound, local_max_v * 10, local_max_v]),
                    maxfev=2000,
                    method='lm' if len(y_indices) > 4 else 'trf'
                )
                perr_v = np.sqrt(np.diag(pcov_v))
            except Exception:
                popt_v = np.array([cy_roi, R_est, local_amp_v, local_min_v])
                perr_v = np.zeros(4)
            
            # Combine results: [x0, y0, sigma_x, R_y, A_x, A_y, offset_x, offset_y]
            # x0, y0 are in original image coordinates
            x0_orig = popt_h[0] + self.ystart
            y0_orig = popt_v[0] + self.xstart
            
            # Store combined parameters
            popt_combined = np.array([
                x0_orig,           # x position in original image
                y0_orig,           # y position in original image
                popt_h[1],         # sigma_x (Gaussian width)
                popt_v[1],         # R_y (SHM turning point)
                popt_h[2],         # Amplitude from horizontal fit
                popt_v[2],         # Amplitude from vertical fit
                popt_h[3],         # Offset from horizontal fit
                popt_v[3]          # Offset from vertical fit
            ])
            
            perr_combined = np.array([
                perr_h[0],         # x0 error
                perr_v[0],         # y0 error
                perr_h[1],         # sigma_x error
                perr_v[1],         # R_y error
                perr_h[2],         # A_x error
                perr_v[2],         # A_y error
                perr_h[3],         # offset_x error
                perr_v[3]          # offset_y error
            ])
            
            popt_list.append(popt_combined)
            perr_list.append(perr_combined)

        return popt_list, perr_list

    def create_annotated_frame(self):
        """
        Creates an annotated image with circles around detected ions and fit parameters displayed.
        Parameters are displayed in columns at the bottom - one column per ion (left to right).
        """
        # Create RGB image from operation_array
        if self.img_rgb is not None:
            annotated = self.img_rgb.copy()
        else:
            annotated = cv2.cvtColor(self.operation_array, cv2.COLOR_GRAY2RGB)
        
        colors = [
            # --- Primary & Secondary (High Brightness) ---
            (0, 255, 0),       # Green
            (255, 0, 0),       # Blue
            (0, 0, 255),       # Red
            (255, 255, 0),     # Cyan
            (255, 0, 255),     # Magenta
            (0, 255, 255),     # Yellow
            (0, 165, 255),     # Orange
            (128, 0, 128),     # Purple
            (203, 192, 255),   # Pink
            (0, 255, 127),     # Lime / Spring Green
            
            # --- Darker / Earth Tones (Good contrast on light backgrounds) ---
            (128, 128, 0),     # Teal
            (0, 128, 0),       # Dark Green
            (128, 0, 0),       # Navy
            (0, 0, 128),       # Maroon
            (42, 42, 165),     # Brown
            (0, 128, 128),     # Olive
            
            # --- Pastels & Others ---
            (250, 206, 135),   # Light Sky Blue
            (211, 0, 148),     # Dark Violet
            (180, 105, 255),   # Hot Pink
            (0, 215, 255),     # Gold
            (128, 128, 128),   # Grey
            (230, 216, 173),   # Light Blue/Grey
            (130, 0, 75),      # Indigo
            (50, 205, 50),     # Lime Green (Darker)
            (255, 191, 0)      # Deep Sky Blue
        ]
        
        # First pass: draw circles and crosshairs around all ions
        for i, (popt, perr) in enumerate(zip(self.Popt, self.Perr)):
            if np.all(popt == 0):
                continue
            
            color = colors[i % len(colors)]
            x0, y0, sigma_x, R_y, A_x, A_y, offset_x, offset_y = popt
            
            # Convert original image coordinates to ROI coordinates for drawing
            x0_roi = int(x0 - self.ystart)
            y0_roi = int(y0 - self.xstart)
            
            # Draw circle around ion (use average of sigma_x and R_y as radius)
            radius = int((sigma_x + R_y) / 2 * 2)  # 2 sigma radius
            center = (x0_roi, y0_roi)
            cv2.circle(annotated, center, radius, color, 1)
            

        
        # Second pass: draw fit parameters in columns at the bottom
        font_scale = 0.35
        line_height = 14
        margin = 5
        
        # Build parameter entries for each ion (column)
        # Each column will have: Ion label, position, sigma_x, R_y, A_x, A_y
        ion_columns = []  # List of (list of text lines, color)
        for i, (popt, perr) in enumerate(zip(self.Popt, self.Perr)):
            if np.all(popt == 0):
                continue
            
            color = colors[i % len(colors)]
            x0, y0, sigma_x, R_y, A_x, A_y, offset_x, offset_y = popt
            
            # Build text lines for this ion's column
            lines = [
                f"Ion {i+1}",
                f"pos: ({x0:.1f}, {y0:.1f})",
                f"sig_x: {sigma_x:.2f}",
                f"R_y: {R_y:.2f}",
                f"A_x: {A_x:.1f}",
                f"A_y: {A_y:.1f}",
            ]
            ion_columns.append((lines, color))
        
        if ion_columns:
            # Calculate layout
            num_columns = len(ion_columns)
            lines_per_column = len(ion_columns[0][0])
            total_text_height = lines_per_column * line_height + margin * 2
            column_width = self.w // num_columns if num_columns > 0 else self.w
            
            # Draw semi-transparent background for better readability
            overlay = annotated.copy()
            cv2.rectangle(overlay, (0, self.h - total_text_height), (self.w, self.h), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.5, annotated, 0.5, 0, annotated)
            
            # Draw text in columns (left to right)
            for col_idx, (lines, color) in enumerate(ion_columns):
                # Calculate x position for this column (centered within its column width)
                col_x = margin + col_idx * column_width
                
                for line_idx, text in enumerate(lines):
                    y_pos = self.h - total_text_height + margin + (line_idx + 1) * line_height - 3
                    
                    # Draw text shadow
                    cv2.putText(annotated, text, (col_x + 1, y_pos + 1),
                                cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 1)
                    # Draw text
                    cv2.putText(annotated, text, (col_x, y_pos),
                                cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 1)
        
        return annotated

    def cv_count_fast(self, m_low=1.01, m_mid=1.05, m_high=2.0, band=3.5):
        """
        Original working ion detection with minor improvements for robustness.
        Returns centers in ROI coordinates.
        """
        self.no_atom = False
        img_rgb = cv2.cvtColor(self.operation_array.copy(), cv2.COLOR_GRAY2RGB)

        sigma = max(1, self.radius / 4.0)
        lowpass_img = self.fast_filter(self.operation_array, sigma=sigma)
        
        self.l_max = np.max(lowpass_img)
        self.l_avg = np.mean(lowpass_img)
        
        middle_thresh = int(0.5 * ((self.l_max) + (self.l_avg)))
        high_thresh = int(self.l_max - 0.25 * (self.l_max - self.l_avg))
        low_thresh = int(self.l_avg + 0.25 * (self.l_max - self.l_avg))
        
        gain = self.l_max / (self.l_avg + 1e-6)

        if gain > m_high:
            thresh_val = low_thresh
        elif m_mid < gain <= m_high:
            thresh_val = middle_thresh
        elif m_low < gain <= m_mid and (self.l_max - self.l_avg) > band:
            thresh_val = high_thresh
        elif gain <= m_low and (self.l_max - self.l_avg) > band:
            thresh_val = int(self.l_max - 1)
        else:
            self.no_atom = True
            return img_rgb, np.zeros_like(lowpass_img), [], [[], []]

        ret, thresh = cv2.threshold(lowpass_img, thresh_val, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
        
        Centers = [[], []]
        self.atom_count = 0
        
        for c in contours:
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            
            cX = int(M["m10"] / M["m00"])
            cY = int(M["m01"] / M["m00"])
            
            too_close = False
            for k in range(len(Centers[0])):
                dist = np.sqrt((cX - Centers[0][k]) ** 2 + (cY - Centers[1][k]) ** 2)
                if dist < 10:
                    too_close = True
                    break
            
            if not too_close:
                Centers[0].append(cX)
                Centers[1].append(cY)
                self.atom_count += 1

        return img_rgb, thresh, contours, Centers

    def create_Settings(self):
        for attr, value in self.__dict__.items():
            if attr not in ["Settings_list", "img_array", "operation_array", "img_rgb", "x_grid", "y_grid", "annotated_frame"]:
                self.Settings_list.append(f"{attr}={value}\n")
