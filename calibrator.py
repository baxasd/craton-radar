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
            # Reshape to 2D
            hm_2d = hm_copy.reshape((rb, db))
            
            # Shift doppler so 0 is in the middle
            hm_2d = np.fft.fftshift(hm_2d, axes=1)
            
            # Zoom by a factor of 2 (instead of 4 to save CPU) for smooth look
            # ndimage.zoom is slow, but at 2x it's acceptable for now
            hm_zoomed = ndimage.zoom(hm_2d, 2, order=1)
            new_rb, new_db = hm_zoomed.shape
            
            flat_data = hm_zoomed.flatten().tolist()
            
            if not dpg.does_alias_exist("heatmap_series"):
                dpg.add_heat_series(
                    flat_data, new_rb, new_db, 
                    label="Range-Doppler", 
                    parent="hm_y_axis", 
                    tag="heatmap_series",
                    scale_min=0, scale_max=4,
                    bounds_min=(-db//2, 0), bounds_max=(db//2, rb)
                )
            else:
                dpg.set_value("heatmap_series", [flat_data])
                
            # Update plot title with simple FPS (estimated)
            dpg.set_item_label("heatmap_plot", f"Range-Doppler Heatmap ({rb}x{db} bins)")
            
        except Exception as e:
            # print(f"Update error: {e}")
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
    
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 10, 10)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 5, 5)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 8)
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, [20, 20, 25])
        
        with dpg.theme_component(dpg.mvPlot):
            dpg.add_theme_color(dpg.mvPlotCol_PlotBg, [10, 10, 12], category=dpg.mvThemeCat_Plots)
            dpg.add_theme_color(dpg.mvPlotCol_AxisGrid, [40, 40, 45], category=dpg.mvThemeCat_Plots)

    dpg.bind_theme(global_theme)
    
    with dpg.window(tag="Primary Window"):
        with dpg.group(horizontal=True):
            dpg.add_text("CRATON RADAR CALIBRATOR", color=[0, 255, 127])
            dpg.add_spacer(width=20)
            dpg.add_text("Status: ONLINE", tag="status_text", color=[0, 255, 0])

        dpg.add_separator()
        dpg.add_spacer(height=5)
        
        with dpg.colormap_registry(show=False):
            # A more professional "Turbo" or "Inferno" style colormap
            dpg.add_colormap([
                [0, 0, 40],       # Deep Blue
                [0, 0, 255],      # Blue
                [0, 255, 255],    # Cyan
                [0, 255, 0],      # Green
                [255, 255, 0],    # Yellow
                [255, 0, 0],      # Red
                [255, 255, 255]   # White (Peak)
            ], False, tag="radar_cmap")
        
        with dpg.plot(height=-1, width=-1, tag="heatmap_plot", no_menus=True):
            dpg.add_plot_legend()
            dpg.add_plot_axis(dpg.mvXAxis, label="Velocity (Bins)", tag="hm_x_axis")
            dpg.add_plot_axis(dpg.mvYAxis, label="Range (Bins)", tag="hm_y_axis")
            dpg.bind_colormap("heatmap_plot", "radar_cmap")
            
            # Set initial axis limits
            dpg.set_axis_limits("hm_y_axis", 0, radar.config.numRangeBins)
            dpg.set_axis_limits("hm_x_axis", -radar.config.numDopplerBins//2, radar.config.numDopplerBins//2)

    dpg.create_viewport(title='Radar Calibrator Dashboard', width=1000, height=800)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("Primary Window", True)
    
    # Use a fixed frame rate for UI to keep CPU usage sane
    while dpg.is_dearpygui_running():
        update_gui(parser)
        dpg.render_dearpygui_frame()
        
    t.do_run = False
    t.join()
    dpg.destroy_context()

if __name__ == "__main__":
    main()
