import time
import logging
from collections import deque

log = logging.getLogger("Telemetry")

class TelemetryTracker:
    def __init__(self, log_file: str, report_interval: float = 10.0):
        self.log_file = log_file
        self.report_interval = report_interval
        self.start_time = time.time()
        self.last_report_time = self.start_time
        
        # Moving averages for FPS using simple deques
        self._capture_times = deque(maxlen=100)
        self._disk_times = deque(maxlen=100)
        
        self.dropped_frames = 0
        self.queue_size = 0
        
        # Kinect specific
        self._tracker_latencies = deque(maxlen=100)

        # Setup file logging
        formatter = logging.Formatter('%(asctime)s,%(message)s')
        fh = logging.FileHandler(self.log_file)
        fh.setFormatter(formatter)
        
        self.logger = logging.getLogger(f"TelemetryFile_{log_file}")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(fh)
        
        # Write CSV header
        self.logger.info("Elapsed(s),CaptureFPS,DiskFPS,QueueSize,DroppedFrames,TrackerLatency(ms)")

    def log_capture_frame(self):
        self._capture_times.append(time.time())

    def log_disk_frame(self):
        self._disk_times.append(time.time())

    def log_dropped_frame(self):
        self.dropped_frames += 1

    def update_queue_size(self, size: int):
        self.queue_size = size

    def log_tracker_latency(self, latency_ms: float):
        self._tracker_latencies.append(latency_ms)

    def _calc_fps(self, times_deque) -> float:
        if len(times_deque) < 2:
            return 0.0
        elapsed = times_deque[-1] - times_deque[0]
        if elapsed <= 0:
            return 0.0
        return (len(times_deque) - 1) / elapsed

    def _calc_avg(self, values_deque) -> float:
        if not values_deque:
            return 0.0
        return sum(values_deque) / len(values_deque)

    def update(self):
        now = time.time()
        elapsed_since_report = now - self.last_report_time
        
        if elapsed_since_report >= self.report_interval:
            total_elapsed = now - self.start_time
            cap_fps = self._calc_fps(self._capture_times)
            disk_fps = self._calc_fps(self._disk_times)
            avg_tracker_lat = self._calc_avg(self._tracker_latencies)
            
            # Log to CSV
            csv_line = f"{total_elapsed:.1f},{cap_fps:.1f},{disk_fps:.1f},{self.queue_size},{self.dropped_frames},{avg_tracker_lat:.1f}"
            self.logger.info(csv_line)
            
            # Log to console
            log.info(f"[{total_elapsed:.1f}s] Capture: {cap_fps:.1f} FPS | Disk: {disk_fps:.1f} FPS | Q: {self.queue_size} | Drops: {self.dropped_frames} | Tracker Latency: {avg_tracker_lat:.1f}ms")
            
            self.last_report_time = now
