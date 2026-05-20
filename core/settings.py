import os
import configparser
import logging
from rich.console import Console

console = Console()
log = logging.getLogger("Settings")

DEFAULT_SETTINGS_PATH = "settings.ini"

def generate_default_settings(path: str):
    config = configparser.ConfigParser()
    
    config['Kinect'] = {
        'fps': '30',
        'out_dir': 'data',
        'queue_maxsize': '300',
        'telemetry_interval': '10.0'
    }
    
    config['Radar'] = {
        'config_file': 'core/config/config.cfg',
        'out_dir': 'data',
        'queue_maxsize': '300',
        'telemetry_interval': '10.0',
        'auto_detect_ports': 'true',
        'cli_port': 'COM3',
        'data_port': 'COM4'
    }
    
    with open(path, 'w') as configfile:
        config.write(configfile)
    console.print(f"[green]Generated default settings at {path}[/green]")

def load_settings(path: str = DEFAULT_SETTINGS_PATH) -> configparser.ConfigParser:
    if not os.path.exists(path):
        generate_default_settings(path)
        
    config = configparser.ConfigParser()
    config.read(path)
    return config
