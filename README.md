# Craton Radar

[![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/) 
[![TI mmWave](https://img.shields.io/badge/TI_mmWave-Serial-red.svg?style=flat)](https://www.ti.com/sensors/mmwave/overview.html)
[![DearPyGui](https://img.shields.io/badge/DearPyGui-2.0-blue.svg?style=flat)](https://github.com/hoffstadt/DearPyGui)
[![License](https://img.shields.io/badge/License-Apache_2.0-blueviolet.svg?style=flat)](LICENSE)

A high-performance CLI tool for raw data acquisition and real-time heatmap visualization from Texas Instruments mmWave Radar sensors.

## Architecture

The system is designed for high-throughput data ingestion and consists of core hardware drivers and visualization nodes:

- **`core/engine.py`**: Handles serial communication, hardware configuration (CLI), and TLV frame parsing.
- **`core/settings.py`**: Manages persistence and auto-generation of global defaults in `settings.ini`.
- **`recorder.py`**: Headless CLI interface for multi-threaded binary data recording and live telemetry.
- **`calibrator.py`**: Real-time visualizer providing a physics-corrected Range-Doppler Heatmap using DearPyGui and SciPy.

## Binary File Structure

Captured data is saved in a raw stream format. Each `.bin` file begins with a metadata header containing the configuration used during capture.

### 1. Metadata Header (File Start)
- **Length**: `4 bytes` (uint32, little-endian). Length of the JSON string.
- **Content**: `N bytes` (UTF-8 encoded JSON string). Contains:
  - `config`: Radar commands, resolutions (range/doppler), and bin counts.
  - `timestamp`: Start time of the recording.

### 2. Frame Data Stream (Sequential)
- **TI Magic Word**: `8 bytes` (`02 01 04 03 06 05 08 07`).
- **Header**: `32 bytes` (Version, Total Length, Frame Number, CPU Cycles, etc.).
- **TLV Payload**: Variable length block containing detected objects and heatmaps as defined in the radar configuration.

## Installation & Usage

### Setup
1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Linux Serial Permissions**:
   To access the radar serial ports without root privileges, add your user to the `dialout` group:
   ```bash
   sudo usermod -a -G dialout $USER
   ```
   *Note: You must log out and back in for this to take effect.*

3. **Linux Performance Optimization (Optional)**:
   By default, Linux buffers serial data for 16ms. To achieve a stable and high FPS, set the data port to low latency mode:
   ```bash
   # Install setserial if needed
   sudo apt-get install setserial
   # Set your data port (usually /dev/ttyUSB1) to low latency
   sudo setserial /dev/ttyUSB1 low_latency
   ```

### Execution (Python)
Run the application to start the data acquisition CLI:
```bash
python recorder.py
```
A `settings.ini` file will be generated on first run. Configure your COM ports and radar configuration file path there.

To verify the radar signal and configure visualization depth, run:
```bash
python calibrator.py
```

### Execution (Standalone Binary)
Once built (see below), navigate to the `dist/craton_radar/` directory:
```bash
# Run Recorder
./radar_recorder

# Run Calibrator
./radar_calibrator
```

## Building from Source

The project uses PyInstaller for creating standalone executables and Inno Setup for Windows installers.

### Windows Build (x64)
1. **Install PyInstaller**:
   ```bash
   pip install pyinstaller
   ```
2. **Run Build Script**:
   ```bash
   pyinstaller tools/windows/build.spec
   ```
   The output will be in `dist/craton_radar/`.
3. **Generate Installer (Optional)**:
   - Install [Inno Setup 6+](https://jrsoftware.org/isdl.php).
   - Open `tools/windows/installer.iss` and click "Compile".
   - The setup file will be created in `tools/windows/output/`.

### Linux Build
1. **Install PyInstaller**:
   ```bash
   pip install pyinstaller
   ```
2. **Run Build Script**:
   ```bash
   pyinstaller tools/linux/build.spec
   ```
   The output will be in `dist/craton_radar/`.

## Contribution & License

- **License**: Distributed under the [Apache 2.0 License](LICENSE).
- **Contributions**: Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change. PRs containing unreviewed, generated AI content will be closed.
