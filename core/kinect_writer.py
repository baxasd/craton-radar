import threading
import queue
import logging
import h5py
import pandas as pd
import time
import os

log = logging.getLogger("KinectWriter")

class KinectWriterThread(threading.Thread):
    def __init__(self, data_queue: queue.Queue, h5_path: str, parquet_path: str, telemetry):
        super().__init__(daemon=True)
        self.data_queue = data_queue
        self.h5_path = h5_path
        self.parquet_path = parquet_path
        self.telemetry = telemetry
        self.running = True
        
        self.metadata_records = []
        
    def run(self):
        log.info(f"Starting KinectWriterThread. H5: {self.h5_path}, Parquet: {self.parquet_path}")
        
        try:
            with h5py.File(self.h5_path, 'w') as h5f:
                # We'll create datasets dynamically when the first frame arrives so we know the shape.
                depth_ds = None
                
                frame_idx = 0
                
                while self.running or not self.data_queue.empty():
                    try:
                        item = self.data_queue.get(timeout=0.5)
                        if item is None:
                            break
                        
                        dev_ts_usec, perf_ns, depth_img, joints, cap_lat = item
                        
                        # Write Depth to HDF5
                        if depth_img is not None:
                            if depth_ds is None:
                                # Create expandable dataset for depth
                                depth_ds = h5f.create_dataset(
                                    'depth', 
                                    shape=(0, depth_img.shape[0], depth_img.shape[1]), 
                                    maxshape=(None, depth_img.shape[0], depth_img.shape[1]),
                                    dtype=depth_img.dtype,
                                    chunks=(1, depth_img.shape[0], depth_img.shape[1]),
                                    compression='lzf' # Fast compression suitable for realtime
                                )
                            
                            depth_ds.resize(frame_idx + 1, axis=0)
                            depth_ds[frame_idx] = depth_img

                        # Prepare joints/metadata record
                        record = {
                            'frame_idx': frame_idx,
                            'device_timestamp_usec': dev_ts_usec,
                            'perf_counter_ns': perf_ns,
                            'capture_latency_ms': cap_lat
                        }
                        
                        if joints:
                            for joint_id, coords in joints.items():
                                record[f'joint_{joint_id}_x'] = coords['x']
                                record[f'joint_{joint_id}_y'] = coords['y']
                                record[f'joint_{joint_id}_z'] = coords['z']
                                
                        self.metadata_records.append(record)
                        
                        frame_idx += 1
                        
                        self.telemetry.log_disk_frame()
                        self.telemetry.update_queue_size(self.data_queue.qsize())
                        self.data_queue.task_done()
                        
                        # Periodically flush metadata to disk to prevent massive memory usage
                        if len(self.metadata_records) >= 1000:
                            self._flush_metadata()

                    except queue.Empty:
                        continue
                        
                # Flush remaining metadata
                if self.metadata_records:
                    self._flush_metadata()

        except Exception as e:
            log.error(f"KinectWriterThread error: {e}")
        finally:
            log.info("KinectWriterThread finished.")

    def _flush_metadata(self):
        try:
            df = pd.DataFrame(self.metadata_records)
            # Append to parquet file if it exists, otherwise write new
            if os.path.exists(self.parquet_path):
                existing_df = pd.read_parquet(self.parquet_path)
                df = pd.concat([existing_df, df], ignore_index=True)
            
            df.to_parquet(self.parquet_path, engine='pyarrow', index=False)
            self.metadata_records = []
        except Exception as e:
            log.error(f"Failed to flush Parquet metadata: {e}")

    def stop(self):
        self.running = False
