import sys
import struct
import threading
import time
import numpy as np
import scipy.ndimage as ndimage
import dearpygui.dearpygui as dpg

from core.engine import RadarSensor
from app import load_settings

class RadarParser:
    def __init__(self, radar_config):
        self.config = radar_config
        self.heatmap = None
        self.heatmap_dims = (0, 0)
        self.lock = threading.Lock()
        
    def parse_frame(self, frame_data):
        if len(frame_data) < 40: return

        header_format = "<8s8I"
        try:
            header = struct.unpack(header_format, frame_data[:40])
        except struct.error:
            return

        magic, version, total_len, platform, frame_no, time_cpu, num_det_obj, num_tlvs, subframe_no = header

        offset = 40
        
        for _ in range(num_tlvs):
            if offset + 8 > len(frame_data): break
            tlv_type, tlv_length = struct.unpack("<II", frame_data[offset:offset+8])
            offset += 8
            
            if offset + tlv_length > len(frame_data): break
            payload = frame_data[offset:offset+tlv_length]
            offset += tlv_length
            
            # Type 5: Range-Doppler Heatmap
            if tlv_type == 5:
                num_elements = tlv_length // 2
                try:
                    vals = struct.unpack(f"<{num_elements}H", payload[:tlv_length])
                    arr = np.array(vals, dtype=np.float32)
                    
                    # Log-scale to make it look like a radar display
                    arr = np.log10(arr + 1)
                    
                    range_bins = self.config.numRangeBins
                    doppler_bins = num_elements // range_bins if range_bins else 32
                    
                    if arr.size == range_bins * doppler_bins:
                        with self.lock:
                            self.heatmap = arr
                            self.heatmap_dims = (range_bins, doppler_bins)
                except struct.error: pass

def update_gui(parser):
    if not dpg.is_dearpygui_running(): return
    
    with parser.lock:
        if parser.heatmap is None:
            return
        hm_copy = parser.heatmap.copy()
        rb, db = parser.heatmap_dims

    if rb > 0 and db > 0 and hm_copy.size == rb * db:
        try:
            # Reshape to 2D for zoom
            hm_2d = hm_copy.reshape((rb, db))
            # Zoom by a factor of 4 for better visual resolution
            hm_zoomed = ndimage.zoom(hm_2d, 4, order=1)
            new_rb, new_db = hm_zoomed.shape
            
            flat_data = hm_zoomed.flatten().tolist()
            
            if not dpg.does_alias_exist("heatmap_series"):
                dpg.set_axis_limits("hm_x_axis", 0, new_db)
                dpg.set_axis_limits("hm_y_axis", 0, new_rb)
                dpg.add_heat_series(
                    flat_data, new_rb, new_db, 
                    label="Range-Doppler", 
                    parent="hm_y_axis", 
                    tag="heatmap_series",
                    scale_min=0, scale_max=5,
                    format="",
                    bounds_min=(0, 0), bounds_max=(new_db, new_rb)
                )
            else:
                dpg.set_value("heatmap_series", [flat_data])
        except Exception as e:
            pass

def radar_thread(parser, radar):
    try:
        radar.connect_and_configure()
    except Exception as e:
        print(f"Failed to connect: {e}")
        return
        
    print("Radar started. Feeding data to UI...")
    while getattr(threading.current_thread(), "do_run", True):
        raw = radar.read_raw_frame()
        if raw:
            parser.parse_frame(raw)
        else:
            time.sleep(0.005)
    radar.close()

def main():
    cfg = load_settings()
    cli, data = RadarSensor.find_ti_ports() if cfg.getboolean('auto_detect_ports') else (cfg.get('cli_port'), cfg.get('data_port'))
    
    if not cli or not data:
        print("Error: Ports not found. Is the radar plugged in?")
        return
        
    radar = RadarSensor(cli, data, cfg.get('config_file'))
    parser = RadarParser(radar.config)
    
    # Start background thread
    t = threading.Thread(target=radar_thread, args=(parser, radar))
    t.do_run = True
    t.start()
    
    dpg.create_context()
    
    # Only render the heatmap in a full window
    with dpg.window(tag="Primary Window"):
        dpg.add_text("Range-Doppler Heatmap")
        with dpg.colormap_registry(show=False):
            dpg.add_colormap([[0,0,0], [0,0,255], [0,255,255], [0,255,0], [255,255,0], [255,0,0]], False, tag="viridis_ish")
        
        with dpg.plot(height=-1, width=-1, tag="heatmap_plot"):
            dpg.add_plot_axis(dpg.mvXAxis, label="Doppler Bins", tag="hm_x_axis")
            dpg.add_plot_axis(dpg.mvYAxis, label="Range Bins", tag="hm_y_axis")
            dpg.bind_colormap("heatmap_plot", "viridis_ish")

    dpg.create_viewport(title='Radar Calibrator Dashboard', width=800, height=600)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("Primary Window", True)
    
    while dpg.is_dearpygui_running():
        update_gui(parser)
        dpg.render_dearpygui_frame()
        
    t.do_run = False
    t.join()
    dpg.destroy_context()

if __name__ == "__main__":
    main()
