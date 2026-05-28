import math
import time
import logging
import serial
from serial.tools import list_ports

log = logging.getLogger("RadarHardware")

_MAGIC = b"\x02\x01\x04\x03\x06\x05\x08\x07"
_TI_VID = 0x0451

class RadarConfig:
    def __init__(self, file_path: str):
        self.file_path = file_path
        with open(file_path) as f:
            lines = [l.split() for l in f if l.strip() and not l.startswith("%")]
        
        profile = {}
        frame = {}
        for val in lines:
            if val[0] == "profileCfg":
                profile = {"numADCsamples": int(val[10])}
            if val[0] == "frameCfg":
                frame = {"numLoops": int(val[3])}
        
        if not profile:
            raise ValueError(f"No profileCfg found in {file_path}")
            
        self.ADCsamples = profile.get("numADCsamples", 64)
        self.numRangeBins = 1 if self.ADCsamples == 0 else 2 ** math.ceil(math.log2(self.ADCsamples))
        self.numDopplerBins = frame.get("numLoops", 32)

class RadarSensor:
    def __init__(self, cli_port: str, data_port: str, config_file: str):
        self.config = RadarConfig(config_file)
        self._cli_port = cli_port
        self._data_port = data_port
        self._cli = None
        self._data = None
        self._buffer = bytearray()

    def connect_and_configure(self):
        self._cli = serial.Serial(self._cli_port, 115200, timeout=0.6)
        self._data = serial.Serial(self._data_port, 921600, timeout=1.0)
        self._data.reset_output_buffer()
        
        with open(self.config.file_path) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("%")]

        for line in lines:
            self._cli.write((line + "\n").encode())
            if line.startswith("sensorStop"):
                time.sleep(0.1)
                self._cli.reset_input_buffer()
                continue
            if line.startswith("sensorStart"):
                time.sleep(0.05)
                self._cli.reset_input_buffer()
                continue
            
            deadline = time.time() + 0.3
            while time.time() < deadline:
                resp = self._cli.readline().decode(errors="ignore").strip()
                if "Done" in resp: break
        self._cli.reset_input_buffer()

    def read_raw_frame(self) -> bytes | None:
        in_waiting = self._data.in_waiting
        if in_waiting > 0:
            self._buffer.extend(self._data.read(in_waiting))
        else:
            chunk = self._data.read(4096)
            if not chunk: return None
            self._buffer.extend(chunk)

        if len(self._buffer) > 32768: # Buffer safety
            idx = self._buffer.find(_MAGIC, 1)
            self._buffer = self._buffer[idx:] if idx != -1 else bytearray()
            return None

        idx = self._buffer.find(_MAGIC)
        if idx == -1:
            if len(self._buffer) > 7: self._buffer = self._buffer[-7:]
            return None
        
        if idx > 0: self._buffer = self._buffer[idx:]
        if len(self._buffer) < 40: return None

        frame_len = int.from_bytes(self._buffer[12:16], byteorder="little")
        if not (16 <= frame_len <= 32768):
            self._buffer = self._buffer[8:]
            return None

        if len(self._buffer) < frame_len: return None

        frame_data = bytes(self._buffer[:frame_len])
        self._buffer = self._buffer[frame_len:]
        return frame_data

    def close(self):
        if self._cli and self._cli.is_open:
            try:
                self._cli.write(b"sensorStop\n")
                time.sleep(0.1)
            except: pass
        for p in (self._cli, self._data):
            if p and p.is_open: p.close()

    @staticmethod
    def find_ti_ports():
        cli = data = None
        for p in list_ports.comports():
            desc = (p.description or "").lower()
            if "application/user uart" in desc or "enhanced com port" in desc: cli = p.device
            elif "auxiliary data port" in desc or "standard com port" in desc: data = p.device
            elif getattr(p, "vid", None) in (_TI_VID, 0x10c4):
                if cli is None: cli = p.device
                elif data is None: data = p.device
        return cli, data
