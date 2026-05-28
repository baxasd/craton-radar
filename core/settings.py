import os
import sys
import configparser

def get_base_path():
    """Returns the base path for the application."""
    if getattr(sys, 'frozen', False):
        # If frozen, sys.executable is the path to the .exe
        # In 'onedir' with 'contents_directory="libs"', the exe is in the root
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if os.path.isabs(relative_path):
        return relative_path
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = get_base_path()

    return os.path.join(base_path, relative_path)

SETTINGS_PATH = os.path.join(get_base_path(), "settings.ini")

DEFAULTS = {
    'Radar': {
        'config_file': 'core/config.cfg',
        'out_dir': 'data',
        'queue_maxsize': '300',
        'telemetry_interval': '10.0',
        'auto_detect_ports': 'true',
        'cli_port': 'COM3',  # Windows default
        'data_port': 'COM4'
    },
    'Calibrator': {
        'max_display_range_m': '5.0',
        'zoom_factor': '3',
        'min_percentile': '5.0',
        'max_percentile': '99.5',
        'ui_refresh_rate': '0.033'
    }
}

def ensure_config():
    """Checks if settings.ini exists, creates it with defaults if not, and ensures all sections exist."""
    config = configparser.ConfigParser()
    
    if os.path.exists(SETTINGS_PATH):
        config.read(SETTINGS_PATH)
    
    modified = False
    for section, options in DEFAULTS.items():
        if section not in config:
            config[section] = options
            modified = True
        else:
            # Ensure all default options exist within the section
            for option, value in options.items():
                if option not in config[section]:
                    config[section][option] = value
                    modified = True
                    
    if modified:
        save_settings(config)
    
    return config

def load_settings():
    """Ensures config exists and returns the ConfigParser object."""
    return ensure_config()

def save_settings(config):
    """Writes the current ConfigParser state to settings.ini."""
    with open(SETTINGS_PATH, 'w') as f:
        config.write(f)
