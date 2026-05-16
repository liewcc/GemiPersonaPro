"""
monitor_window.py — Standalone Monitor window.

Launched as a SEPARATE PROCESS by image_notifier.py via subprocess.Popen
so that Tkinter's Tcl interpreter is completely isolated from the notifier
popup's Tk() instance.  This prevents the PopQuitMessage cross-contamination
that caused the monitor window to exit whenever the popup was dismissed.
"""

import os, sys, json, socket, subprocess, threading, tkinter as tk

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_FILE  = os.path.join(_SCRIPT_DIR, 'notifier_state.json')

# ── ensure project root is on sys.path ────────────────────────────────────────
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import config_utils


# ── helpers ────────────────────────────────────────────────────────────────────

def _load_notifier_state():
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {
                'auto':    set(data.get('last_ack_auto',   data.get('last_ack_files', []))),
                'upscale': set(data.get('last_ack_upscale', []))
            }
        except Exception:
            pass
    return {'auto': set(), 'upscale': set()}


def _is_gemipersona_running():
    """TCP connect — no HTTP, avoids ProactorPipe errors."""
    try:
        with socket.create_connection(('127.0.0.1', 8501), timeout=0.5):
            return True
    except OSError:
        return False


def _open_file_foreground(path):
    import ctypes
    abs_path = os.path.abspath(path)
    if os.name == 'nt':
        try:
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
            ctypes.windll.user32.AllowSetForegroundWindow(-1)
        except Exception:
            pass
        os.startfile(abs_path)
    else:
        if hasattr(os, 'startfile'):
            os.startfile(abs_path)
        else:
            opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
            subprocess.Popen([opener, abs_path])


def _fmt_dur(secs):
    secs = max(0, int(secs))
    h = secs // 3600; m = (secs % 3600) // 60; s = secs % 60
    if h > 0:  return f"{h}h {m:02d}m"
    if m > 0:  return f"{m}m {s:02d}s"
    return f"{s}s"


def _get_last_log_line():
    log_path = os.path.join(_SCRIPT_DIR, 'engine.log')
    try:
        if not os.path.exists(log_path):
            return f'[log not found: {log_path}]'
        with open(log_path, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return '[engine.log is empty]'
            chunk = min(size, 4096)
            f.seek(-chunk, 2)
            tail = f.read(chunk).decode('utf-8', errors='replace')
        lines = [l.strip() for l in tail.splitlines() if l.strip()]
        if not lines:
            return '[no recent log lines]'
        raw = lines[-1]
        if raw.startswith('{'):
            try:
                obj    = json.loads(raw)
                ev     = obj.get('event', '')
                msg    = obj.get('message', '')[:120]
                ts_raw = obj.get('ts', obj.get('timestamp', obj.get('time', '')))
                ts     = ts_raw.split('T')[-1][:8] if 'T' in ts_raw else ts_raw[:8]
                raw    = f'[{ts}] {ev}: {msg}' if (ts or ev) else msg
            except Exception:
                pass
        return raw[:160]
    except Exception as _e:
        return f'[log read error: {_e}]'


def _load_data():
    """Parse health log; return (detailed_list, cycles_list, stats_dict)."""
    try:
        import health_parser as hp
        _, detailed, _ = hp.parse_account_health(
            target_account="ALL_EVENTS", login_data=[])
        cycles = hp.parse_engine_cycles()
    except Exception as _e:
        return [], [], {'_error': str(_e)}

    stats = {'images': 0, 'refused': 0, 'reset': 0,
             'cycle_dur': '', 'account': 'N/A', 'is_running': False}
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

    for rec in detailed:
        acct = rec.get('account', '')
        if acct and acct.lower() not in ('unknown', ''):
            stats['account'] = acct
            break

    return detailed, cycles, stats


# ── main window ────────────────────────────────────────────────────────────────

def main():
    # Read folder paths from config (same source as monitor_directory)
    try:
        cfg = config_utils.load_config()
        auto_folder    = cfg.get('save_dir', '')
        upscale_folder = cfg.get('upscaler', {}).get('output_dir', '')
    except Exception:
        auto_folder = upscale_folder = ''

    # ── colour palette ───────────────────────────────────────────────────────
    C_BG     = '#0f1117'
    C_CARD   = '#1a1f2e'
    C_BORDER = '#7c3aed'
    C_TEXT   = '#e2e8f0'
    C_MUTED  = '#8892a4'
    C_SUB    = '#272d3d'

    STATUS_COLORS = {
        'Success': '#2ecc71',
        'Reject':  '#a0a0ff',
        'Reset':   '#f39c12',
        'Fail':    '#ff4444',
        'Ongoing': '#888888',
    }

    N_EVENTS = 60

    # ── draw chart ───────────────────────────────────────────────────────────
    def _draw_chart(canvas, data, cw, ch):
        canvas.delete('all')
        data = [r for r in data if r.get('status') != 'Ongoing']
        if not data:
            canvas.create_text(cw // 2, ch // 2,
                               text='No completed events recorded yet.',
                               fill=C_MUTED, font=('Segoe UI', 10))
            return
        import math
        PAD_L, PAD_R, PAD_T, PAD_B = 80, 18, 16, 32
        chart_w = cw - PAD_L - PAD_R
        chart_h = ch - PAD_T - PAD_B
        events = list(reversed(data[:N_EVENTS]))
        n = len(events)
        durations = []
        for r in events:
            try:    durations.append(max(0, float(r.get('health', '0s').replace('s', ''))))
            except: durations.append(0)
        max_dur = max(durations) if durations else 1
        if max_dur == 0: max_dur = 1
        log_max = math.log1p(max_dur)
        def _dur_to_y(dur):
            if log_max == 0: return PAD_T + chart_h
            ratio = math.log1p(max(dur, 0)) / log_max
            return PAD_T + chart_h - int(chart_h * ratio)
            
        spacing = chart_w / n
        
        # Draw alternating background segments for accounts/sessions
        _seg = 0
        _prev_si = None
        _prev_acct = None
        for i, rec in enumerate(events):
            si = rec.get('session_index')
            acct = str(rec.get('account', '')).lower()
            if _prev_si is not None and (si != _prev_si or acct != _prev_acct):
                _seg += 1
            _prev_si = si
            _prev_acct = acct
            if _seg % 2 == 1:
                x0 = PAD_L + i * spacing
                x1 = PAD_L + (i + 1) * spacing
                canvas.create_rectangle(x0, PAD_T, x1, PAD_T + chart_h, fill='#333f5c', outline='')

        GRIDLINE_VALS = [1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200]
        drawn_y = []
        for val in GRIDLINE_VALS:
            if val > max_dur * 1.05: break
            y_px = _dur_to_y(val)
            if any(abs(y_px - prev) < 12 for prev in drawn_y): continue
            drawn_y.append(y_px)
            canvas.create_line(PAD_L, y_px, PAD_L + chart_w, y_px, fill='#475569', width=1)
            canvas.create_text(PAD_L - 8, y_px, text=_fmt_dur(val),
                               fill=C_MUTED, font=('Segoe UI', 7), anchor='e')
        y_top = _dur_to_y(max_dur)
        if not any(abs(y_top - prev) < 12 for prev in drawn_y):
            canvas.create_line(PAD_L, y_top, PAD_L + chart_w, y_top, fill='#475569', width=1)
            canvas.create_text(PAD_L - 8, y_top, text=_fmt_dur(max_dur),
                               fill=C_MUTED, font=('Segoe UI', 7), anchor='e')
        bar_w   = max(2, chart_w / n - 1)
        spacing = chart_w / n
        for i, (rec, dur) in enumerate(zip(events, durations)):
            status = rec.get('status', 'Fail')
            color  = STATUS_COLORS.get(status, '#888888')
            y0 = _dur_to_y(max(dur, 0.5))
            y1 = PAD_T + chart_h
            x0 = PAD_L + i * spacing
            x1 = x0 + bar_w
            canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline='')
        canvas.create_line(PAD_L, PAD_T + chart_h, PAD_L + chart_w, PAD_T + chart_h,
                           fill=C_MUTED, width=1)
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
    win = tk.Tk()
    win.title('Monitor — GemiPersona')
    win.configure(bg=C_BORDER)
    win.resizable(False, False)
    win.attributes('-topmost', True)

    def _safe_report_exception(exc, val, tb):
        import traceback as _tb
        _tb.print_exception(exc, val, tb)
    win.report_callback_exception = _safe_report_exception

    outer = tk.Frame(win, bg=C_BORDER, padx=1, pady=1)
    outer.pack(fill='both', expand=True)
    body = tk.Frame(outer, bg=C_BG)
    body.pack(fill='both', expand=True)

    # title bar
    tbar = tk.Frame(body, bg=C_BG, padx=14, pady=8)
    tbar.pack(fill='x')
    tk.Label(tbar, text='📊  Monitor Analysis', bg=C_BG, fg=C_TEXT,
             font=('Segoe UI Semibold', 10)).pack(side='left')

    def _close():
        win.destroy()

    x_lbl = tk.Label(tbar, text='  ✕  ', bg=C_BG, fg=C_MUTED,
                     font=('Segoe UI', 9), cursor='hand2')
    x_lbl.pack(side='right')
    x_lbl.bind('<Button-1>', lambda e: _close())
    x_lbl.bind('<Enter>',    lambda e: x_lbl.config(fg=C_TEXT))
    x_lbl.bind('<Leave>',    lambda e: x_lbl.config(fg=C_MUTED))
    win.protocol('WM_DELETE_WINDOW', _close)
    win.bind('<Escape>', lambda e: _close())

    tk.Frame(body, bg=C_BORDER, height=1).pack(fill='x')

    # stats row
    stats_frame = tk.Frame(body, bg=C_BG, padx=14, pady=8)
    stats_frame.pack(fill='x')
    stat_labels = {}

    def _make_stat(parent, key, title):
        col = tk.Frame(parent, bg=C_CARD, padx=4, pady=8)
        col.pack(side='left', expand=True, fill='both', padx=(0, 6))
        tk.Label(col, text=title, bg=C_CARD, fg=C_MUTED,
                 font=('Segoe UI', 8)).pack()
        val_lbl = tk.Label(col, text='—', bg=C_CARD, fg=C_TEXT,
                           font=('Segoe UI Semibold', 15))
        val_lbl.pack()
        stat_labels[key] = val_lbl

    _make_stat(stats_frame, 'account',   '👤 Account')
    _make_stat(stats_frame, 'images',    '✅ Images')
    _make_stat(stats_frame, 'auto_new',  '📥 New Images')
    _make_stat(stats_frame, 'refused',   '🚫 Refused')
    _make_stat(stats_frame, 'reset',     '🔄 Reset')
    _make_stat(stats_frame, 'cycle_dur', '⏱ Cycle Duration')

    for w in stats_frame.winfo_children():
        w.pack_configure(padx=(0, 6))
    stats_frame.winfo_children()[-1].pack_configure(padx=0)

    # status badge
    badge_frame = tk.Frame(body, bg=C_BG, padx=14)
    badge_frame.pack(fill='x')
    status_badge = tk.Label(badge_frame, text='', bg=C_BG,
                            font=('Segoe UI Semibold', 8))
    status_badge.pack(side='left')

    # log line (fixed-size container clips overflow on right)
    _log_frame = tk.Frame(body, bg=C_BG, width=650, height=20)
    _log_frame.pack(fill='x', padx=14, pady=2)
    _log_frame.pack_propagate(False)
    log_line_lbl = tk.Label(_log_frame, text='reading log...', bg=C_BG, fg='#a8d8ff',
                            font=('Segoe UI', 9), anchor='w')
    log_line_lbl.pack(fill='both', expand=True)

    # chart
    CANVAS_W, CANVAS_H = 650, 180
    chart_canvas = tk.Canvas(body, width=CANVAS_W, height=CANVAS_H,
                             bg=C_CARD, highlightthickness=0)
    chart_canvas.pack(padx=14, pady=(4, 0))

    # buttons
    btn_frame = tk.Frame(body, bg=C_BG, padx=14, pady=10)
    btn_frame.pack(fill='x')

    _btn_style = dict(relief='flat', bg=C_SUB, fg=C_TEXT,
                      font=('Segoe UI Semibold', 9), padx=8, pady=4,
                      cursor='hand2', activebackground='#363d52',
                      activeforeground=C_TEXT)

    def _open_auto():
        if auto_folder and os.path.exists(auto_folder):
            _open_file_foreground(auto_folder)

    def _open_upscale():
        if upscale_folder and os.path.exists(upscale_folder):
            _open_file_foreground(upscale_folder)

    def _open_gemi():
        run_bat = os.path.join(_SCRIPT_DIR, 'run.bat')
        if os.path.exists(run_bat):
            subprocess.Popen(['cmd', '/c', 'start', '', run_bat],
                             shell=False, close_fds=True)

    tk.Button(btn_frame, text='📁 Download Folder',
              command=_open_auto, **_btn_style).pack(side='left', padx=(0, 6))
    tk.Button(btn_frame, text='📁 Upscale Folder',
              command=_open_upscale, **_btn_style).pack(side='left', padx=(0, 6))

    _gemi_running = _is_gemipersona_running()
    _gemi_btn = tk.Button(btn_frame, text='🌐 Open GemiPersona',
                          command=_open_gemi, **_btn_style)
    if _gemi_running:
        _gemi_btn.config(state='disabled', fg=C_MUTED, cursor='arrow')
    _gemi_btn.pack(side='left', padx=(0, 6))

    def _reset_new_images():
        last_ack = _load_notifier_state()
        if auto_folder and os.path.exists(auto_folder):
            last_ack['auto'] = set(os.listdir(auto_folder))
            try:
                with open(_STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump({
                        'last_ack_auto': list(last_ack['auto']),
                        'last_ack_upscale': list(last_ack.get('upscale', set()))
                    }, f)
            except Exception:
                pass
            if 'auto_new' in stat_labels:
                stat_labels['auto_new'].config(text='0', fg=C_TEXT)

    tk.Button(btn_frame, text='Reset New Images Count', relief='flat',
              bg=C_SUB, fg=C_TEXT, font=('Segoe UI Semibold', 9),
              padx=10, pady=4, cursor='hand2',
              activebackground='#363d52', activeforeground=C_TEXT,
              command=_reset_new_images).pack(side='left', padx=(0, 6))

    tk.Button(btn_frame, text='Close', relief='flat',
              bg=C_SUB, fg=C_MUTED, font=('Segoe UI Semibold', 9),
              padx=10, pady=4, cursor='hand2',
              activebackground='#363d52', activeforeground=C_TEXT,
              command=_close).pack(side='left')

    # ── polling loops ─────────────────────────────────────────────────────────
    # 所有阻塞 I/O（文件读取、socket 连接、log 解析）均在 daemon 线程中执行，
    # 仅通过 win.after(0, callback) 回调在 UI 线程更新控件，避免卡顿。

    def _apply_chart_data(detailed, cycles, stats):
        """在 UI 线程中将解析结果写入控件。"""
        try:
            if not win.winfo_exists():
                return
            if '_error' in stats:
                chart_canvas.delete('all')
                chart_canvas.create_text(
                    CANVAS_W // 2, CANVAS_H // 2,
                    text=f"Error loading data:\n{stats['_error']}",
                    fill='#ff6666', font=('Segoe UI', 9), justify='center')
                status_badge.config(text='⚠ Load Error', fg='#ff6666')
                return
            stat_labels['account'].config(text=stats.get('account', 'N/A'))
            stat_labels['images'].config(text=str(stats.get('images', 0)))

            auto_pending = 0
            try:
                last_ack = _load_notifier_state()
                if auto_folder and os.path.exists(auto_folder):
                    cur = set(os.listdir(auto_folder))
                    auto_pending = len([
                        f for f in (cur - last_ack.get('auto', set()))
                        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp4'))
                    ])
            except Exception:
                pass

            stat_labels['auto_new'].config(
                text=str(auto_pending),
                fg='#2ecc71' if auto_pending > 0 else C_TEXT)
            stat_labels['refused'].config(
                text=str(stats.get('refused', 0)),
                fg='#a0a0ff' if stats.get('refused', 0) > 0 else C_TEXT)
            stat_labels['reset'].config(
                text=str(stats.get('reset', 0)),
                fg='#f39c12' if stats.get('reset', 0) > 0 else C_TEXT)
            stat_labels['cycle_dur'].config(text=stats.get('cycle_dur', '—') or '—')
            if stats.get('is_running'):
                status_badge.config(text='● Running', fg='#2ecc71')
            else:
                status_badge.config(text='○ Stopped', fg=C_MUTED)
            _draw_chart(chart_canvas, detailed, CANVAS_W, CANVAS_H)
        except Exception:
            pass

    def _apply_log_data(line, alive):
        """在 UI 线程中将日志行与按钮状态写入控件。"""
        try:
            if not win.winfo_exists():
                return
            line = ''.join(c for c in line if 0x20 <= ord(c) <= 0xFFFF)
            line = line.split('\n')[0]
            log_line_lbl.config(text=line)
            if alive:
                _gemi_btn.config(state='disabled', fg=C_MUTED, cursor='arrow')
            else:
                _gemi_btn.config(state='normal', fg=C_TEXT, cursor='hand2')
        except Exception:
            pass

    def _poll_log():
        """每 1 秒轮询一次：I/O 在后台线程，UI 更新回调至主线程。"""
        def _worker():
            try:
                line  = _get_last_log_line()       # 文件 I/O — 后台线程
                alive = _is_gemipersona_running()  # socket  — 后台线程
            except Exception:
                line, alive = '[read error]', False
            try:
                if win.winfo_exists():
                    win.after(0, lambda: _apply_log_data(line, alive))
            except Exception:
                pass

        try:
            if not win.winfo_exists():
                return
            threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            pass
        finally:
            try:
                if win.winfo_exists():
                    win.after(1000, _poll_log)
            except Exception:
                pass

    def _poll_chart():
        """每 5 秒轮询一次：解析在后台线程，UI 更新回调至主线程。"""
        def _worker():
            try:
                detailed, cycles, stats = _load_data()  # 解析 log — 后台线程
            except Exception as e:
                detailed, cycles, stats = [], [], {'_error': str(e)}
            try:
                if win.winfo_exists():
                    win.after(0, lambda: _apply_chart_data(detailed, cycles, stats))
            except Exception:
                pass

        try:
            if not win.winfo_exists():
                return
            threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            pass
        finally:
            try:
                if win.winfo_exists():
                    win.after(5000, _poll_chart)
            except Exception:
                pass

    win.after(1, _poll_log)
    win.after(1, _poll_chart)

    # centre on screen
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    ww = win.winfo_reqwidth()
    wh = win.winfo_reqheight()
    win.geometry(f'{ww}x{wh}+{(sw - ww) // 2}+{(sh - wh) // 2}')
    win.deiconify()

    win.mainloop()


if __name__ == '__main__':
    main()
