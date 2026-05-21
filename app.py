import time
import logging
import queue
import os
import threading
import configparser
from datetime import datetime
from collections import deque

from core.engine import RadarSensor

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("RadarCapture")

class TelemetryTracker:
    def __init__(self, interval: float = 10.0):
        self.interval = interval
        self.start = time.time()
        self.last = self.start
        self.cap_times = deque(maxlen=100)
        self.disk_times = deque(maxlen=100)
        self.drops = 0
        self.q_size = 0

    def log_cap(self): self.cap_times.append(time.time())
    def log_disk(self): self.disk_times.append(time.time())
    def log_drop(self): self.drops += 1
    
    def update(self):
        now = time.time()
        if now - self.last >= self.interval:
            c_fps = (len(self.cap_times)-1)/(self.cap_times[-1]-self.cap_times[0]) if len(self.cap_times)>1 else 0
            d_fps = (len(self.disk_times)-1)/(self.disk_times[-1]-self.disk_times[0]) if len(self.disk_times)>1 else 0
            print(f"[{now-self.start:.1f}s] CAP: {c_fps:.1f} | DISK: {d_fps:.1f} | Q: {self.q_size} | Drops: {self.drops}")
            self.last = now

class Writer(threading.Thread):
    def __init__(self, q: queue.Queue, path: str, tel: TelemetryTracker):
        super().__init__(daemon=True)
        self.q, self.path, self.tel, self.running = q, path, tel, True

    def run(self):
        log.info(f"Writing to {self.path}")
        with open(self.path, 'wb') as f:
            while self.running or not self.q.empty():
                try:
                    item = self.q.get(timeout=0.5)
                    if item is None: break
                    f.write(item[1])
                    self.tel.log_disk()
                    self.tel.q_size = self.q.qsize()
                    self.q.task_done()
                except queue.Empty: continue

def load_settings():
    path = "settings.ini"
    config = configparser.ConfigParser()
    if not os.path.exists(path):
        config['Radar'] = {'config_file': 'core/config/config.cfg', 'out_dir': 'data', 
                           'queue_maxsize': '300', 'telemetry_interval': '10.0',
                           'auto_detect_ports': 'true', 'cli_port': 'COM3', 'data_port': 'COM4'}
        with open(path, 'w') as f: config.write(f)
    config.read(path)
    return config['Radar']

def run_capture():
    cfg = load_settings()
    cfg_file = cfg.get('config_file')
    out_dir = cfg.get('out_dir', 'data')
    
    if not os.path.exists(cfg_file):
        print(f"Error: {cfg_file} not found."); return

    os.makedirs(out_dir, exist_ok=True)
    bin_path = os.path.join(out_dir, f"radar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bin")

    cli, data = RadarSensor.find_ti_ports() if cfg.getboolean('auto_detect_ports') else (cfg.get('cli_port'), cfg.get('data_port'))
    if not cli or not data: print("Error: Ports not found."); return
            
    radar = RadarSensor(cli, data, cfg_file)
    try:
        radar.connect_and_configure()
    except Exception as e:
        print(f"Error: {e}"); return
    
    q = queue.Queue(maxsize=cfg.getint('queue_maxsize'))
    tel = TelemetryTracker(interval=cfg.getfloat('telemetry_interval'))
    writer = Writer(q, bin_path, tel)
    writer.start()
    
    print("\nCapture started. Press Ctrl+C to stop.")
    try:
        while True:
            raw = radar.read_raw_frame()
            if raw:
                tel.log_cap()
                try: q.put_nowait((time.perf_counter_ns(), raw))
                except queue.Full: tel.log_drop()
            tel.update()
            if not raw: time.sleep(0.001)
    except KeyboardInterrupt:
        print("\nStopping capture...")
    finally:
        radar.close(); writer.running = False
        try: q.put_nowait(None)
        except: pass
        writer.join(timeout=2.0)
        print("Capture complete.")

def main():
    print("RADAR CAPTURE CLI")
    
    while True:
        print("\n[1] Start Capture  [2] Exit")
        try:
            choice = input("> ").strip()
        except KeyboardInterrupt:
            break

        if choice == '1':
            run_capture()
        elif choice == '2':
            break

if __name__ == "__main__":
    main()
