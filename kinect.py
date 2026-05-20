import time
import logging
import queue
import sys
import os
from datetime import datetime
from rich.console import Console

import pykinect_azure as pykinect
from pykinect_azure.k4a import _k4a
from pykinect_azure.k4a.capture import Capture
from pykinect_azure.k4a._k4atypes import (
    K4A_DEPTH_MODE_NFOV_UNBINNED,
    K4A_COLOR_RESOLUTION_OFF
)

# --- MONKEY PATCH pykinect_azure Capture ---
# Pykinect_azure (0.0.4) has bugs in its capture object management leading to 
# invalid handles and incorrect instance creation. We patch the methods at 
# runtime to ensure portability across different environments without modifying
# the installed library package directly.
def _patched_release_handle(self):
    if self.is_valid():
        _k4a.k4a_capture_release(self._handle)
        self._handle = None

@staticmethod
def _patched_create():
    handle = _k4a.k4a_capture_t()
    _k4a.VERIFY(_k4a.k4a_capture_create(handle), "Create capture failed!")
    return Capture(handle)

Capture.release_handle = _patched_release_handle
Capture.create = _patched_create
# --- END MONKEY PATCH ---

from core.kinect_writer import KinectWriterThread
from core.telemetry import TelemetryTracker
from core.settings import load_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger("RecordKinect")
console = Console()

class HeadlessKinect:
    def __init__(self, fps=30):
        self.device = None
        self.tracker = None
        
        try:
            pykinect.initialize_libraries(track_body=True)
            self.device_config = pykinect.default_configuration
            
            # Headless explicit configuration
            self.device_config.color_resolution = K4A_COLOR_RESOLUTION_OFF # Color not needed
            self.device_config.depth_mode = K4A_DEPTH_MODE_NFOV_UNBINNED
            
            fps_map = {5: pykinect.K4A_FRAMES_PER_SECOND_5, 
                       15: pykinect.K4A_FRAMES_PER_SECOND_15, 
                       30: pykinect.K4A_FRAMES_PER_SECOND_30}
            self.device_config.camera_fps = fps_map.get(min(fps, 30), pykinect.K4A_FRAMES_PER_SECOND_30)
            
            self.device = pykinect.start_device(config=self.device_config)
            
            self.tracker = pykinect.start_body_tracker()
            log.info("Headless Kinect initialized.")
        except Exception as e:
            log.error(f"Kinect initialization failed: {e}")
            self.device = None

    def _safe_pop_result(self, timeout_in_ms=0):
        from pykinect_azure.k4abt import _k4abt
        from pykinect_azure.k4a._k4atypes import K4A_WAIT_RESULT_SUCCEEDED, K4A_WAIT_RESULT_TIMEOUT
        from pykinect_azure.k4abt.frame import Frame

        frame_handle = _k4abt.k4abt_frame_t()
        res = _k4abt.k4abt_tracker_pop_result(self.tracker._handle, frame_handle, timeout_in_ms)
        
        if res == K4A_WAIT_RESULT_SUCCEEDED:
            return Frame(frame_handle, self.tracker.calibration)
        return None

    def get_capture(self):
        if not self.device:
            return None, None, None, None, 0.0

        capture_start = time.time()
        try:
            capture = self.device.update()
            
            ret_depth, depth_image = capture.get_depth_image()
            if not ret_depth:
                return None, None, None, None, 0.0
            
            depth_image_obj = capture.get_depth_image_object()
            dev_ts = _k4a.k4a_image_get_device_timestamp_usec(depth_image_obj.handle())
            
            joints = {}
            if self.tracker:
                self.tracker.enqueue_capture(capture.handle())
                body_frame = self._safe_pop_result(timeout_in_ms=0)
                
                if body_frame is not None and body_frame.is_valid():
                    num_bodies = body_frame.get_num_bodies()
                    if num_bodies > 0:
                        body_3d = body_frame.get_body(0)
                        for i in range(pykinect.K4ABT_JOINT_COUNT):
                            joint_3d = body_3d.joints[i]
                            joints[i] = {
                                'x': joint_3d.position.x, 
                                'y': joint_3d.position.y, 
                                'z': joint_3d.position.z
                            }
                    body_frame.release()

            capture_latency = (time.time() - capture_start) * 1000.0
            return dev_ts, time.perf_counter_ns(), depth_image, joints, capture_latency
            
        except Exception as e:
            log.error(f"Capture error: {e}")
            return None, None, None, None, 0.0

    def close(self):
        if self.tracker:
            try:
                self.tracker.destroy()
            except Exception:
                pass
        if self.device:
            try:
                self.device.close()
            except Exception:
                pass


def main():
    config = load_settings()
    kinect_cfg = config['Kinect']
    
    fps = kinect_cfg.getint('fps', 30)
    out_dir = kinect_cfg.get('out_dir', 'data')
    queue_maxsize = kinect_cfg.getint('queue_maxsize', 300)
    telemetry_interval = kinect_cfg.getfloat('telemetry_interval', 10.0)

    os.makedirs(out_dir, exist_ok=True)
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    h5_path = os.path.join(out_dir, f"kinect_{session_id}.h5")
    parquet_path = os.path.join(out_dir, f"kinect_joints_{session_id}.parquet")
    log_path = os.path.join(out_dir, f"telemetry_kinect_{session_id}.log")

    console.print(f"\n[bold green]Starting Kinect Acquisition...[/bold green]")
    console.print(f"Output Directory: {out_dir}")
    console.print(f"FPS Target: {fps}\n")
    
    kinect = HeadlessKinect(fps=fps)
    if not kinect.device:
        sys.exit(1)
        
    data_queue = queue.Queue(maxsize=queue_maxsize)
    telemetry = TelemetryTracker(log_path, report_interval=telemetry_interval)
    
    writer = KinectWriterThread(data_queue, h5_path, parquet_path, telemetry)
    writer.start()
    
    log.info("Starting capture loop. Press Ctrl+C to stop.")
    try:
        while True:
            dev_ts, perf_ns, depth_img, joints, cap_lat = kinect.get_capture()
            
            if depth_img is not None:
                telemetry.log_capture_frame()
                telemetry.log_tracker_latency(cap_lat)
                
                try:
                    data_queue.put_nowait((dev_ts, perf_ns, depth_img, joints, cap_lat))
                except queue.Full:
                    telemetry.log_dropped_frame()
                    
            telemetry.update()

    except KeyboardInterrupt:
        log.info("Keyboard interrupt received. Stopping capture...")
    finally:
        kinect.close()
        writer.stop()
        try:
            data_queue.put_nowait(None)
        except queue.Full:
            pass
        writer.join(timeout=2.0)
        log.info("Shutdown complete.")

if __name__ == "__main__":
    main()
