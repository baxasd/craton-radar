import threading
import queue
import logging
import json
import time

log = logging.getLogger("RadarWriter")

class RadarWriterThread(threading.Thread):
    def __init__(self, data_queue: queue.Queue, bin_path: str, telemetry):
        super().__init__(daemon=True)
        self.data_queue = data_queue
        self.bin_path = bin_path
        self.telemetry = telemetry
        self.running = True

    def run(self):
        log.info(f"Starting RadarWriterThread. Writing to {self.bin_path}")
        try:
            with open(self.bin_path, 'wb') as f:
                while self.running or not self.data_queue.empty():
                    try:
                        # Wait for data, timeout to allow graceful shutdown
                        item = self.data_queue.get(timeout=0.5)
                        if item is None: # Sentinel for shutdown
                            break
                        
                        perf_counter_ns, raw_binary_frame = item
                        
                        # Assuming raw_binary_frame is already the exact bytes we want to append.
                        # For later offline parsing we might want to also save the timestamp.
                        # Since the packet doesn't have our OS timestamp, we can prepend a small custom header 
                        # or just rely on the constant frame rate. 
                        # For pure raw stream, let's just write the raw frame.
                        f.write(raw_binary_frame)
                        
                        self.telemetry.log_disk_frame()
                        self.telemetry.update_queue_size(self.data_queue.qsize())
                        self.data_queue.task_done()
                        
                    except queue.Empty:
                        continue
        except Exception as e:
            log.error(f"RadarWriterThread error: {e}")
        finally:
            log.info("RadarWriterThread finished.")

    def stop(self):
        self.running = False

def save_radar_config(config_summary: dict, json_path: str):
    with open(json_path, 'w') as f:
        json.dump(config_summary, f, indent=4)
