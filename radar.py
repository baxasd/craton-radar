import time
import logging
import queue
import sys
import os
from datetime import datetime
from rich.console import Console

from core.hardware.radar import RadarSensor
from core.radar_writer import RadarWriterThread, save_radar_config
from core.telemetry import TelemetryTracker
from core.settings import load_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger("RecordRadar")
console = Console()

def main():
    config = load_settings()
    radar_cfg = config['Radar']
    
    config_file = radar_cfg.get('config_file', 'core/config/config.cfg')
    out_dir = radar_cfg.get('out_dir', 'data')
    queue_maxsize = radar_cfg.getint('queue_maxsize', 300)
    telemetry_interval = radar_cfg.getfloat('telemetry_interval', 10.0)
    auto_detect_ports = radar_cfg.getboolean('auto_detect_ports', True)

    if not os.path.exists(config_file):
        console.print(f"[bold red]Error:[/bold red] Configuration file '{config_file}' not found.")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    bin_path = os.path.join(out_dir, f"radar_{session_id}.bin")
    json_path = os.path.join(out_dir, f"radar_{session_id}.json")
    log_path = os.path.join(out_dir, f"telemetry_radar_{session_id}.log")

    console.print(f"\n[bold green]Starting Radar Acquisition...[/bold green]")
    console.print(f"Output Directory: {out_dir}")
    console.print(f"Config File: {config_file}\n")
    
    # 1. Setup hardware
    if auto_detect_ports:
        cli_port, data_port = RadarSensor.find_ti_ports()
        if not cli_port or not data_port:
            log.error("Could not find TI Radar USB ports. Try setting auto_detect_ports=false in settings.ini and provide ports manually.")
            sys.exit(1)
    else:
        cli_port = radar_cfg.get('cli_port')
        data_port = radar_cfg.get('data_port')
        if not cli_port or not data_port:
            log.error("auto_detect_ports is false, but cli_port or data_port are not set in settings.ini.")
            sys.exit(1)
            
    log.info(f"Found Radar on CLI: {cli_port}, DATA: {data_port}")
    
    radar = RadarSensor(cli_port, data_port, config_file)
    try:
        radar.connect_and_configure()
    except Exception as e:
        log.error(f"Failed to configure radar: {e}")
        sys.exit(1)
        
    save_radar_config(radar.config.summary(), json_path)
    
    # 2. Setup Queues and Telemetry
    data_queue = queue.Queue(maxsize=queue_maxsize)
    telemetry = TelemetryTracker(log_path, report_interval=telemetry_interval)
    
    # 3. Start Writer Thread
    writer = RadarWriterThread(data_queue, bin_path, telemetry)
    writer.start()
    
    # 4. Capture Loop
    log.info("Starting capture loop. Press Ctrl+C to stop.")
    try:
        while True:
            raw_frame = radar.read_raw_frame()
            
            if raw_frame:
                perf_ns = time.perf_counter_ns()
                telemetry.log_capture_frame()
                
                try:
                    data_queue.put_nowait((perf_ns, raw_frame))
                except queue.Full:
                    telemetry.log_dropped_frame()
                    
            telemetry.update()
            
            # Prevent 100% CPU lockup if buffer is empty
            if not raw_frame:
                time.sleep(0.001)

    except KeyboardInterrupt:
        log.info("Keyboard interrupt received. Stopping capture...")
    finally:
        radar.close()
        writer.stop()
        # Wake up queue if blocked
        try:
            data_queue.put_nowait(None)
        except queue.Full:
            pass
        writer.join(timeout=2.0)
        log.info("Shutdown complete.")

if __name__ == "__main__":
    main()
