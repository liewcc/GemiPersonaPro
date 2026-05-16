import os
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
_disable_auto_popup  = False

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
# Account Health standalone window  (pure tkinter, no matplotlib)
# ---------------------------------------------------------------------------

_health_window_open = False

def _show_health_window():
    """Open a standalone dark-themed tkinter window showing Account Health charts.
    Runs in its own thread + tk.Tk() — completely independent of any popup.
    Draws bar charts directly on a Canvas — zero extra dependencies.
    """
    global _health_window_open
    if _health_window_open:
        return
    _health_window_open = True
    try:
        _show_health_window_inner()
    except Exception as _e:
        import traceback
        print(f'[health window] fatal error: {_e}')
        traceback.print_exc()
    finally:
        _health_window_open = False


def _show_health_window_inner():

    # ── colour palette (matches notifier theme) ──────────────────────────────
    C_BG     = '#0f1117'
    C_CARD   = '#1a1f2e'
    C_BORDER = '#7c3aed'
    C_TEXT   = '#e2e8f0'
    C_MUTED  = '#8892a4'
    C_ACCENT = '#7c3aed'
    C_SUB    = '#272d3d'

    STATUS_COLORS = {
        'Success': '#2ecc71',
        'Reject':  '#a0a0ff',
        'Reset':   '#f39c12',
        'Fail':    '#ff4444',
        'Ongoing': '#888888',
    }

    N_EVENTS = 60   # how many recent events to plot

    # ── helpers ──────────────────────────────────────────────────────────────
    def _fmt_dur(secs):
        secs = max(0, int(secs))
        h = secs // 3600; m = (secs % 3600) // 60; s = secs % 60
        if h > 0:  return f"{h}h {m:02d}m"
        if m > 0:  return f"{m}m {s:02d}s"
        return f"{s}s"

    def _load_data():
        """Parse health log and return (detailed_list, cycles_list, stats_dict)."""
        try:
            import sys, traceback as _tb
            if _SCRIPT_DIR not in sys.path:
                sys.path.insert(0, _SCRIPT_DIR)
            import health_parser as hp
            _, detailed, _ = hp.parse_account_health(target_account="ALL_EVENTS", login_data=[])
            cycles = hp.parse_engine_cycles()
        except Exception as _e:
            print(f"[notifier health] _load_data failed: {_e}")
            import traceback; traceback.print_exc()
            return [], [], {'_error': str(_e)}

        # Compute aggregate stats from the last (running) cycle if available
        stats = {'images': 0, 'refused': 0, 'reset': 0, 'cycle_dur': '', 'account': 'N/A', 'is_running': False}
        if cycles:
            lc = cycles[-1]
            stats['images']     = lc.get('success_count', 0)
            stats['refused']    = lc.get('reject_count', 0)
            stats['reset']      = lc.get('reset_count', 0)
            stats['is_running'] = lc.get('is_running', False)
            try:
                from datetime import datetime
                s = lc.get('full_start_time', lc.get('start_time_str', ''))
                e = lc.get('stop_time_str', s)
                fmt_s = '%Y-%m-%d %H:%M:%S' if '-' in s else '%H:%M:%S'
                fmt_e = '%Y-%m-%d %H:%M:%S' if '-' in e else '%H:%M:%S'
                ds = (datetime.strptime(e, fmt_e) - datetime.strptime(s, fmt_s)).total_seconds()
                if ds < 0: ds += 86400
                stats['cycle_dur'] = _fmt_dur(ds)
            except Exception:
                stats['cycle_dur'] = ''

        # Grab active account from the most recent event
        for rec in detailed:
            acct = rec.get('account', '')
            if acct and acct.lower() not in ('unknown', ''):
                stats['account'] = acct
                break

        return detailed, cycles, stats

    # ── draw bar chart on canvas ──────────────────────────────────────────────
    def _draw_chart(canvas, data, canvas_w, canvas_h):
        canvas.delete('all')
        if not data:
            canvas.create_text(canvas_w // 2, canvas_h // 2,
                               text='No events recorded yet.', fill=C_MUTED,
                               font=('Segoe UI', 10))
            return

        import math
        PAD_L, PAD_R, PAD_T, PAD_B = 48, 18, 16, 32
        chart_w = canvas_w - PAD_L - PAD_R
        chart_h = canvas_h - PAD_T - PAD_B

        # Take last N events (data is newest-first → reverse for chronological)
        events = list(reversed(data[:N_EVENTS]))
        n = len(events)

        # Durations in seconds
        durations = []
        for r in events:
            try:    durations.append(max(0, float(r.get('health', '0s').replace('s', ''))))
            except: durations.append(0)

        max_dur = max(durations) if durations else 1
        if max_dur == 0: max_dur = 1

        log_max = math.log1p(max_dur)

        def _dur_to_y(dur):
            """Map duration (seconds) → canvas Y pixel using log1p scale."""
            if log_max == 0: return PAD_T + chart_h
            ratio = math.log1p(max(dur, 0)) / log_max
            return PAD_T + chart_h - int(chart_h * ratio)

        # ── Y-axis gridlines & labels (meaningful log-spaced breakpoints) ────
        GRIDLINE_VALS = [1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200]
        drawn_y = []
        for val in GRIDLINE_VALS:
            if val > max_dur * 1.05:
                break
            y_px = _dur_to_y(val)
            if any(abs(y_px - prev) < 12 for prev in drawn_y):
                continue
            drawn_y.append(y_px)
            canvas.create_line(PAD_L, y_px, PAD_L + chart_w, y_px,
                               fill='#1e2535', width=1)
            canvas.create_text(PAD_L - 4, y_px, text=_fmt_dur(val),
                               fill=C_MUTED, font=('Segoe UI', 7), anchor='e')
        # Always label the top (max)
        y_top = _dur_to_y(max_dur)
        if not any(abs(y_top - prev) < 12 for prev in drawn_y):
            canvas.create_line(PAD_L, y_top, PAD_L + chart_w, y_top,
                               fill='#1e2535', width=1)
            canvas.create_text(PAD_L - 4, y_top, text=_fmt_dur(max_dur),
                               fill=C_MUTED, font=('Segoe UI', 7), anchor='e')

        # ── bars ─────────────────────────────────────────────────────────────
        bar_w   = max(2, chart_w / n - 1)
        spacing = chart_w / n

        for i, (rec, dur) in enumerate(zip(events, durations)):
            status = rec.get('status', 'Fail')
            color  = STATUS_COLORS.get(status, '#888888')
            y0 = _dur_to_y(max(dur, 0.5))   # min 0.5s so bar always visible
            y1 = PAD_T + chart_h
            x0 = PAD_L + i * spacing
            x1 = x0 + bar_w
            canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline='')

        # ── X-axis baseline ──────────────────────────────────────────────────
        canvas.create_line(PAD_L, PAD_T + chart_h, PAD_L + chart_w, PAD_T + chart_h,
                           fill=C_MUTED, width=1)

        # ── legend ───────────────────────────────────────────────────────────
        legend_items = [('Success', '#2ecc71'), ('Refused', '#a0a0ff'),
                        ('Reset', '#f39c12'), ('Fail', '#ff4444')]
        lx = PAD_L
        ly = PAD_T + chart_h + 14
        for label, clr in legend_items:
            canvas.create_rectangle(lx, ly - 5, lx + 10, ly + 5, fill=clr, outline='')
            canvas.create_text(lx + 14, ly, text=label, fill=C_MUTED,
                               font=('Segoe UI', 7), anchor='w')
            lx += 68

    # ── build window ─────────────────────────────────────────────────────────
    win = tk.Tk()   # always standalone — runs in its own thread
    win.title('Account Health — GemiPersona')
    win.configure(bg=C_BORDER)
    win.resizable(False, False)
    win.attributes('-topmost', True)

    # 1-px border wrapper
    outer = tk.Frame(win, bg=C_BORDER, padx=1, pady=1)
    outer.pack(fill='both', expand=True)
    body = tk.Frame(outer, bg=C_BG)
    body.pack(fill='both', expand=True)

    # ── title bar ────────────────────────────────────────────────────────────
    tbar = tk.Frame(body, bg=C_BG, padx=14, pady=8)
    tbar.pack(fill='x')
    tk.Label(tbar, text='📊  Account Health Analysis', bg=C_BG, fg=C_TEXT,
             font=('Segoe UI Semibold', 10)).pack(side='left')
    def _close_health():
        global _health_window_open
        _health_window_open = False
        win.destroy()
    x_lbl = tk.Label(tbar, text='  ✕  ', bg=C_BG, fg=C_MUTED,
                     font=('Segoe UI', 9), cursor='hand2')
    x_lbl.pack(side='right')
    x_lbl.bind('<Button-1>', lambda e: _close_health())
    x_lbl.bind('<Enter>',    lambda e: x_lbl.config(fg=C_TEXT))
    x_lbl.bind('<Leave>',    lambda e: x_lbl.config(fg=C_MUTED))
    win.protocol('WM_DELETE_WINDOW', _close_health)
    win.bind('<Escape>', lambda e: _close_health())

    # separator
    tk.Frame(body, bg=C_BORDER, height=1).pack(fill='x')

    # ── stats row ────────────────────────────────────────────────────────────
    stats_frame = tk.Frame(body, bg=C_BG, padx=14, pady=8)
    stats_frame.pack(fill='x')

    stat_labels = {}   # key → (title_lbl, value_lbl)

    def _make_stat(parent, key, title):
        col = tk.Frame(parent, bg=C_CARD, padx=12, pady=8)
        col.pack(side='left', expand=True, fill='both', padx=(0, 6))
        tk.Label(col, text=title, bg=C_CARD, fg=C_MUTED,
                 font=('Segoe UI', 8)).pack()
        val_lbl = tk.Label(col, text='—', bg=C_CARD, fg=C_TEXT,
                           font=('Segoe UI Semibold', 15))
        val_lbl.pack()
        stat_labels[key] = val_lbl

    _make_stat(stats_frame, 'account',   '👤 Account')
    _make_stat(stats_frame, 'images',    '✅ Images')
    _make_stat(stats_frame, 'refused',   '🚫 Refused')
    _make_stat(stats_frame, 'reset',     '🔄 Reset')
    _make_stat(stats_frame, 'cycle_dur', '⏱ Cycle Duration')

    # fix last card: no right padding
    for w in stats_frame.winfo_children():
        w.pack_configure(padx=(0, 6))
    stats_frame.winfo_children()[-1].pack_configure(padx=0)

    # ── status badge ─────────────────────────────────────────────────────────
    badge_frame = tk.Frame(body, bg=C_BG, padx=14)
    badge_frame.pack(fill='x')
    status_badge = tk.Label(badge_frame, text='', bg=C_BG,
                            font=('Segoe UI Semibold', 8))
    status_badge.pack(side='left')

    # ── chart section label ───────────────────────────────────────────────────
    lbl_frame = tk.Frame(body, bg=C_BG, padx=14, pady=4)
    lbl_frame.pack(fill='x')
    tk.Label(lbl_frame, text=f'Loading Duration — Last {N_EVENTS} Events',
             bg=C_BG, fg=C_MUTED, font=('Segoe UI', 8)).pack(side='left')

    # ── chart canvas ─────────────────────────────────────────────────────────
    CANVAS_W, CANVAS_H = 580, 180
    chart_canvas = tk.Canvas(body, width=CANVAS_W, height=CANVAS_H,
                             bg=C_CARD, highlightthickness=0)
    chart_canvas.pack(padx=14, pady=(4, 0))

    # ── buttons ───────────────────────────────────────────────────────────────
    btn_frame = tk.Frame(body, bg=C_BG, padx=14, pady=10)
    btn_frame.pack(fill='x')

    def _refresh():
        detailed, cycles, stats = _load_data()
        # Show error in chart area if data loading failed
        if '_error' in stats:
            chart_canvas.delete('all')
            chart_canvas.create_text(
                CANVAS_W // 2, CANVAS_H // 2,
                text=f"Error loading data:\n{stats['_error']}",
                fill='#ff6666', font=('Segoe UI', 9), justify='center')
            status_badge.config(text='⚠ Load Error', fg='#ff6666')
            return
        # Update stat cards
        stat_labels['account'].config(text=stats.get('account', 'N/A'))
        stat_labels['images'].config(text=str(stats.get('images', 0)))
        stat_labels['refused'].config(
            text=str(stats.get('refused', 0)),
            fg='#a0a0ff' if stats.get('refused', 0) > 0 else C_TEXT)
        stat_labels['reset'].config(
            text=str(stats.get('reset', 0)),
            fg='#f39c12' if stats.get('reset', 0) > 0 else C_TEXT)
        stat_labels['cycle_dur'].config(text=stats.get('cycle_dur', '—') or '—')
        # Status badge
        if stats.get('is_running'):
            status_badge.config(text='● Running', fg='#2ecc71')
        else:
            status_badge.config(text='○ Stopped', fg=C_MUTED)
        # Redraw chart
        _draw_chart(chart_canvas, detailed, CANVAS_W, CANVAS_H)

    tk.Button(
        btn_frame, text='🔄 Refresh', relief='flat',
        bg=C_SUB, fg=C_TEXT, font=('Segoe UI Semibold', 9),
        padx=10, pady=4, cursor='hand2',
        activebackground='#363d52', activeforeground=C_TEXT,
        command=_refresh
    ).pack(side='left', padx=(0, 6))

    tk.Button(
        btn_frame, text='Close', relief='flat',
        bg=C_SUB, fg=C_MUTED, font=('Segoe UI Semibold', 9),
        padx=10, pady=4, cursor='hand2',
        activebackground='#363d52', activeforeground=C_TEXT,
        command=_close_health
    ).pack(side='left')

    # ── initial data load & auto-refresh ─────────────────────────────────────
    def _auto_refresh():
        try:
            if not _health_window_open or not win.winfo_exists():
                return
            _refresh()
            if _health_window_open and win.winfo_exists():
                win.after(5000, _auto_refresh)
        except Exception:
            pass  # Never let an after() callback crash the process

    # Override tkinter's default exception handler for this window:
    # without this, any exception inside an after() callback on pythonw.exe
    # calls sys.excepthook which can terminate the whole process silently.
    def _safe_report_exception(exc, val, tb):
        import traceback as _tb
        print(f'[health tkinter] suppressed exception: {val}')
        _tb.print_exception(exc, val, tb)
    win.report_callback_exception = _safe_report_exception

    _auto_refresh()

    # ── centre window on screen ──────────────────────────────────────────────
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    ww = win.winfo_reqwidth()
    wh = win.winfo_reqheight()
    win.geometry(f'{ww}x{wh}+{(sw - ww) // 2}+{(sh - wh) // 2}')
    win.deiconify()

    # Own the mainloop — this thread lives until the user closes the window
    win.mainloop()


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

    # -- Action buttons row 2 (Dismiss, Health, Open GemiPersona) --
    btn_bar = tk.Frame(body, bg=C_BG)
    btn_bar.pack(fill='x', pady=(8 if has_folder_btn else 10, 0))

    tk.Button(
        btn_bar, text='Dismiss', relief='flat',
        bg=C_BTN_SEC, fg=C_MUTED, font=FONT_BTN,
        padx=10, pady=4, cursor='hand2',
        activebackground='#363d52', activeforeground=C_TEXT,
        command=_manual_exit
    ).pack(side='left', expand=True, fill='x', padx=(0, 4))

    def _open_health():
        # Health runs completely independently in its own thread + tk.Tk().
        # The TclError bug (pady tuple) that originally caused silent failure
        # has been fixed — threading is now the correct and stable approach.
        threading.Thread(target=_show_health_window, daemon=True).start()

    tk.Button(
        btn_bar, text='📊 Health', relief='flat',
        bg=C_BTN_SEC, fg='#a0c4ff', font=FONT_BTN,
        padx=10, pady=4, cursor='hand2',
        activebackground='#363d52', activeforeground=C_TEXT,
        command=_open_health
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
    def show_health(icon, item):
        threading.Thread(target=_show_health_window, daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem("Show Status", show_status, default=True),
        pystray.MenuItem("Account Health", show_health),
        pystray.MenuItem("Quit", quit_app)
    )

    tray_icon = pystray.Icon("GemiPersonaNotifier", icon_img, "GemiPersona Notifier", menu)

    # Restart loop: if pystray exits unexpectedly, re-launch it.
    # A deliberate quit via quit_app() sets app_running=False first.
    while app_running:
        try:
            tray_icon.run()
        except Exception as _e:
            _logging.error(f'tray_icon.run() crashed: {_e}', exc_info=True)
            if not app_running:
                break
            time.sleep(3)   # brief pause before restarting the tray icon
            try:
                tray_icon = pystray.Icon("GemiPersonaNotifier", icon_img, "GemiPersona Notifier", menu)
            except Exception:
                break
        else:
            break   # clean exit (quit_app called)


if __name__ == '__main__':
    main()
