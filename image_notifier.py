import os
import time
import ctypes
import threading
import json
import urllib.request
import pystray
from PIL import Image, ImageDraw
import config_utils

app_running = True
current_dir_display = ""
tray_icon = None

def create_image(width, height, color1, color2):
    # Create a nice placeholder icon image
    image = Image.new('RGB', (width, height), color1)
    dc = ImageDraw.Draw(image)
    dc.rectangle((width // 2, 0, width, height // 2), fill=color2)
    dc.rectangle((0, height // 2, width // 2, height), fill=color2)
    return image

def is_looping_active():
    # Sync HTTP request to local engine
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/browser/automation/stats")
        with urllib.request.urlopen(req, timeout=1.5) as response:
            data = json.loads(response.read().decode())
            return data.get('is_running', False)
    except Exception:
        return False

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
        
    MB_YESNO = 0x04
    MB_TOPMOST = 0x40000
    style = MB_YESNO | MB_TOPMOST
    
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
                    
                l_state = "Running" if is_looping_active() else "Stopped / Offline"
                active_account = config.get('active_user', 'N/A') or 'N/A'
                msg = f"New image(s) downloaded!\n\nLooping System: {l_state}\nActive Account: {active_account}\nDirectory: {current_dir}\nIncludes:\n{file_list}\n\n[Yes] = Open folder\n[No] = Close message"
                
                # WinAPI native blocking message box
                result = ctypes.windll.user32.MessageBoxW(0, msg, 'GemiPersona Notification', style)
                if result == 6: # IDYES
                    os.startfile(current_dir)
                
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
        ctypes.windll.user32.MessageBoxW(0, msg, 'GemiPersona Status', 0x40000) # MB_OK
    else:
        l_state = "Running" if is_looping_active() else "Stopped / Offline"
        active_account = config_utils.load_config().get('active_user', 'N/A') or 'N/A'
        msg = f"GemiPersona Monitoring Active\n\nLooping System: {l_state}\nActive Account: {active_account}\nMonitoring Directory:\n{current_dir_display}\n\n[Yes] = Open folder\n[No] = Close message"
        
        # MB_YESNO | MB_TOPMOST
        style = 0x04 | 0x40000
        result = ctypes.windll.user32.MessageBoxW(0, msg, 'GemiPersona Status', style)
        if result == 6: # IDYES
            try:
                os.startfile(current_dir_display)
            except Exception:
                pass

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
    
    # 2. Start sys-tray app
    icon_img = create_image(64, 64, '#333333', '#1e90ff') # Dark / Blue icon
    menu = pystray.Menu(
        pystray.MenuItem("Show Status", show_status, default=True),
        pystray.MenuItem("Quit", quit_app)
    )
    
    tray_icon = pystray.Icon("GemiPersonaNotifier", icon_img, "GemiPersona Notifier", menu)
    tray_icon.run()

if __name__ == '__main__':
    main()
