import os
import configparser

SETTINGS_PATH = "settings.ini"

DEFAULTS = {
    'Radar': {
        'config_file': 'core/config.cfg',
        'out_dir': 'data',
        'queue_maxsize': '300',
        'telemetry_interval': '10.0',
        'auto_detect_ports': 'true',
        'cli_port': '/dev/ttyUSB0',  # Linux default as seen in user's previous output
        'data_port': '/dev/ttyUSB1'
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
