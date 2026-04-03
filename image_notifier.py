import os
import time
import threading
import json
import urllib.request
import pystray
from PIL import Image
from win11toast import toast
import config_utils

app_running = True
current_dir_display = ""
tray_icon = None

# Resolve icon paths relative to this script's location
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_TRAY_ICON_PATH = os.path.join(_SCRIPT_DIR, 'sys_img', 'icon_no_BG.png')
_TOAST_ICON_PATH = os.path.join(_SCRIPT_DIR, 'sys_img', 'icon.png')

def get_automation_stats():
    """Fetch full automation stats from the engine service."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/browser/automation/stats")
        with urllib.request.urlopen(req, timeout=1.5) as response:
            return json.loads(response.read().decode())
    except Exception:
        return {}



def monitor_directory():
    global app_running, current_dir_display
    
    last_files = set()
    current_dir = ""
    
    # Run an initial config check instantly before the 5s loop begins
    try:
        config = config_utils.load_config()
        initial_dir = config.get('save_dir', '')
        if initial_dir and os.path.exists(initial_dir):
            current_dir_display = initial_dir
            current_dir = initial_dir
            last_files = set(os.listdir(current_dir))
        else:
            current_dir_display = "Not set or not found"
    except Exception:
        pass
        

    
    while app_running:
        try:
            # Main cycle sleep
            time.sleep(5)
            
            # Load config and path dynamically
            config = config_utils.load_config()
            new_dir = config.get('save_dir', '')
            
            if not new_dir or not os.path.exists(new_dir):
                current_dir_display = "Not set or not found"
                continue
                
            current_dir_display = new_dir
            if new_dir != current_dir:
                current_dir = new_dir
                last_files = set(os.listdir(current_dir))
                continue
                
            current_files = set(os.listdir(current_dir))
            new_files = current_files - last_files
            
            image_files = [f for f in new_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
            
            if image_files:
                file_list = '\n'.join([f"- {f}" for f in image_files[:10]])
                if len(image_files) > 10:
                    file_list += f"\n... and {len(image_files) - 10} more."
                    
                stats = get_automation_stats()
                l_state = "Running" if stats.get('is_running', False) else "Stopped"
                active_account = config.get('active_user', 'N/A') or 'N/A'
                s_cycles = stats.get('cycles', 0)
                s_images = stats.get('successes', 0)
                s_refused = stats.get('refusals', 0)
                s_resets = stats.get('resets', 0)
                msg = (f"Account: {active_account} [{l_state}]\n"
                       f"Cycle: {s_cycles}  Image: {s_images}  Refused: {s_refused}  Reset: {s_resets}\n"
                       f"Path: {current_dir}")
                
                path_uri = f'file:///{current_dir.replace("\\", "/")}'
                buttons = [
                    {'activationType': 'protocol', 'arguments': path_uri, 'content': 'Open Folder'},
                    {'activationType': 'background', 'arguments': 'dismiss', 'content': 'Dismiss'}
                ]
                
                # Native win11 toast notification
                toast(
                    "GemiPersona - Download Complete",
                    msg,
                    icon=_TOAST_ICON_PATH,
                    buttons=buttons,
                    audio={'silent': False} 
                )
                
                # Immediately refresh current_files AFTER the popup is closed
                # This intentionally skips any images that dropped in while the popup was open
                current_files = set(os.listdir(current_dir))
                    
            last_files = current_files
            
        except Exception:
            # Swallow parsing/IO exceptions and retry safely later
            time.sleep(5)

def _show_status_thread():
    global app_running
    if not current_dir_display or current_dir_display == "Not set or not found":
        msg = "GemiPersona Initializing or Directory Not Set...\n\nPlease ensure your configuration is saved."
        toast("GemiPersona Status", msg, icon=_TOAST_ICON_PATH, audio={'silent': True})
    else:
        stats = get_automation_stats()
        l_state = "Running" if stats.get('is_running', False) else "Stopped"
        active_account = config_utils.load_config().get('active_user', 'N/A') or 'N/A'
        s_cycles = stats.get('cycles', 0)
        s_images = stats.get('successes', 0)
        s_refused = stats.get('refusals', 0)
        s_resets = stats.get('resets', 0)
        msg = (f"Account: {active_account} [{l_state}]\n"
               f"Cycle: {s_cycles}  Image: {s_images}  Refused: {s_refused}  Reset: {s_resets}\n"
               f"Path: {current_dir_display}")
        
        path_uri = f'file:///{current_dir_display.replace("\\", "/")}'
        buttons = [
            {'activationType': 'protocol', 'arguments': path_uri, 'content': 'Open Folder'},
            {'activationType': 'background', 'arguments': 'dismiss', 'content': 'Dismiss'}
        ]
        
        toast("GemiPersona Status", msg, icon=_TOAST_ICON_PATH, buttons=buttons, audio={'silent': True})

def show_status(icon, item):
    # Launch in a new thread so it doesn't block the pystray system tray event loop
    threading.Thread(target=_show_status_thread, daemon=True).start()

def quit_app(icon, item):
    global app_running
    app_running = False
    icon.stop()

def main():
    global tray_icon
    # 1. Start background monitor thread
    monitor_thread = threading.Thread(target=monitor_directory, daemon=True)
    monitor_thread.start()
    
    # 2. Start sys-tray app with real GemiPersona icon
    icon_img = Image.open(_TRAY_ICON_PATH)
    menu = pystray.Menu(
        pystray.MenuItem("Show Status", show_status, default=True),
        pystray.MenuItem("Quit", quit_app)
    )
    
    tray_icon = pystray.Icon("GemiPersonaNotifier", icon_img, "GemiPersona Notifier", menu)
    tray_icon.run()

if __name__ == '__main__':
    main()
