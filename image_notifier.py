import os
import subprocess
import time
import threading
import json
import urllib.request
import tkinter as tk
import pystray
from PIL import Image
import config_utils
import ctypes

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
_disable_auto_popup  = False

# Resolve icon path relative to this script's location
_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_TRAY_ICON_PATH = os.path.join(_SCRIPT_DIR, 'sys_img', 'icon_no_BG.png')
_STATE_FILE = os.path.join(_SCRIPT_DIR, 'notifier_state.json')

def load_notifier_state():
    """Load the last acknowledged file list."""
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {
                    'auto': set(data.get('last_ack_auto', data.get('last_ack_files', []))),
                    'upscale': set(data.get('last_ack_upscale', []))
                }
        except:
            pass
    return {'auto': set(), 'upscale': set()}

def save_notifier_state(auto_set, upscale_set):
    """Save the current directory files as acknowledged."""
    try:
        with open(_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'last_ack_auto': list(auto_set),
                'last_ack_upscale': list(upscale_set)
            }, f)
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
    """Check if the GemiPersona Streamlit app is alive on port 8501."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8501/healthz")
        with urllib.request.urlopen(req, timeout=1.5) as response:
            return response.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Shared helper: build and show a themed tkinter popup near the taskbar
# ---------------------------------------------------------------------------

def _build_popup(title_text, auto_pending, up_pending, auto_running, up_running, auto_folder=None, upscale_folder=None, auto_close_ms=None, on_manual_close=None):
    """Construct and run a dark-themed borderless popup window.

    Args:
        title_text     : string shown in the popup header
        auto_pending   : number of auto downloads
        up_pending     : number of upscaler downloads
        auto_running   : boolean indicating if automation is running
        up_running     : boolean indicating if upscaler is running
        auto_folder    : path for the Automation '📁 Download Folder' button
        upscale_folder : path for the Upscaler '📁 Upscale Folder' button
        auto_close_ms  : if set, window auto-dismisses after this many milliseconds
        on_manual_close: callback triggered when user explicitly clicks a button or X
    """
    C_BG      = '#0f1117'
    C_CARD    = '#1a1f2e'
    C_BORDER  = '#7c3aed'
    C_TEXT    = '#e2e8f0'
    C_MUTED   = '#8892a4'
    C_BTN_PRI = '#7c3aed'
    C_BTN_SEC = '#272d3d'

    FONT_TITLE = ('Segoe UI Semibold', 10)
    FONT_LABEL = ('Segoe UI', 9)
    FONT_VALUE = ('Segoe UI', 9)
    FONT_BTN   = ('Segoe UI Semibold', 9)

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    root.configure(bg=C_BORDER)

    def _manual_exit(callback=None):
        if on_manual_close:
            on_manual_close()
        if callback:
            callback()
        root.destroy()

    # 1-px accent border via outer frame
    outer = tk.Frame(root, bg=C_BORDER, padx=1, pady=1)
    outer.pack(fill='both', expand=True)

    body = tk.Frame(outer, bg=C_BG, padx=14, pady=10)
    body.pack(fill='both', expand=True)

    # -- Title bar --
    title_bar = tk.Frame(body, bg=C_BG)
    title_bar.pack(fill='x', pady=(0, 8))

    tk.Label(title_bar, text=title_text, bg=C_BG, fg=C_TEXT,
             font=FONT_TITLE).pack(side='left')

    close_lbl = tk.Label(title_bar, text='  ✕  ', bg=C_BG, fg=C_MUTED,
                         font=('Segoe UI', 9), cursor='hand2')
    close_lbl.pack(side='right')
    close_lbl.bind('<Button-1>', lambda e: _manual_exit())
    close_lbl.bind('<Enter>',    lambda e: close_lbl.config(fg=C_TEXT))
    close_lbl.bind('<Leave>',    lambda e: close_lbl.config(fg=C_MUTED))

    # -- Separator --
    tk.Frame(body, bg=C_BORDER, height=1).pack(fill='x', pady=(0, 8))

    # -- Data card --
    card = tk.Frame(body, bg=C_CARD, padx=12, pady=12)
    card.pack(fill='x')

    # Two columns: Left (Auto), Right (Upscaler)
    left_col = tk.Frame(card, bg=C_CARD)
    left_col.pack(side='left', expand=True, fill='both')

    right_col = tk.Frame(card, bg=C_CARD)
    right_col.pack(side='right', expand=True, fill='both')

    # Auto Section
    tk.Label(left_col, text="Auto", bg=C_CARD, fg=C_TEXT if auto_running else C_MUTED, font=('Segoe UI', 10)).pack()
    tk.Label(left_col, text=str(auto_pending), bg=C_CARD, fg='#ff5555' if (auto_pending > 0 and auto_running) else (C_TEXT if auto_running else C_MUTED), font=('Segoe UI Bold', 24)).pack()

    # Upscaler Section
    tk.Label(right_col, text="Upscaler", bg=C_CARD, fg=C_TEXT if up_running else C_MUTED, font=('Segoe UI', 10)).pack()
    tk.Label(right_col, text=str(up_pending), bg=C_CARD, fg='#ff5555' if (up_pending > 0 and up_running) else (C_TEXT if up_running else C_MUTED), font=('Segoe UI Bold', 24)).pack()

    # -- Action buttons row 1 (Folders) --
    folder_bar = tk.Frame(body, bg=C_BG)
    folder_bar.pack(fill='x', pady=(10, 0))

    def _open_auto():
        if auto_folder:
            open_file_foreground(auto_folder)
        _manual_exit()

    def _open_upscale():
        if upscale_folder:
            open_file_foreground(upscale_folder)
        _manual_exit()

    has_folder_btn = False
    if auto_folder:
        tk.Button(
            folder_bar, text='📁 Download Folder', relief='flat',
            bg=C_BTN_SEC, fg=C_TEXT, font=FONT_BTN,
            padx=10, pady=4, cursor='hand2',
            activebackground='#363d52', activeforeground=C_TEXT,
            command=_open_auto
        ).pack(side='left', expand=True, fill='x', padx=(0, 4))
        has_folder_btn = True

    if upscale_folder:
        tk.Button(
            folder_bar, text='📁 Upscale Folder', relief='flat',
            bg=C_BTN_SEC, fg=C_TEXT, font=FONT_BTN,
            padx=10, pady=4, cursor='hand2',
            activebackground='#363d52', activeforeground=C_TEXT,
            command=_open_upscale
        ).pack(side='left', expand=True, fill='x', padx=(4 if has_folder_btn else 0, 0))
        has_folder_btn = True

    if not has_folder_btn:
        folder_bar.destroy()

    # -- Action buttons row 2 (Dismiss & Open GemiPersona) --
    btn_bar = tk.Frame(body, bg=C_BG)
    btn_bar.pack(fill='x', pady=(8 if has_folder_btn else 10, 0))

    tk.Button(
        btn_bar, text='Dismiss', relief='flat',
        bg=C_BTN_SEC, fg=C_MUTED, font=FONT_BTN,
        padx=10, pady=4, cursor='hand2',
        activebackground='#363d52', activeforeground=C_TEXT,
        command=_manual_exit
    ).pack(side='left', expand=True, fill='x', padx=(0, 4))

    def _open_gemipersona():
        run_bat = os.path.join(_SCRIPT_DIR, "run.bat")
        if os.path.exists(run_bat):
            subprocess.Popen(
                ["cmd", "/c", "start", "", run_bat],
                shell=False,
                close_fds=True
            )
        _manual_exit()

    running = is_gemipersona_running()

    if running:
        gp_bg = C_BTN_SEC
        gp_fg = '#4a5568'
        gp_cursor = 'arrow'
        gp_cmd = lambda: None
    else:
        gp_bg = C_BTN_PRI
        gp_fg = '#ffffff'
        gp_cursor = 'hand2'
        gp_cmd = _open_gemipersona

    tk.Button(
        btn_bar, text='Open GemiPersona', relief='flat',
        bg=gp_bg, fg=gp_fg, font=FONT_BTN,
        padx=10, pady=4, cursor=gp_cursor,
        activebackground='#6d28d9' if not running else gp_bg,
        activeforeground='#ffffff' if not running else gp_fg,
        command=gp_cmd
    ).pack(side='left', expand=True, fill='x', padx=(4, 0))

    # -- Checkbox row (Disable auto popup) --
    chk_bar = tk.Frame(body, bg=C_BG)
    chk_bar.pack(fill='x', pady=(8, 0))

    chk_var = tk.BooleanVar(value=_disable_auto_popup)
    
    def on_chk_toggle():
        global _disable_auto_popup
        _disable_auto_popup = chk_var.get()

    tk.Checkbutton(
        chk_bar, text="Do not show popups automatically",
        variable=chk_var, command=on_chk_toggle,
        bg=C_BG, fg=C_MUTED, selectcolor=C_CARD,
        activebackground=C_BG, activeforeground=C_TEXT,
        font=('Segoe UI', 8), cursor='hand2'
    ).pack(side='left')

    # -- Position: bottom-right, above taskbar --
    root.update_idletasks()
    win_w = root.winfo_reqwidth()
    win_h = root.winfo_reqheight()
    scr_w = root.winfo_screenwidth()
    scr_h = root.winfo_screenheight()
    x_pos = scr_w - win_w - 20
    y_pos = scr_h - win_h - 55     # 55px clears standard taskbar
    root.geometry(f'{win_w}x{win_h}+{x_pos}+{y_pos}')
    root.deiconify()

    root.bind('<Escape>', lambda e: _manual_exit())

    if auto_close_ms:
        # Note: auto-close uses root.destroy() directly, bypassing _manual_exit's callback
        root.after(auto_close_ms, lambda: root.destroy() if root.winfo_exists() else None)

    root.mainloop()


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
        
        def on_manual_ack():
            auto_set = set(os.listdir(current_dir_display)) if current_dir_display and os.path.exists(current_dir_display) else set()
            up_set = set(os.listdir(current_upscale_dir)) if current_upscale_dir and os.path.exists(current_upscale_dir) else set()
            save_notifier_state(auto_set, up_set)

        _build_popup(
            "GemiPersona Notifier", 
            auto_pending=auto_pending, up_pending=up_pending,
            auto_running=auto_running, up_running=up_running,
            auto_folder=current_dir_display, upscale_folder=current_upscale_dir, 
            on_manual_close=on_manual_ack
        )

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

        def on_manual_ack():
            save_notifier_state(current_auto_files, current_up_files)

        _build_popup(
            f"GemiPersona — {count} New Image{'s' if count > 1 else ''}",
            auto_pending=total_auto_pending, up_pending=total_up_pending,
            auto_running=auto_running, up_running=up_running,
            auto_folder=current_auto_dir,
            upscale_folder=current_up_dir,
            auto_close_ms=8000,          # Auto-dismiss after 8 seconds
            on_manual_close=on_manual_ack
        )

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
                    if not _disable_auto_popup:
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
    global app_running
    app_running = False
    icon.stop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    global tray_icon
    monitor_thread = threading.Thread(target=monitor_directory, daemon=True)
    monitor_thread.start()

    icon_img = Image.open(_TRAY_ICON_PATH)
    menu = pystray.Menu(
        pystray.MenuItem("Show Status", show_status, default=True),
        pystray.MenuItem("Quit", quit_app)
    )

    tray_icon = pystray.Icon("GemiPersonaNotifier", icon_img, "GemiPersona Notifier", menu)
    tray_icon.run()


if __name__ == '__main__':
    main()
