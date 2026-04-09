import os
import time
import threading
import json
import urllib.request
import tkinter as tk
import pystray
from PIL import Image
import config_utils

app_running = True
current_dir_display = ""
tray_icon = None
_status_popup_open   = False
_download_popup_open = False

# Resolve icon path relative to this script's location
_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_TRAY_ICON_PATH = os.path.join(_SCRIPT_DIR, 'sys_img', 'icon_no_BG.png')


def get_automation_stats():
    """Fetch full automation stats from the engine service."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/browser/automation/stats")
        with urllib.request.urlopen(req, timeout=1.5) as response:
            return json.loads(response.read().decode())
    except Exception:
        return {}


def is_gemipersona_running():
    """Check if GemiPersona engine or Streamlit app is alive."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/health")
        with urllib.request.urlopen(req, timeout=1.0) as response:
            return response.status == 200
    except Exception:
        pass
    stats = get_automation_stats()
    if stats:
        return True
    try:
        req = urllib.request.Request("http://127.0.0.1:8501/healthz")
        with urllib.request.urlopen(req, timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Shared helper: build and show a themed tkinter popup near the taskbar
# ---------------------------------------------------------------------------

def _build_popup(title_text, rows, folder_path, auto_close_ms=None):
    """Construct and run a dark-themed borderless popup window.

    Args:
        title_text   : string shown in the popup header
        rows         : list of (label, value) tuples for the data card
        folder_path  : path for the 'Open Folder' button, or None to hide it
        auto_close_ms: if set, window auto-dismisses after this many milliseconds
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
    close_lbl.bind('<Button-1>', lambda e: root.destroy())
    close_lbl.bind('<Enter>',    lambda e: close_lbl.config(fg=C_TEXT))
    close_lbl.bind('<Leave>',    lambda e: close_lbl.config(fg=C_MUTED))

    # -- Separator --
    tk.Frame(body, bg=C_BORDER, height=1).pack(fill='x', pady=(0, 8))

    # -- Data card --
    card = tk.Frame(body, bg=C_CARD, padx=12, pady=8)
    card.pack(fill='x')

    for label, value in rows:
        row_frame = tk.Frame(card, bg=C_CARD)
        row_frame.pack(fill='x', pady=2)
        tk.Label(row_frame, text=label, width=8, anchor='w',
                 bg=C_CARD, fg=C_MUTED, font=FONT_LABEL).pack(side='left')
        tk.Label(row_frame, text=value, anchor='w',
                 bg=C_CARD, fg=C_TEXT, font=FONT_VALUE,
                 wraplength=260, justify='left').pack(side='left', fill='x', expand=True)

    # -- Button row --
    btn_bar = tk.Frame(body, bg=C_BG)
    btn_bar.pack(fill='x', pady=(10, 0))

    def _open_folder():
        if folder_path:
            os.startfile(folder_path)
        root.destroy()

    if folder_path:
        tk.Button(
            btn_bar, text='Open Folder', relief='flat',
            bg=C_BTN_PRI, fg='#ffffff', font=FONT_BTN,
            padx=10, pady=4, cursor='hand2',
            activebackground='#6d28d9', activeforeground='#ffffff',
            command=_open_folder
        ).pack(side='left')

    tk.Button(
        btn_bar, text='Dismiss', relief='flat',
        bg=C_BTN_SEC, fg=C_MUTED, font=FONT_BTN,
        padx=10, pady=4, cursor='hand2',
        activebackground='#363d52', activeforeground=C_TEXT,
        command=root.destroy
    ).pack(side='left', padx=(8 if folder_path else 0, 0))

    def _open_gemipersona():
        run_bat = os.path.join(_SCRIPT_DIR, "run.bat")
        if os.path.exists(run_bat):
            os.startfile(run_bat)
        root.destroy()

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
    ).pack(side='left', padx=(8, 0))

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

    root.bind('<Escape>', lambda e: root.destroy())

    if auto_close_ms:
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
        if not current_dir_display or current_dir_display == "Not set or not found":
            rows = [
                ("Status",    "Initializing..."),
                ("Directory", "Not set or not found"),
            ]
            folder_path = None
        else:
            stats       = get_automation_stats()
            active_acct = config_utils.load_config().get('active_user', 'N/A') or 'N/A'
            rows = [
                ("Account", active_acct),
                ("State",   "Running" if stats.get('is_running', False) else "Stopped"),
                ("Cycle",   str(stats.get('cycles', 0))),
                ("Saved",   str(stats.get('successes', 0))),
                ("Refused", str(stats.get('refusals', 0))),
                ("Resets",  str(stats.get('resets', 0))),
                ("Path",    current_dir_display),
            ]
            folder_path = current_dir_display

        _build_popup("GemiPersona Notifier", rows, folder_path)

    finally:
        _status_popup_open = False


# ---------------------------------------------------------------------------
# New Downloads popup  (auto-triggered when new images are detected)
# ---------------------------------------------------------------------------

def _show_new_files_popup(image_files, active_account, l_state,
                          s_cycles, s_images, s_refused, s_resets, directory):
    """Show a new-download alert popup — bypasses Windows notification system entirely.
    Auto-dismisses after 8 seconds if the user takes no action.
    """
    global _download_popup_open
    if _download_popup_open:
        return
    _download_popup_open = True

    try:
        count   = len(image_files)
        preview = image_files[:5]
        extra   = count - len(preview)

        file_summary = '\n'.join(preview)
        if extra > 0:
            file_summary += f'\n...and {extra} more'

        rows = [
            ("Account", active_account),
            ("State",   l_state),
            ("Cycle",   str(s_cycles)),
            ("Saved",   str(s_images)),
            ("Refused", str(s_refused)),
            ("Resets",  str(s_resets)),
            ("New",     file_summary),
            ("Path",    directory),
        ]

        _build_popup(
            f"GemiPersona — {count} New Image{'s' if count > 1 else ''}",
            rows,
            folder_path=directory,
            auto_close_ms=8000          # Auto-dismiss after 8 seconds
        )

    finally:
        _download_popup_open = False


# ---------------------------------------------------------------------------
# Background monitor thread
# ---------------------------------------------------------------------------

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
            time.sleep(5)

            config  = config_utils.load_config()
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
            new_files     = current_files - last_files
            image_files   = [f for f in new_files
                             if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]

            if image_files:
                stats          = get_automation_stats()
                l_state        = "Running" if stats.get('is_running', False) else "Stopped"
                active_account = config.get('active_user', 'N/A') or 'N/A'
                s_cycles       = stats.get('cycles', 0)
                s_images       = stats.get('successes', 0)
                s_refused      = stats.get('refusals', 0)
                s_resets       = stats.get('resets', 0)

                # Launch tkinter popup in its own daemon thread (non-blocking)
                threading.Thread(
                    target=_show_new_files_popup,
                    args=(image_files, active_account, l_state,
                          s_cycles, s_images, s_refused, s_resets, current_dir),
                    daemon=True
                ).start()

            last_files = current_files

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
