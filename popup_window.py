import os
import sys
import json
import tkinter as tk
import threading
import subprocess
import ctypes
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_FILE = os.path.join(_SCRIPT_DIR, 'notifier_state.json')

def save_notifier_state(auto_set, upscale_set, disable_auto=None):
    try:
        data = {}
        if os.path.exists(_STATE_FILE):
            with open(_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        data['last_ack_auto'] = list(auto_set)
        data['last_ack_upscale'] = list(upscale_set)
        if disable_auto is not None:
            data['disable_auto_popup'] = disable_auto
            
        with open(_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except:
        pass

def open_file_foreground(file_path):
    abs_path = os.path.abspath(file_path)
    if os.name == 'nt':
        try:
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

def is_gemipersona_running():
    import socket
    try:
        with socket.create_connection(('127.0.0.1', 8501), timeout=0.5):
            return True
    except OSError:
        return False

def _show_monitor_window():
    hw_script = os.path.join(_SCRIPT_DIR, 'monitor_window.py')
    if not os.path.exists(hw_script):
        return

    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if not os.path.exists(pythonw):
        pythonw = sys.executable

    try:
        subprocess.Popen([pythonw, hw_script], cwd=_SCRIPT_DIR, close_fds=True)
    except:
        pass

def main():
    if len(sys.argv) < 2:
        return
    
    try:
        data = json.loads(sys.argv[1])
    except:
        return

    title_text = data.get("title_text", "")
    auto_pending = data.get("auto_pending", 0)
    up_pending = data.get("up_pending", 0)
    auto_running = data.get("auto_running", False)
    up_running = data.get("up_running", False)
    auto_folder = data.get("auto_folder")
    upscale_folder = data.get("upscale_folder")
    auto_close_ms = data.get("auto_close_ms")

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

    def on_manual_ack():
        auto_set = set(os.listdir(auto_folder)) if auto_folder and os.path.exists(auto_folder) else set()
        up_set = set(os.listdir(upscale_folder)) if upscale_folder and os.path.exists(upscale_folder) else set()
        save_notifier_state(auto_set, up_set)

    def _manual_exit():
        on_manual_ack()
        root.destroy()

    outer = tk.Frame(root, bg=C_BORDER, padx=1, pady=1)
    outer.pack(fill='both', expand=True)

    body = tk.Frame(outer, bg=C_BG, padx=14, pady=10)
    body.pack(fill='both', expand=True)

    title_bar = tk.Frame(body, bg=C_BG)
    title_bar.pack(fill='x', pady=(0, 8))

    tk.Label(title_bar, text=title_text, bg=C_BG, fg=C_TEXT, font=FONT_TITLE).pack(side='left')

    close_lbl = tk.Label(title_bar, text='  ✕  ', bg=C_BG, fg=C_MUTED, font=('Segoe UI', 9), cursor='hand2')
    close_lbl.pack(side='right')
    close_lbl.bind('<Button-1>', lambda e: _manual_exit())
    close_lbl.bind('<Enter>',    lambda e: close_lbl.config(fg=C_TEXT))
    close_lbl.bind('<Leave>',    lambda e: close_lbl.config(fg=C_MUTED))

    tk.Frame(body, bg=C_BORDER, height=1).pack(fill='x', pady=(0, 8))

    card = tk.Frame(body, bg=C_CARD, padx=12, pady=12)
    card.pack(fill='x')

    left_col = tk.Frame(card, bg=C_CARD)
    left_col.pack(side='left', expand=True, fill='both')

    right_col = tk.Frame(card, bg=C_CARD)
    right_col.pack(side='right', expand=True, fill='both')

    tk.Label(left_col, text="Auto", bg=C_CARD, fg=C_TEXT if auto_running else C_MUTED, font=('Segoe UI', 10)).pack()
    tk.Label(left_col, text=str(auto_pending), bg=C_CARD, fg='#ff5555' if (auto_pending > 0 and auto_running) else (C_TEXT if auto_running else C_MUTED), font=('Segoe UI Bold', 24)).pack()

    tk.Label(right_col, text="Upscaler", bg=C_CARD, fg=C_TEXT if up_running else C_MUTED, font=('Segoe UI', 10)).pack()
    tk.Label(right_col, text=str(up_pending), bg=C_CARD, fg='#ff5555' if (up_pending > 0 and up_running) else (C_TEXT if up_running else C_MUTED), font=('Segoe UI Bold', 24)).pack()

    folder_bar = tk.Frame(body, bg=C_BG)
    folder_bar.pack(fill='x', pady=(10, 0))

    def _open_auto():
        if auto_folder: open_file_foreground(auto_folder)
        _manual_exit()

    def _open_upscale():
        if upscale_folder: open_file_foreground(upscale_folder)
        _manual_exit()

    has_folder_btn = False
    if auto_folder:
        tk.Button(folder_bar, text='📁 Download Folder', relief='flat', bg=C_BTN_SEC, fg=C_TEXT, font=FONT_BTN, padx=10, pady=4, cursor='hand2', activebackground='#363d52', activeforeground=C_TEXT, command=_open_auto).pack(side='left', expand=True, fill='x', padx=(0, 4))
        has_folder_btn = True

    if upscale_folder:
        tk.Button(folder_bar, text='📁 Upscale Folder', relief='flat', bg=C_BTN_SEC, fg=C_TEXT, font=FONT_BTN, padx=10, pady=4, cursor='hand2', activebackground='#363d52', activeforeground=C_TEXT, command=_open_upscale).pack(side='left', expand=True, fill='x', padx=(4 if has_folder_btn else 0, 0))
        has_folder_btn = True

    if not has_folder_btn:
        folder_bar.destroy()

    btn_bar = tk.Frame(body, bg=C_BG)
    btn_bar.pack(fill='x', pady=(8 if has_folder_btn else 10, 0))

    tk.Button(btn_bar, text='Dismiss', relief='flat', bg=C_BTN_SEC, fg=C_MUTED, font=FONT_BTN, padx=10, pady=4, cursor='hand2', activebackground='#363d52', activeforeground=C_TEXT, command=_manual_exit).pack(side='left', expand=True, fill='x', padx=(0, 4))

    tk.Button(btn_bar, text='📊 Monitor', relief='flat', bg=C_BTN_SEC, fg='#a0c4ff', font=FONT_BTN, padx=10, pady=4, cursor='hand2', activebackground='#363d52', activeforeground=C_TEXT, command=_show_monitor_window).pack(side='left', expand=True, fill='x', padx=(0, 4))

    def _open_gemipersona():
        run_bat = os.path.join(_SCRIPT_DIR, "run.bat")
        if os.path.exists(run_bat):
            subprocess.Popen(["cmd", "/c", "start", "", run_bat], shell=False, close_fds=True)
        _manual_exit()

    running = is_gemipersona_running()
    gp_btn = tk.Button(btn_bar, text='Open GemiPersona', relief='flat', bg=C_BTN_SEC, fg=C_MUTED if running else C_TEXT, font=FONT_BTN, padx=10, pady=4, cursor='arrow' if running else 'hand2', activebackground=C_BTN_SEC, activeforeground=C_TEXT, command=(lambda: None) if running else _open_gemipersona, state='disabled' if running else 'normal')
    gp_btn.pack(side='left', expand=True, fill='x', padx=(4, 0))

    # -- Checkbox row (Disable auto popup) --
    chk_bar = tk.Frame(body, bg=C_BG)
    chk_bar.pack(fill='x', pady=(8, 0))

    # Read current setting from state file
    _disable_auto_popup = False
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
                _disable_auto_popup = state_data.get('disable_auto_popup', False)
        except:
            pass

    chk_var = tk.BooleanVar(value=_disable_auto_popup)
    
    def on_chk_toggle():
        auto_set = set(os.listdir(auto_folder)) if auto_folder and os.path.exists(auto_folder) else set()
        up_set = set(os.listdir(upscale_folder)) if upscale_folder and os.path.exists(upscale_folder) else set()
        save_notifier_state(auto_set, up_set, disable_auto=chk_var.get())

    tk.Checkbutton(
        chk_bar, text="Do not show popups automatically",
        variable=chk_var, command=on_chk_toggle,
        bg=C_BG, fg=C_MUTED, selectcolor=C_CARD,
        activebackground=C_BG, activeforeground=C_TEXT,
        font=('Segoe UI', 8), cursor='hand2'
    ).pack(side='left')

    root.update_idletasks()
    win_w = root.winfo_reqwidth()
    win_h = root.winfo_reqheight()
    scr_w = root.winfo_screenwidth()
    scr_h = root.winfo_screenheight()
    x_pos = scr_w - win_w - 20
    y_pos = scr_h - win_h - 55
    root.geometry(f'{win_w}x{win_h}+{x_pos}+{y_pos}')
    root.deiconify()

    root.bind('<Escape>', lambda e: _manual_exit())

    if auto_close_ms:
        root.after(auto_close_ms, lambda: root.destroy() if root.winfo_exists() else None)

    _gp_btn_ref = [gp_btn]
    def _poll_gp_btn():
        try:
            if not root.winfo_exists(): return
            btn = _gp_btn_ref[0]
            if btn:
                alive = is_gemipersona_running()
                if alive:
                    btn.config(state='disabled', fg=C_MUTED, cursor='arrow', activebackground=C_BTN_SEC, command=lambda: None)
                else:
                    btn.config(state='normal', fg=C_TEXT, cursor='hand2', activebackground=C_BTN_SEC, command=_open_gemipersona)
            root.after(3000, _poll_gp_btn)
        except: pass

    root.after(3000, _poll_gp_btn)
    root.mainloop()

if __name__ == '__main__':
    main()
