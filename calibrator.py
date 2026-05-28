import struct
import threading
import time
import numpy as np
import scipy.ndimage as ndimage
import dearpygui.dearpygui as dpg

from core.engine import RadarSensor
from core.settings import load_settings

class RadarParser:
    """Thread-safe parser for raw TI Radar TLV streams."""
    def __init__(self, radar_config):
        self.config = radar_config
        self.heatmap = None
        self.heatmap_dims = (0, 0)
        self.lock = threading.Lock()
        
    def parse_frame(self, frame_data: bytes):
        """Extracts Range-Doppler Heatmap (Type 5) from raw frame."""
        if len(frame_data) < 40: 
            return

        # Header: Magic(8), Version(4), TotalLen(4), Platform(4), Frame#(4), Time(4), Obj#(4), TLV#(4), Subframe#(4)
        try:
            header = struct.unpack("<8s8I", frame_data[:40])
            num_tlvs = header[7]
        except (struct.error, IndexError):
            return

        offset = 40
        for _ in range(num_tlvs):
            if offset + 8 > len(frame_data): break
            tlv_type, tlv_length = struct.unpack("<II", frame_data[offset:offset+8])
            offset += 8
            
            if offset + tlv_length > len(frame_data): break
            payload = frame_data[offset:offset+tlv_length]
            offset += tlv_length
            
            # Type 5: Range-Doppler Heatmap (Standard TI Format)
            if tlv_type == 5:
                num_elements = tlv_length // 2
                try:
                    vals = struct.unpack(f"<{num_elements}H", payload[:tlv_length])
                    arr = np.array(vals, dtype=np.float32)
                    
                    rb = self.config.numRangeBins
                    db = num_elements // rb if rb else 32
                    
                    if arr.size == rb * db:
                        with self.lock:
                            self.heatmap = arr
                            self.heatmap_dims = (rb, db)
                except (struct.error, ZeroDivisionError): 
                    pass

def update_gui(parser: RadarParser, calib_cfg):
    """
    Processes radar data and updates the DPG plot.
    Includes guards against malformed data and floating point errors that cause segfaults.
    """
    if not dpg.is_dearpygui_running():
        return
        
    max_display_range_m = calib_cfg.getfloat('max_display_range_m', fallback=5.0)
    zoom_factor = calib_cfg.getint('zoom_factor', fallback=3)
    min_percentile = calib_cfg.getfloat('min_percentile', fallback=5.0)
    max_percentile = calib_cfg.getfloat('max_percentile', fallback=99.5)
    
    # 1. Thread-safe data capture
    with parser.lock:
        if parser.heatmap is None or parser.heatmap_dims[0] == 0:
            return
        raw_data = parser.heatmap.copy()
        rows, cols = parser.heatmap_dims

    try:
        # 2. Physical Clipping (Range Gating)
        range_res = parser.config.rangeRes
        max_bin = min(rows, max(1, int(max_display_range_m / range_res)))
        
        # 3. Reshape and Gate
        # Use ravel/reshape for efficiency, slice to max display range
        matrix = raw_data.reshape((rows, cols))[:max_bin, :]
        
        # 4. Processing Pipeline
        # Doppler shift (center zero), Log scaling (20*log10), and Smoothing
        matrix = np.fft.fftshift(matrix, axes=1)
        matrix = 20.0 * np.log10(np.abs(matrix) + 1e-6)
        
        # 5. Interpolation (Guard against excessive zoom factors)
        if 1 < zoom_factor <= 4:
            matrix = ndimage.zoom(matrix, zoom_factor, order=3)
        
        # 6. Normalization & Safety Checks
        # Segfault Guard: Ensure no NaNs or Infs reach the C-based rendering backend
        if not np.all(np.isfinite(matrix)):
            return
            
        lo = float(np.percentile(matrix, min_percentile))
        hi = float(np.percentile(matrix, max_percentile))
        scale_hi = hi if hi > lo else lo + 0.1
        
        # 7. Orientation Adjustment
        # Flip so Range=0 starts at the bottom of the Y-axis
        matrix = np.flipud(matrix)
        
        # 8. Render to DPG
        flat_list = matrix.ravel().tolist()
        actual_r_max = range_res * max_bin
        max_v = parser.config.dopMax
        
        if dpg.does_alias_exist("heatmap_series"):
            dpg.set_value("heatmap_series", [flat_list])
            dpg.configure_item("heatmap_series", 
                               scale_min=lo, scale_max=scale_hi,
                               bounds_min=(-max_v, 0), bounds_max=(max_v, actual_r_max))
            dpg.set_axis_limits("hm_y_axis", 0, actual_r_max)
        else:
            dpg.add_heat_series(flat_list, matrix.shape[0], matrix.shape[1],
                                parent="hm_y_axis", tag="heatmap_series",
                                scale_min=lo, scale_max=scale_hi,
                                bounds_min=(-max_v, 0), bounds_max=(max_v, actual_r_max),
                                format="")
                
        dpg.set_item_label("heatmap_plot", f"Heatmap | Range: {actual_r_max:.1f}m | Velocity: \u00b1{max_v:.1f}m/s")
            
    except Exception:
        # Silent fail to keep UI thread alive even if a frame is corrupt
        pass

def radar_worker(parser: RadarParser, radar: RadarSensor):
    """Background thread to ingest high-speed serial data."""
    try:
        radar.connect_and_configure()
    except Exception as e:
        print(f"Connection Failed: {e}")
        return
        
    print("Radar Active. Streaming data...")
    thread = threading.current_thread()
    while getattr(thread, "do_run", True):
        frame_found = False
        while True:
            raw = radar.read_raw_frame()
            if not raw:
                break
            frame_found = True
            parser.parse_frame(raw)
            
        if not frame_found:
            time.sleep(0.0001)
    radar.close()

def main():
    # 1. Setup Data Pipeline
    config = load_settings()
    radar_cfg = config['Radar']
    calib_cfg = config['Calibrator']
    ui_refresh_rate = calib_cfg.getfloat('ui_refresh_rate', fallback=0.033)
    max_display_range_m = calib_cfg.getfloat('max_display_range_m', fallback=5.0)
    
    ports = RadarSensor.find_ti_ports() if radar_cfg.getboolean('auto_detect_ports') else (radar_cfg.get('cli_port'), radar_cfg.get('data_port'))
    if not ports[0] or not ports[1]:
        print("Error: Ports not found. Is the radar plugged in?")
        return
        
    radar = RadarSensor(ports[0], ports[1], radar_cfg.get('config_file'))
    parser = RadarParser(radar.config)
    
    # 2. Launch Background Ingestion
    t = threading.Thread(target=radar_worker, args=(parser, radar), daemon=True)
    t.do_run = True
    t.start()
    
    # 3. Setup DearPyGui Context
    dpg.create_context()
    
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, [15, 15, 20])
        
        with dpg.theme_component(dpg.mvPlot):
            dpg.add_theme_color(dpg.mvPlotCol_PlotBg, [5, 5, 8], category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_AxisGrid, [30, 30, 35], category=dpg.mvThemeCat_Plots)

    dpg.bind_theme(global_theme)
    
    with dpg.window(tag="Primary Window"):
        with dpg.colormap_registry(show=False):
            # Professional "Radar-Night" Colormap
            dpg.add_colormap([
                [0, 0, 30], [0, 0, 255], [0, 255, 255], [0, 255, 0], 
                [255, 255, 0], [255, 0, 0], [255, 255, 255]
            ], False, tag="radar_cmap")
        
        with dpg.plot(height=-1, width=-1, tag="heatmap_plot", no_menus=True):
            dpg.add_plot_legend()
            dpg.add_plot_axis(dpg.mvXAxis, label="Velocity (m/s)", tag="hm_x_axis")
            dpg.add_plot_axis(dpg.mvYAxis, label="Range (m)", tag="hm_y_axis")
            dpg.bind_colormap("heatmap_plot", "radar_cmap")
            
            # Initial Axis Projection
            init_r = min(max_display_range_m, radar.config.rangeRes * radar.config.numRangeBins)
            init_v = radar.config.dopMax
            dpg.set_axis_limits("hm_y_axis", 0, init_r)
            dpg.set_axis_limits("hm_x_axis", -init_v, init_v)

    # 4. Initialize Viewport
    dpg.create_viewport(title='Craton Radar Calibrator', width=1100, height=800)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("Primary Window", True)
    
    # 5. Main Loop
    last_update = 0
    while dpg.is_dearpygui_running():
        now = time.time()
        if now - last_update > ui_refresh_rate:
            update_gui(parser, calib_cfg)
            last_update = now
        dpg.render_dearpygui_frame()
        
    # 6. Shutdown
    print("Stopping threads...")
    t.do_run = False
    t.join(timeout=1.0)
    dpg.destroy_context()

if __name__ == "__main__":
    main()
