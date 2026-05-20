# Craton Capture

Craton Capture is a headless, CLI-based data acquisition system designed for stable, long-running research recordings. It provides highly reliable, multi-threaded capture scripts for the **Microsoft Azure Kinect DK** and **Texas Instruments mmWave Radar**.

By stripping away GUI overhead and realtime visualization, the system focuses entirely on deterministic timestamps, low dropped frames, and buffered disk writing for offline analysis.

## Features

* **Headless Architecture:** No GUI rendering or PyQT overhead. Runs entirely in the console.
* **Producer-Consumer Queues:** Acquisition threads are decoupled from storage threads to prevent disk I/O bottlenecks from dropping hardware frames.
* **Azure Kinect DK:** Captures `NFOV_UNBINNED` depth streams and asynchronous 3D native Body Tracking data. (Color capture is disabled to maximize USB bandwidth and performance).
* **TI mmWave Radar:** Captures raw binary packets directly from the high-speed data port.
* **Telemetry Tracking:** Continuously monitors capture FPS, disk write FPS, queue backlogs, tracker latency, and dropped frames.
* **Auto-Configuration:** All settings are centrally managed in an auto-generating `settings.ini` file.

## Output Formats

### Kinect (`kinect.py`)
* **Depth Stream:** `.h5` (HDF5 format, LZF compressed for realtime performance).
* **Joints & Metadata:** `.parquet` (Includes deterministic device timestamps, perf counters, and 3D joint coordinates).
* **Telemetry Log:** `.log` (CSV-formatted performance metrics).

### Radar (`radar.py`)
* **Raw Stream:** `.bin` (Continuous binary stream of TLV packets).
* **Configuration Summary:** `.json` (Human-readable extract of the radar's `.cfg` state).
* **Telemetry Log:** `.log` (CSV-formatted performance metrics).

## Installation

Ensure you have Python 3.10+ installed.

1. Clone the repository.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Ensure you have the [Azure Kinect Sensor SDK](https://github.com/microsoft/Azure-Kinect-Sensor-SDK) and [Azure Kinect Body Tracking SDK](https://github.com/microsoft/Azure-Kinect-Samples/tree/master/body-tracking-samples) installed on your system if you intend to use `kinect.py`.

## Configuration (`settings.ini`)

Upon launching either script for the first time, a `settings.ini` file is automatically generated in the root directory. You can edit this file to configure the application:

```ini
[Kinect]
fps = 30
out_dir = data
queue_maxsize = 300
telemetry_interval = 10.0

[Radar]
config_file = core/config/config.cfg
out_dir = data
queue_maxsize = 300
telemetry_interval = 10.0
# Set to 'false' if you want to manually specify COM ports
auto_detect_ports = true
cli_port = COM3
data_port = COM4
```

* **`queue_maxsize`**: The maximum number of frames to hold in memory if the disk is busy. 300 frames is ~10 seconds at 30 FPS.
* **`telemetry_interval`**: How often (in seconds) the system calculates and logs performance metrics (e.g., FPS, dropped frames).

## Usage

Simply run the desired script. Settings will be read silently from `settings.ini`.

**To record from the Azure Kinect:**
```bash
python kinect.py
```

**To record from the TI mmWave Radar:**
```bash
python radar.py
```

Press `Ctrl+C` to gracefully stop recording. The system will safely drain the remaining frames in the queue to disk and shut down the hardware.
