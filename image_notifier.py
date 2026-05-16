import os
import sys
import subprocess
import time
import threading
import json
import asyncio
import urllib.request
import tkinter as tk
import pystray
from PIL import Image
import config_utils
import ctypes

# Suppress the harmless Windows asyncio cleanup noise:
# "ConnectionResetError: [WinError 10054] An existing connection was forcibly closed"
# This occurs when a remote HTTP server (FastAPI / Streamlit) closes its socket
# abruptly and the ProactorEventLoop tries to call sock.shutdown() on an already-
# closed socket.  It is a known CPython bug and has zero functional impact.
def _silence_proactor_pipe_errors(loop, context):
    exc = context.get('exception')
    if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
        return  # Suppress silently
    loop.default_exception_handler(context)

try:
    _loop = asyncio.get_event_loop()
except RuntimeError:
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
_loop.set_exception_handler(_silence_proactor_pipe_errors)

def open_file_foreground(file_path):
    """Opens a file or directory and ensures it comes to the foreground."""
    abs_path = os.path.abspath(file_path)
    if os.name == 'nt':
        try:
            # Simulate Alt key press to unlock focus permission on Windows
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
            ctypes.windll.user32.AllowSetForegroundWindow(-1)
        except: pass
        os.startfile(abs_path)
    else:
        if hasattr(os, 'startfile'): os.startfile(abs_path)
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, abs_path])

app_running = True
current_dir_display = ""
current_upscale_dir = ""
tray_icon = None
_status_popup_open   = False
_download_popup_open = False

# Resolve icon path relative to this script's location
_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_TRAY_ICON_PATH = os.path.join(_SCRIPT_DIR, 'sys_img', 'icon_no_BG.png')
_STATE_FILE = os.path.join(_SCRIPT_DIR, 'notifier_state.json')
_LOG_FILE   = os.path.join(_SCRIPT_DIR, 'notifier_error.log')

# ── Global error logger (critical for pythonw.exe which has no console) ─────
import logging as _logging, sys as _sys
_logging.basicConfig(
    filename=_LOG_FILE, level=_logging.ERROR,
    format='%(asctime)s [%(threadName)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def _global_excepthook(exc_type, exc_val, exc_tb):
    _logging.error('Unhandled exception', exc_info=(exc_type, exc_val, exc_tb))
    _sys.__excepthook__(exc_type, exc_val, exc_tb)

_sys.excepthook = _global_excepthook

def load_notifier_state():
    """Load the last acknowledged file list."""
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {
                    'auto': set(data.get('last_ack_auto', data.get('last_ack_files', []))),
                    'upscale': set(data.get('last_ack_upscale', [])),
                    'disable_auto_popup': data.get('disable_auto_popup', False)
                }
        except:
            pass
    return {'auto': set(), 'upscale': set(), 'disable_auto_popup': False}

def save_notifier_state(auto_set, upscale_set):
    """Save the current directory files as acknowledged."""
    try:
        data = {}
        if os.path.exists(_STATE_FILE):
            with open(_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        data['last_ack_auto'] = list(auto_set)
        data['last_ack_upscale'] = list(upscale_set)
        with open(_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except:
        pass

def get_automation_stats():
    """Fetch full automation stats from the engine service."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/browser/automation/stats")
        with urllib.request.urlopen(req, timeout=1.5) as response:
            return json.loads(response.read().decode())
    except Exception:
        return {}


def is_gemipersona_running():
    """Check if GemiPersona Streamlit is listening on port 8501.
    Uses a raw TCP connect instead of HTTP to avoid triggering asyncio
    ProactorPipe ConnectionResetError (WinError 10054) on the Streamlit side.
    """
    import socket
    try:
        with socket.create_connection(('127.0.0.1', 8501), timeout=0.5):
            return True
    except OSError:
        return False

# ---------------------------------------------------------------------------
# Monitor window — launched as a SEPARATE PROCESS (monitor_window.py)
# Running it in-process via tk.Tk() in a thread shared Tcl interpreter state
# with the popup; destroying the popup sent PostQuitMessage / cleared
# _default_root and crashed the monitor window.  A subprocess is immune.
# ---------------------------------------------------------------------------

_monitor_proc = None   # subprocess.Popen handle

def _show_monitor_window():
    """Launch monitor_window.py as a separate pythonw process.
    If one is already running, bring it to the foreground instead.
    """
    global _monitor_proc
    # If a previous instance is still alive, don't open another one
    if _monitor_proc is not None and _monitor_proc.poll() is None:
        return   # already running — do nothing (process manages its own focus)

    hw_script = os.path.join(_SCRIPT_DIR, 'monitor_window.py')
    if not os.path.exists(hw_script):
        _logging.error(f'monitor_window.py not found at {hw_script}')
        return

    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if not os.path.exists(pythonw):
        pythonw = sys.executable  # fallback to python.exe on non-Windows

    try:
        _monitor_proc = subprocess.Popen(
            [pythonw, hw_script],
            cwd=_SCRIPT_DIR,
            close_fds=True
        )
    except Exception as _e:
        _logging.error(f'_show_monitor_window: failed to launch: {_e}', exc_info=True)


# ---------------------------------------------------------------------------
# Shared helper: launch popup_window.py as a subprocess
# ---------------------------------------------------------------------------

def _launch_popup_subprocess(data_dict):
    """Launch popup_window.py as a separate pythonw process to avoid Tcl crashes."""
    popup_script = os.path.join(_SCRIPT_DIR, 'popup_window.py')
    if not os.path.exists(popup_script):
        return

    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if not os.path.exists(pythonw):
        pythonw = sys.executable

    try:
        subprocess.Popen(
            [pythonw, popup_script, json.dumps(data_dict)],
            cwd=_SCRIPT_DIR,
            close_fds=True
        )
    except Exception as _e:
        _logging.error(f'_launch_popup_subprocess failed: {_e}', exc_info=True)


# ---------------------------------------------------------------------------
# Show Status popup  (user-triggered via tray menu)
# ---------------------------------------------------------------------------

def _show_status_popup():
    """Show status popup — bypasses Windows notification system entirely."""
    global _status_popup_open
    if _status_popup_open:
        return
    _status_popup_open = True

    try:
        stats = get_automation_stats()
        auto_running = stats.get('is_running', False)
        up_running = os.path.exists(os.path.join(_SCRIPT_DIR, "upscaler.lock"))

        last_ack = load_notifier_state()
        
        auto_pending = 0
        if current_dir_display and os.path.exists(current_dir_display):
            current_auto = set(os.listdir(current_dir_display))
            auto_pending = len([f for f in (current_auto - last_ack.get('auto', set())) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp4'))])
            
        up_pending = 0
        if current_upscale_dir and os.path.exists(current_upscale_dir):
            current_up = set(os.listdir(current_upscale_dir))
            up_pending = len([f for f in (current_up - last_ack.get('upscale', set())) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp4'))])
        
        data = {
            "title_text": "GemiPersona Notifier",
            "auto_pending": auto_pending,
            "up_pending": up_pending,
            "auto_running": auto_running,
            "up_running": up_running,
            "auto_folder": current_dir_display,
            "upscale_folder": current_upscale_dir
        }
        _launch_popup_subprocess(data)

    finally:
        _status_popup_open = False


# ---------------------------------------------------------------------------
# New Downloads popup  (auto-triggered when new images are detected)
# ---------------------------------------------------------------------------

def _show_new_files_popup(auto_images, up_images, 
                          total_auto_pending, total_up_pending, current_auto_files, current_up_files,
                          current_auto_dir, current_up_dir):
    """Show a new-download alert popup — bypasses Windows notification system entirely.
    Auto-dismisses after 8 seconds if the user takes no action.
    """
    global _download_popup_open
    if _download_popup_open:
        return
    _download_popup_open = True

    try:
        count = len(auto_images) + len(up_images)
        
        stats = get_automation_stats()
        auto_running = stats.get('is_running', False)
        up_running = os.path.exists(os.path.join(_SCRIPT_DIR, "upscaler.lock"))

        data = {
            "title_text": f"GemiPersona — {count} New Image{'s' if count > 1 else ''}",
            "auto_pending": total_auto_pending,
            "up_pending": total_up_pending,
            "auto_running": auto_running,
            "up_running": up_running,
            "auto_folder": current_auto_dir,
            "upscale_folder": current_up_dir,
            "auto_close_ms": 8000
        }
        _launch_popup_subprocess(data)

    finally:
        _download_popup_open = False


# ---------------------------------------------------------------------------
# Background monitor thread
# ---------------------------------------------------------------------------

def monitor_directory():
    global app_running, current_dir_display, current_upscale_dir

    last_auto_files = set()
    last_upscale_files = set()
    
    current_auto_dir = ""
    current_up_dir = ""

    # Initial check
    try:
        config = config_utils.load_config()
        initial_auto = config.get('save_dir', '')
        if initial_auto and os.path.exists(initial_auto):
            current_dir_display = initial_auto
            current_auto_dir = initial_auto
            last_auto_files = set(os.listdir(current_auto_dir))
        else:
            current_dir_display = "Not set or not found"
            
        initial_up = config.get('upscaler', {}).get('output_dir', '')
        if initial_up and os.path.exists(initial_up):
            current_upscale_dir = initial_up
            current_up_dir = initial_up
            last_upscale_files = set(os.listdir(current_up_dir))
        else:
            current_upscale_dir = "Not set or not found"
    except Exception:
        pass

    while app_running:
        try:
            time.sleep(5)

            config  = config_utils.load_config()
            new_auto = config.get('save_dir', '')
            new_up = config.get('upscaler', {}).get('output_dir', '')

            auto_changed = False
            up_changed = False

            if new_auto and os.path.exists(new_auto):
                current_dir_display = new_auto
                if new_auto != current_auto_dir:
                    current_auto_dir = new_auto
                    last_auto_files = set(os.listdir(current_auto_dir))
                    auto_changed = True
            else:
                current_dir_display = "Not set or not found"
                last_auto_files = set()

            if new_up and os.path.exists(new_up):
                current_upscale_dir = new_up
                if new_up != current_up_dir:
                    current_up_dir = new_up
                    last_upscale_files = set(os.listdir(current_up_dir))
                    up_changed = True
            else:
                current_upscale_dir = "Not set or not found"
                last_upscale_files = set()

            if auto_changed or up_changed:
                state = load_notifier_state()
                if auto_changed: state['auto'] = last_auto_files
                if up_changed: state['upscale'] = last_upscale_files
                save_notifier_state(state['auto'], state['upscale'])
                continue

            current_auto_files = set(os.listdir(current_auto_dir)) if current_auto_dir else set()
            current_up_files = set(os.listdir(current_up_dir)) if current_up_dir else set()

            new_auto_files = current_auto_files - last_auto_files
            new_up_files = current_up_files - last_upscale_files

            auto_images = [f for f in new_auto_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp4'))]
            up_images = [f for f in new_up_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp4'))]

            if auto_images or up_images:
                # Give the engine a short grace period to update its internal success counter
                time.sleep(1.5)
                
                stats = get_automation_stats()
                l_state = "Running" if stats.get('is_running', False) else "Stopped"
                active_account = config.get('active_user', 'N/A') or 'N/A'

                last_ack = load_notifier_state()
                
                save_needed = False
                if not last_ack['auto'] and current_auto_files:
                    last_ack['auto'] = last_auto_files
                    save_needed = True
                if not last_ack['upscale'] and current_up_files:
                    last_ack['upscale'] = last_upscale_files
                    save_needed = True
                if save_needed:
                    save_notifier_state(last_ack['auto'], last_ack['upscale'])

                total_auto_pending = [f for f in (current_auto_files - last_ack['auto']) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp4'))]
                total_up_pending = [f for f in (current_up_files - last_ack['upscale']) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp4'))]

                if len(total_auto_pending) > 0 or len(total_up_pending) > 0:
                    if not last_ack.get('disable_auto_popup', False):
                        threading.Thread(
                            target=_show_new_files_popup,
                            args=(auto_images, up_images, 
                                  len(total_auto_pending), len(total_up_pending),
                                  current_auto_files, current_up_files,
                                  current_auto_dir, current_up_dir),
                            daemon=True
                        ).start()

            last_auto_files = current_auto_files
            last_upscale_files = current_up_files

        except Exception:
            time.sleep(5)


# ---------------------------------------------------------------------------
# Tray menu callbacks
# ---------------------------------------------------------------------------

def show_status(icon, item):
    threading.Thread(target=_show_status_popup, daemon=True).start()


def quit_app(icon, item):
    global app_running, _monitor_proc
    app_running = False
    icon.stop()
    
    # Try to gracefully kill the tracked monitor process
    if _monitor_proc is not None and _monitor_proc.poll() is None:
        try:
            _monitor_proc.terminate()
        except:
            pass
            
    # Also aggressively clean up any orphaned monitor or popup windows
    try:
        import psutil
        for p in psutil.process_iter(['cmdline']):
            try:
                cmd = p.info.get('cmdline')
                if cmd:
                    joined = ' '.join(cmd)
                    if 'monitor_window.py' in joined or 'popup_window.py' in joined:
                        p.terminate()
            except:
                pass
    except:
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    global tray_icon
    monitor_thread = threading.Thread(target=monitor_directory, daemon=True)
    monitor_thread.start()

    icon_img = Image.open(_TRAY_ICON_PATH)
    def show_monitor(icon, item):
        threading.Thread(target=_show_monitor_window, daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem("Show Status", show_status, default=True),
        pystray.MenuItem("Monitor", show_monitor),
        pystray.MenuItem("Quit", quit_app)
    )

    def _start_tray():
        """Start (or restart) the tray icon in its own detached thread."""
        global tray_icon
        try:
            tray_icon = pystray.Icon("GemiPersonaNotifier", icon_img, "GemiPersona Notifier", menu)
            # run_detached() spawns an internal thread for the Win32 message loop.
            # This isolates pystray from Tkinter's PostQuitMessage calls, which
            # previously caused the main message loop to exit unexpectedly.
            tray_icon.run_detached()
            _logging.error('tray_icon.run_detached() started OK')
        except Exception as _e:
            _logging.error(f'_start_tray failed: {_e}', exc_info=True)

    _start_tray()

    # ── Main thread keep-alive ──────────────────────────────────────────────
    # The main thread must stay alive for daemon threads to keep running.
    # Every 10 s we check if the tray icon is still alive; if not, restart it.
    _TRAY_CHECK_INTERVAL = 10
    while app_running:
        time.sleep(_TRAY_CHECK_INTERVAL)
        if not app_running:
            break
        # Restart tray if it died unexpectedly (but not if user chose Quit)
        try:
            if not tray_icon.visible:
                _logging.error('tray_icon not visible — restarting')
                _start_tray()
        except Exception:
            pass


if __name__ == '__main__':
    main()
