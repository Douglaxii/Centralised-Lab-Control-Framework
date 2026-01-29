"""
Benchmark script for Image Handler optimizations
Compares performance: Original vs Numba-optimized vs Parallel processing
Optimized for Intel Core i9 + NVIDIA Quadro P400
"""

import os
import sys
import time
import glob
import json
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
import multiprocessing as mp

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ==============================================================================
# CONFIGURATION
# ==============================================================================
INPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_images")
OUTPUT_DIR = os.path.join(INPUT_DIR, "benchmark_output")
NUM_WARMUP = 3  # Warmup iterations for JIT compilation
NUM_RUNS = 10   # Benchmark iterations per image


def create_test_image(path, size=(300, 300), num_ions=3):
    """Create synthetic test image with ion-like spots."""
    img = np.random.normal(50, 5, size).astype(np.float32)
    
    # Add Gaussian spots for ions
    for _ in range(num_ions):
        cx = np.random.randint(50, size[1] - 50)
        cy = np.random.randint(50, size[0] - 50)
        
        y, x = np.ogrid[:size[0], :size[1]]
        spot = 200 * np.exp(-((x-cx)**2 + (y-cy)**2) / (2 * 15**2))
        img += spot
    
    cv2.imwrite(path, img.astype(np.uint8))
    return path


def ensure_test_images():
    """Ensure we have test images for benchmarking."""
    os.makedirs(INPUT_DIR, exist_ok=True)
    
    test_images = []
    for i, (size, ions) in enumerate([(300, 3), (500, 5), (800, 10)]):
        path = os.path.join(INPUT_DIR, f"benchmark_{size[0]}x{size[0]}_{ions}ions.jpg")
        if not os.path.exists(path):
            print(f"Creating test image: {path}")
            create_test_image(path, size=(size[0], size[0]), num_ions=ions)
        test_images.append((path, size[0], ions))
    
    # Also use real images if available
    real_images = glob.glob(os.path.join(INPUT_DIR, "**", "*.jpg"), recursive=True)
    for img_path in real_images:
        if "benchmark" not in img_path and "annotated" not in img_path:
            test_images.append((img_path, "real", "?"))
    
    return test_images[:5]  # Limit to 5 test images


def benchmark_single(handler_class, image_path, num_runs=NUM_RUNS):
    """Benchmark a single handler class on one image."""
    times = []
    
    for i in range(num_runs + NUM_WARMUP):
        start = time.perf_counter()
        try:
            handler = handler_class(
                filename=image_path,
                xstart=0, xfinish=300,
                ystart=0, yfinish=300,
                analysis=2,
                radius=20
            )
            elapsed = (time.perf_counter() - start) * 1000  # ms
            
            if i >= NUM_WARMUP:  # Skip warmup
                times.append(elapsed)
        except Exception as e:
            print(f"  Error: {e}")
            return None
    
    return {
        'mean': np.mean(times),
        'std': np.std(times),
        'min': np.min(times),
        'max': np.max(times),
        'median': np.median(times),
        'times': times
    }


def benchmark_numba_impact():
    """Benchmark the impact of Numba JIT on SHM model."""
    print("\n" + "=" * 80)
    print("NUMBA JIT IMPACT BENCHMARK")
    print("=" * 80)
    
    try:
        from server.cam.image_handler_optimized import shm_1d_numba, shm_1d
        import numba
        
        # Create test data
        y = np.linspace(0, 100, 1000)
        y0, R, A, offset = 50, 20, 100, 10
        
        # Pure Python (simulate without numba)
        def shm_pure_python(y, y0, R, A, offset):
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
        
        # Warmup numba
        _ = shm_1d_numba(y, y0, R, A, offset)
        
        # Benchmark pure Python
        start = time.perf_counter()
        for _ in range(1000):
            _ = shm_pure_python(y, y0, R, A, offset)
        py_time = (time.perf_counter() - start) * 1000
        
        # Benchmark Numba
        start = time.perf_counter()
        for _ in range(1000):
            _ = shm_1d_numba(y, y0, R, A, offset)
        numba_time = (time.perf_counter() - start) * 1000
        
        speedup = py_time / numba_time
        
        print(f"\nSHM Model (1000 iterations, 1000 points):")
        print(f"  Pure Python:  {py_time:.2f} ms")
        print(f"  Numba JIT:    {numba_time:.2f} ms")
        print(f"  Speedup:      {speedup:.1f}x")
        
        return {'pure_python_ms': py_time, 'numba_ms': numba_time, 'speedup': speedup}
        
    except ImportError as e:
        print(f"  [SKIP] Numba not available: {e}")
        return None


def benchmark_handlers():
    """Benchmark original vs optimized image handler."""
    print("\n" + "=" * 80)
    print("IMAGE HANDLER BENCHMARK")
    print("=" * 80)
    
    # Get test images
    test_images = ensure_test_images()
    
    # Import handlers
    try:
        from server.cam.image_handler import Image_Handler as OriginalHandler
        from server.cam.image_handler_optimized import Image_Handler as OptimizedHandler
        has_optimized = True
    except ImportError as e:
        print(f"[ERROR] Could not import handlers: {e}")
        return
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'cpu_cores': mp.cpu_count(),
        'num_runs': NUM_RUNS,
        'images': []
    }
    
    print(f"\nCPU: {mp.cpu_count()} cores")
    print(f"Runs per image: {NUM_RUNS} (plus {NUM_WARMUP} warmup)")
    print(f"\n{'Image':<40} {'Original':>12} {'Optimized':>12} {'Speedup':>10}")
    print("-" * 80)
    
    for img_path, size, ions in test_images:
        img_name = os.path.basename(img_path)[:40]
        
        # Benchmark original
        orig_stats = benchmark_single(OriginalHandler, img_path)
        if orig_stats is None:
            continue
        
        # Benchmark optimized
        opt_stats = benchmark_single(OptimizedHandler, img_path)
        if opt_stats is None:
            continue
        
        speedup = orig_stats['mean'] / opt_stats['mean']
        
        print(f"{img_name:<40} {orig_stats['mean']:>10.1f}ms {opt_stats['mean']:>10.1f}ms {speedup:>9.1f}x")
        
        results['images'].append({
            'path': img_path,
            'size': size,
            'ions': ions,
            'original': orig_stats,
            'optimized': opt_stats,
            'speedup': speedup
        })
    
    # Overall summary
    if results['images']:
        avg_speedup = np.mean([r['speedup'] for r in results['images']])
        print(f"\n{'':<40} {'Average Speedup:':>12} {avg_speedup:>10.1f}x")
        results['average_speedup'] = avg_speedup
    
    return results


def benchmark_parallel_processing():
    """Benchmark parallel processing with multiple workers."""
    print("\n" + "=" * 80)
    print("PARALLEL PROCESSING BENCHMARK")
    print("=" * 80)
    
    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
    import multiprocessing as mp
    
    test_images = ensure_test_images()
    
    def process_one(args):
        """Process single image (for pool)."""
        img_path, _ = args
        try:
            from server.cam.image_handler_optimized import Image_Handler
            start = time.perf_counter()
            handler = Image_Handler(
                filename=img_path,
                xstart=0, xfinish=300,
                ystart=0, yfinish=300,
                analysis=2,
                radius=20
            )
            elapsed = (time.perf_counter() - start) * 1000
            return elapsed
        except Exception as e:
            return None
    
    num_workers_list = [1, 2, 4, min(8, mp.cpu_count())]
    
    print(f"\nProcessing {len(test_images)} images with different worker counts:")
    print(f"{'Workers':>8} {'Total Time':>12} {'Per Image':>12} {'Speedup':>10}")
    print("-" * 50)
    
    baseline_time = None
    
    for num_workers in num_workers_list:
        # Prepare work items (multiple copies for stress test)
        work_items = [(img, i) for i in range(3) for img in test_images]
        
        start = time.perf_counter()
        
        if num_workers == 1:
            # Sequential processing
            results = [process_one(item) for item in work_items]
        else:
            # Parallel processing
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                results = list(executor.map(process_one, work_items))
        
        total_time = (time.perf_counter() - start) * 1000
        valid_results = [r for r in results if r is not None]
        avg_per_image = np.mean(valid_results) if valid_results else 0
        
        if baseline_time is None:
            baseline_time = total_time
            speedup = 1.0
        else:
            speedup = baseline_time / total_time
        
        print(f"{num_workers:>8} {total_time:>10.1f}ms {avg_per_image:>10.1f}ms {speedup:>9.1f}x")


def print_system_info():
    """Print system hardware information."""
    print("=" * 80)
    print("SYSTEM INFORMATION")
    print("=" * 80)
    
    print(f"\nPython: {sys.version}")
    print(f"CPU Cores: {mp.cpu_count()}")
    
    # NumPy/BLAS info
    import numpy as np
    print(f"NumPy: {np.__version__}")
    
    # Numba info
    try:
        import numba
        print(f"Numba: {numba.__version__}")
        print(f"  Threads: {numba.config.NUMBA_NUM_THREADS}
        print(f"  CPU: {numba.config.NUMBA_CPU_NAME}")
        
        # Check if SVML is available (Intel vector math)
        if numba.config.USING_SVML:
            print(f"  Intel SVML: Enabled (fast vector math)")
        else:
            print(f"  Intel SVML: Not available")
    except ImportError:
        print("Numba: Not installed")
    
    # OpenCV info
    try:
        import cv2
        print(f"OpenCV: {cv2.__version__}")
        if hasattr(cv2, 'cuda') and cv2.cuda.getCudaEnabledDeviceCount() > 0:
            print(f"  CUDA: Available")
            cv2.cuda.setDevice(0)
            print(f"  GPU: {cv2.cuda.Device(0).name()}")
        else:
            print(f"  CUDA: Not available")
    except Exception as e:
        print(f"OpenCV: Error checking - {e}")


def main():
    """Run all benchmarks."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print_system_info()
    
    # Run benchmarks
    numba_results = benchmark_numba_impact()
    handler_results = benchmark_handlers()
    
    try:
        benchmark_parallel_processing()
    except Exception as e:
        print(f"\n[WARNING] Parallel benchmark failed: {e}")
        print("  (This is normal on Windows without proper multiprocessing support)")
    
    # Save results
    all_results = {
        'timestamp': datetime.now().isoformat(),
        'system': {
            'cpu_cores': mp.cpu_count(),
            'python': sys.version,
        },
        'numba_impact': numba_results,
        'handler_comparison': handler_results
    }
    
    results_path = os.path.join(OUTPUT_DIR, f"benchmark_{datetime.now():%Y%m%d_%H%M%S}.json")
    with open(results_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\n{'=' * 80}")
    print(f"Results saved to: {results_path}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    # Required for Windows multiprocessing
    mp.set_start_method('spawn', force=True)
    main()
