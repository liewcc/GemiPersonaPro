import os
import json
import copy
import logging

def get_project_root():
    return os.path.abspath(os.path.dirname(__file__))

def get_config_path():
    return os.path.join(get_project_root(), "config.json")

def get_login_lookup_path():
    return os.path.join(get_project_root(), "user_login_lookup.json")

DEFAULT_CONFIG = {
    "show_engine_console": True,
    "heartbeat_timeout": 3600,
    "headless": False,
    "browser_url": "https://gemini.google.com/app",
    "prompt": "",
    "selected_tool": "",
    "selected_model": "",
    "discovery": {
        "available_tools": [],
        "available_models": []
    },
    "automation": {
        "auto_looping": False,
        "mode": "rounds",
        "goal": 1,
        "remove_watermark": True,
        "use_gpu": True
    },
    "active_user": None,
    "save_dir": os.path.join(get_project_root(), "gemini_outputs"),
    "name_prefix": "",
    "name_padding": 2,
    "name_start": 1,
    "startup_redirect": "gemini_setup",
    "quota_full": [
        "quota exceeded",
        "daily limit",
        "reached your limit",
        "我今天无法为您创建更多图像",
        "十分抱歉"
    ],
    "selected_files": []
}

def load_config():
    """Reads config.json with fallback to defaults and protection against 0-byte reads."""
    config_path = get_config_path()
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    
    if os.path.exists(config_path):
        try:
            # Check size first to avoid race-condition empty reads
            if os.path.getsize(config_path) > 0:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        # Use update pattern to preserve non-default keys if any, 
                        # but ensure all default keys exist.
                        cfg.update(data)
        except Exception as e:
            print(f"[CONFIG] Read Error: {e}")
            # Fallback to DEFAULT_CONFIG is already in cfg
    return cfg

def save_config(updates):
    """Merges updates into current config and writes atomically."""
    current = load_config()
    current.update(updates)
    
    config_path = get_config_path()
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=4, ensure_ascii=False)
        return current
    except Exception as e:
        print(f"[CONFIG] Write Error: {e}")
        return current

def load_login_lookup():
    """Reads user_login_lookup.json with protection against 0-byte reads."""
    lookup_path = get_login_lookup_path()
    if os.path.exists(lookup_path):
        try:
            if os.path.getsize(lookup_path) > 0:
                with open(lookup_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
        except Exception as e:
            print(f"[CONFIG] Lookup Read Error: {e}")
    return []

def save_login_lookup(data):
    """Writes user_login_lookup.json atomically."""
    lookup_path = get_login_lookup_path()
    try:
        with open(lookup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[CONFIG] Lookup Write Error: {e}")
        return False
