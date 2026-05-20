"""
monitor_window.py — Standalone Monitor window.

Launched as a SEPARATE PROCESS by image_notifier.py via subprocess.Popen
so that Tkinter's Tcl interpreter is completely isolated from the notifier
popup's Tk() instance.  This prevents the PopQuitMessage cross-contamination
that caused the monitor window to exit whenever the popup was dismissed.
"""

import os, sys, json, socket, subprocess, threading, tkinter as tk
from tkinter import ttk

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
                # Omit the "DEBUG" prefix to avoid confusion in the monitor display
                if ev and ev != 'DEBUG':
                    raw = f'[{ts}] {ev}: {msg}' if ts else f'{ev}: {msg}'
                else:
                    raw = f'[{ts}] {msg}' if ts else msg
            except Exception:
                pass
        return raw[:160]
    except Exception as _e:
        return f'[log read error: {_e}]'


_cached_detailed = []
_cached_cycles = []
_last_event_count = -1

def _count_events_tail():
    try:
        log_path = os.path.join(_SCRIPT_DIR, 'engine.log')
        if not os.path.exists(log_path): return 0
        fsize = os.path.getsize(log_path)
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            if fsize > 65536:
                f.seek(fsize - 65536)
                f.readline()
            count = 0
            for line in f:
                if 'SUCCESS' in line or 'REJECT' in line or 'RESET' in line or 'ACCOUNT_SWITCH' in line or 'START' in line or 'BOUNDARY' in line:
                    count += 1
            return count
    except Exception:
        return -1

def _load_data():
    global _cached_detailed, _cached_cycles, _last_event_count
    
    stats = {'images': 0, 'refused': 0, 'reset': 0, 'is_running': False, 'total_cycles': 1,
             'cycle_dur': '', 'account': 'N/A', 'acct_switch': '—', 'acct_images': 0, 'acct_refused': 0, 'acct_reset': 0}
             
    try:
        import requests
        resp = requests.get("http://127.0.0.1:8000/browser/automation/stats", timeout=1.0)
        if resp.status_code == 200:
            api_stats = resp.json()
            stats['images'] = int(api_stats.get('successes', 0))
            # Mirror Dashboard status bar exactly: cycles/successes/refusals/resets directly from API
            stats['refused'] = int(api_stats.get('refusals', 0))
            stats['reset'] = int(api_stats.get('resets', 0))
            stats['is_running'] = api_stats.get('is_running', False)
            acct = api_stats.get('current_account_id') or api_stats.get('account', '')
            if acct:
                stats['account'] = acct
            stats['acct_switch'] = api_stats.get('acct_switch', '—')
            stats['acct_images'] = int(api_stats.get('acct_successes', 0))
            stats['acct_refused'] = int(api_stats.get('acct_refusals', 0))
            stats['acct_reset'] = int(api_stats.get('acct_resets', 0))
            # 'cycles' is the engine's cycle counter; never use 'round' (that's per-image)
            cycles_val = api_stats.get('cycles')
            if cycles_val is not None:
                stats['total_cycles'] = int(cycles_val)
    except Exception:
        pass
        
    tail_count = _count_events_tail()
    if tail_count != _last_event_count or _last_event_count == -1:
        try:
            import health_parser as hp
            login_data = []
            try:
                with open(os.path.join(_SCRIPT_DIR, 'user_login_lookup.json'), 'r', encoding='utf-8') as f:
                    login_data = json.load(f)
            except: pass
            _, _cached_detailed, _ = hp.parse_account_health(target_account="ALL_EVENTS", login_data=login_data)
            _cached_cycles = hp.parse_engine_cycles()
            _last_event_count = tail_count
        except Exception as _e:
            return _cached_detailed, _cached_cycles, {"_error": str(_e)}

    if _cached_cycles:
        lc = _cached_cycles[-1]

        if stats["account"] == "N/A":
            stats["images"] = lc.get("success_count", 0)
            stats["refused"] = lc.get("reject_count", 0)
            stats["reset"] = lc.get("reset_count", 0)
            stats["is_running"] = lc.get("is_running", False)
            if stats["total_cycles"] == 1:
                stats["total_cycles"] = len(_cached_cycles)
            for rec in _cached_detailed:
                acct = rec.get("account", "")
                if acct and acct.lower() not in ("unknown", ""):
                    stats["account"] = acct
                    break

        try:
            from datetime import datetime
            s = lc.get("full_start_time", lc.get("start_time_str", ""))
            fmt_s = "%Y-%m-%d %H:%M:%S" if "-" in s else "%H:%M:%S"
            start_dt = datetime.strptime(s, fmt_s)
            if stats["is_running"] or _is_gemipersona_running():
                ds = (datetime.now() - start_dt).total_seconds()
            else:
                e = lc.get("stop_time_str", s)
                fmt_e = "%Y-%m-%d %H:%M:%S" if "-" in e else "%H:%M:%S"
                ds = (datetime.strptime(e, fmt_e) - start_dt).total_seconds()
            if ds < 0: ds += 86400
            stats["cycle_dur"] = _fmt_dur(ds)
        except Exception:
            pass

    # Always fill per-account stats from user_login_lookup.json
    if stats["account"] != "N/A":
        try:
            def _norm(v): return str(v or '').split('@')[0].lower().strip()
            acct_norm = _norm(stats["account"])
            with open(os.path.join(_SCRIPT_DIR, "user_login_lookup.json"), "r", encoding="utf-8") as f:
                login_data = json.load(f)
            for u in login_data:
                if _norm(u.get("username", "")) == acct_norm:
                    sw = u.get("last_switched_at", "—")
                    stats["acct_switch"] = sw.split(" ")[-1] if " " in sw else sw
                    if stats.get("acct_images", 0) == 0:
                        stats["acct_images"] = u.get("session_images", 0)
                    if stats.get("acct_refused", 0) == 0:
                        stats["acct_refused"] = u.get("session_refused", 0)
                    if stats.get("acct_reset", 0) == 0:
                        stats["acct_reset"] = u.get("session_resets", 0)
                    break
        except Exception:
            pass

    return _cached_detailed, _cached_cycles, stats


def _load_stats_data():
    try:
        path = os.path.join(_SCRIPT_DIR, 'reject_stat_log.json')
        if not os.path.exists(path):
            return []
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


# ── main window ────────────────────────────────────────────────────────────────

def main():
    # Read folder paths from config (same source as monitor_directory)
    try:
        cfg = config_utils.load_config()
        auto_folder    = cfg.get('save_dir', '')
        upscale_folder = cfg.get('upscaler', {}).get('output_dir', '')
    except Exception:
        auto_folder = upscale_folder = ''

    _PREFS_FILE = os.path.join(_SCRIPT_DIR, 'monitor_ui_prefs.json')
    try:
        with open(_PREFS_FILE, 'r', encoding='utf-8') as f:
            ui_prefs = json.load(f)
    except Exception:
        ui_prefs = {
            'scale_0': 'log',
            'scale_1': 'log',
            'scale_2': 'log',
            'perf_mode': 'images',
            'active_tab': 0
        }

    def _save_ui_prefs():
        try:
            with open(_PREFS_FILE, 'w', encoding='utf-8') as f:
                json.dump(ui_prefs, f)
        except: pass

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

    # ── draw chart ───────────────────────────────────────────────────────────
    def _draw_chart(canvas, data, cw, ch):
        canvas.delete('all')
        data = [r for r in data if r.get('status') != 'Ongoing']
        if not data:
            canvas.create_text(cw // 2, ch // 2,
                               text='No completed events recorded yet.',
                               fill=C_MUTED, font=('Microsoft YaHei UI', 10))
            return
        import math
        PAD_L, PAD_R, PAD_T, PAD_B = 55, 18, 16, 32
        chart_w = cw - PAD_L - PAD_R
        chart_h = ch - PAD_T - PAD_B
        N_EVENTS = max(30, int(chart_w / 7.5))
        events = list(reversed(data[:N_EVENTS]))
        n = len(events)
        durations = []
        for r in events:
            try:    durations.append(max(0, float(r.get('health', '0s').replace('s', ''))))
            except: durations.append(0)
        max_dur = max(durations) if durations else 1
        if max_dur == 0: max_dur = 1
        log_max = math.log1p(max_dur)
        is_log = (ui_prefs.get('scale_0', 'log') == 'log')
        def _dur_to_y(dur):
            if is_log:
                if log_max == 0: return PAD_T + chart_h
                ratio = math.log1p(max(dur, 0)) / log_max
            else:
                ratio = max(dur, 0) / max_dur
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
                               fill=C_MUTED, font=('Microsoft YaHei UI', 7), anchor='e')
        y_top = _dur_to_y(max_dur)
        if not any(abs(y_top - prev) < 12 for prev in drawn_y):
            canvas.create_line(PAD_L, y_top, PAD_L + chart_w, y_top, fill='#475569', width=1)
            canvas.create_text(PAD_L - 8, y_top, text=_fmt_dur(max_dur),
                               fill=C_MUTED, font=('Microsoft YaHei UI', 7), anchor='e')
        bar_w   = max(2, chart_w / n - 1)
        spacing = chart_w / n
        
        bars_info = []
        for i, (rec, dur) in enumerate(zip(events, durations)):
            status = rec.get('status', 'Fail')
            color  = STATUS_COLORS.get(status, '#888888')
            y0 = _dur_to_y(max(dur, 0.5))
            y1 = PAD_T + chart_h
            x0 = PAD_L + i * spacing
            x1 = x0 + bar_w
            canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline='')
            
            acct = str(rec.get('account', '')).split('@')[0]
            if not acct or acct.lower() == 'unknown': acct = 'Unknown'
            bars_info.append((x0, y0, x1, y1, acct, _fmt_dur(dur)))
            
        canvas.create_line(PAD_L, PAD_T + chart_h, PAD_L + chart_w, PAD_T + chart_h,
                           fill=C_MUTED, width=1)
        legend_items = [('Success', '#2ecc71'), ('Refused', '#a0a0ff'),
                        ('Reset', '#f39c12'), ('Fail', '#ff4444')]
        lx = PAD_L
        ly = PAD_T + chart_h + 14
        for label, clr in legend_items:
            canvas.create_rectangle(lx, ly - 5, lx + 10, ly + 5, fill=clr, outline='')
            canvas.create_text(lx + 14, ly, text=label, fill=C_MUTED,
                               font=('Microsoft YaHei UI', 7), anchor='w')
            lx += 68

        tooltip_bg = canvas.create_rectangle(0, 0, 0, 0, fill='#272d3d', outline='', state='hidden')
        tooltip = canvas.create_text(0, 0, text='', fill='#ffffff', font=('Microsoft YaHei UI Bold', 9), state='hidden', anchor='e')
        
        fixed_x = cw - 12
        fixed_y = PAD_T + chart_h + 14
        
        def _update_tooltip(x, y):
            for (x0, y0, x1, y1, acct, dur_str) in bars_info:
                if x0 <= x <= x1 and y0 <= y <= y1:
                    canvas.itemconfig(tooltip, text=f"{acct}  |  {dur_str}", state='normal')
                    canvas.coords(tooltip, fixed_x, fixed_y)
                    bbox = canvas.bbox(tooltip)
                    if bbox:
                        canvas.coords(tooltip_bg, bbox[0]-8, bbox[1]-4, bbox[2]+8, bbox[3]+4)
                        canvas.itemconfig(tooltip_bg, state='normal')
                        canvas.tag_raise(tooltip_bg)
                        canvas.tag_raise(tooltip)
                    return
            canvas.itemconfig(tooltip, state='hidden')
            canvas.itemconfig(tooltip_bg, state='hidden')
            
        def on_motion(event):
            canvas._last_x, canvas._last_y = event.x, event.y
            _update_tooltip(event.x, event.y)
            
        def on_leave(event):
            canvas._last_x, canvas._last_y = -1, -1
            canvas.itemconfig(tooltip, state='hidden')
            canvas.itemconfig(tooltip_bg, state='hidden')

        canvas.bind('<Motion>', on_motion)
        canvas.bind('<Leave>', on_leave)

        if getattr(canvas, '_last_x', -1) >= 0 and getattr(canvas, '_last_y', -1) >= 0:
            _update_tooltip(canvas._last_x, canvas._last_y)

    def _draw_stats_chart(canvas, data, cw, ch):
        canvas.delete('all')
        if not data:
            canvas.create_text(cw // 2, ch // 2,
                               text='No processing stats recorded yet.',
                               fill=C_MUTED, font=('Microsoft YaHei UI', 10))
            return
        import math
        PAD_L, PAD_R, PAD_T, PAD_B = 55, 18, 16, 32
        chart_w = cw - PAD_L - PAD_R
        chart_h = ch - PAD_T - PAD_B
        
        N_EVENTS = max(30, int(chart_w / 7.5))
        items = data[-N_EVENTS:]
        n = len(items)
        
        durations = [r.get('duration_sec', 0) for r in items]
        max_dur = max(durations) if durations else 1
        if max_dur == 0: max_dur = 1
        log_max = math.log1p(max_dur)
        is_log = (ui_prefs.get('scale_1', 'log') == 'log')
        
        def _dur_to_y(dur):
            if is_log:
                if log_max == 0: return PAD_T + chart_h
                ratio = math.log1p(max(dur, 0)) / log_max
            else:
                ratio = max(dur, 0) / max_dur
            return PAD_T + chart_h - int(chart_h * ratio)
            
        spacing = chart_w / n if n > 0 else chart_w
        bar_w = max(2, spacing - 1)
        
        GRIDLINE_VALS = [1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200]
        drawn_y = []
        for val in GRIDLINE_VALS:
            if val > max_dur * 1.05: break
            y_px = _dur_to_y(val)
            if any(abs(y_px - prev) < 12 for prev in drawn_y): continue
            drawn_y.append(y_px)
            canvas.create_line(PAD_L, y_px, PAD_L + chart_w, y_px, fill='#475569', width=1)
            canvas.create_text(PAD_L - 8, y_px, text=_fmt_dur(val),
                               fill=C_MUTED, font=('Microsoft YaHei UI', 7), anchor='e')
        y_top = _dur_to_y(max_dur)
        if not any(abs(y_top - prev) < 12 for prev in drawn_y):
            canvas.create_line(PAD_L, y_top, PAD_L + chart_w, y_top, fill='#475569', width=1)
            canvas.create_text(PAD_L - 8, y_top, text=_fmt_dur(max_dur),
                               fill=C_MUTED, font=('Microsoft YaHei UI', 7), anchor='e')
                               
        bars_info = []
        for i, (rec, dur) in enumerate(zip(items, durations)):
            x0 = PAD_L + i * spacing
            x1 = x0 + bar_w
            y0 = _dur_to_y(max(dur, 0.5))
            y1 = PAD_T + chart_h
            
            refused = rec.get('refused_count', 0)
            resets = rec.get('reset_count', 0)
            if resets > 0: color = '#1e3a8a'     # 深蓝色 (Reset)
            elif refused > 0: color = '#3b82f6'  # 中蓝色 (Refused)
            else: color = '#93c5fd'              # 浅蓝色 (Normal)
            
            canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline='')
            
            filename = str(rec.get('filename', ''))
            display_filename = filename.replace('.png', '').replace('.jpg', '')
            
            bars_info.append((x0, y0, x1, y1, display_filename, _fmt_dur(dur), refused, resets))
            
        canvas.create_line(PAD_L, PAD_T + chart_h, PAD_L + chart_w, PAD_T + chart_h, fill=C_MUTED, width=1)
        
        legend_items = [('Normal', '#93c5fd'), ('Refused', '#3b82f6'), ('Reset', '#1e3a8a')]
        lx = PAD_L
        ly = PAD_T + chart_h + 14
        for label, clr in legend_items:
            canvas.create_rectangle(lx, ly - 5, lx + 10, ly + 5, fill=clr, outline='')
            canvas.create_text(lx + 14, ly, text=label, fill=C_MUTED,
                               font=('Microsoft YaHei UI', 7), anchor='w')
            lx += 68

        tooltip_bg = canvas.create_rectangle(0, 0, 0, 0, fill='#272d3d', outline='', state='hidden')
        tooltip = canvas.create_text(0, 0, text='', fill='#ffffff', font=('Microsoft YaHei UI Bold', 9), state='hidden', anchor='e')
        
        fixed_x = cw - 12
        fixed_y = PAD_T + chart_h + 14
        
        def _update_tooltip(x, y):
            for (x0, y0, x1, y1, fname, dur_str, ref, res) in bars_info:
                if x0 <= x <= x1 and y0 <= y <= y1:
                    info_text = f"{fname}  |  {dur_str}  |  Refused: {ref}  |  Reset: {res}"
                    canvas.itemconfig(tooltip, text=info_text, state='normal')
                    canvas.coords(tooltip, fixed_x, fixed_y)
                    bbox = canvas.bbox(tooltip)
                    if bbox:
                        canvas.coords(tooltip_bg, bbox[0]-8, bbox[1]-4, bbox[2]+8, bbox[3]+4)
                        canvas.itemconfig(tooltip_bg, state='normal')
                        canvas.tag_raise(tooltip_bg)
                        canvas.tag_raise(tooltip)
                    return
            canvas.itemconfig(tooltip, state='hidden')
            canvas.itemconfig(tooltip_bg, state='hidden')
            
        def on_motion(event):
            canvas._last_x, canvas._last_y = event.x, event.y
            _update_tooltip(event.x, event.y)
            
        def on_leave(event):
            canvas._last_x, canvas._last_y = -1, -1
            canvas.itemconfig(tooltip, state='hidden')
            canvas.itemconfig(tooltip_bg, state='hidden')

        canvas.bind('<Motion>', on_motion)
        canvas.bind('<Leave>', on_leave)

        if getattr(canvas, '_last_x', -1) >= 0 and getattr(canvas, '_last_y', -1) >= 0:
            _update_tooltip(canvas._last_x, canvas._last_y)

    def _draw_perf_chart(canvas, detailed_data, cw, ch, mode='images'):
        canvas.delete('all')
        if not detailed_data:
            canvas.create_text(cw // 2, ch // 2,
                               text='No records yet.',
                               fill=C_MUTED, font=('Microsoft YaHei UI', 10))
            return

        import math
        stats = []
        for e in reversed(detailed_data):
            if e.get('status') == 'Ongoing': continue
            s_id = e.get("session_index")
            acct = str(e.get("account", "Unknown"))
            st_val = e.get("status", "")
            success_val = 1 if st_val == "Success" else 0
            try:    dur_val = max(0, float(e.get('health', '0s').replace('s', '')))
            except: dur_val = 0
            if stats and stats[-1]["session_index"] == s_id and stats[-1]["account"].lower() == acct.lower():
                stats[-1]["images"] += success_val
                stats[-1]["duration"] += dur_val
            else:
                stats.append({"session_index": s_id, "account": acct,
                              "images": success_val, "duration": dur_val})

        PAD_L, PAD_R, PAD_T, PAD_B = 55, 18, 16, 32
        chart_w = cw - PAD_L - PAD_R
        chart_h = ch - PAD_T - PAD_B
        N_EVENTS = max(30, int(chart_w / 7.5))
        view_stats = stats[-N_EVENTS:]
        n = len(view_stats)
        if n == 0: return

        is_log = (ui_prefs.get('scale_2', 'log') == 'log')

        if mode == 'time':
            values = [s["duration"] for s in view_stats]
            max_v = max(values) if values else 1
            if max_v == 0: max_v = 1
            log_max = math.log1p(max_v)
            def _v_to_y(v):
                if is_log:
                    if log_max == 0: return PAD_T + chart_h
                    ratio = math.log1p(max(v, 0)) / log_max
                else:
                    ratio = max(v, 0) / max_v
                return PAD_T + chart_h - int(chart_h * ratio)
            GRIDLINE_VALS = [1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200]
            drawn_y = []
            for val in GRIDLINE_VALS:
                if val > max_v * 1.05: break
                y_px = _v_to_y(val)
                if any(abs(y_px - prev) < 12 for prev in drawn_y): continue
                drawn_y.append(y_px)
                canvas.create_line(PAD_L, y_px, PAD_L + chart_w, y_px, fill='#475569', width=1)
                canvas.create_text(PAD_L - 8, y_px, text=_fmt_dur(val),
                                   fill=C_MUTED, font=('Microsoft YaHei UI', 7), anchor='e')
            y_top = _v_to_y(max_v)
            if not any(abs(y_top - prev) < 12 for prev in drawn_y):
                canvas.create_line(PAD_L, y_top, PAD_L + chart_w, y_top, fill='#475569', width=1)
                canvas.create_text(PAD_L - 8, y_top, text=_fmt_dur(max_v),
                                   fill=C_MUTED, font=('Microsoft YaHei UI', 7), anchor='e')
            bar_color_a, bar_color_b = '#7c3aed', '#a78bfa'
            legend_label = 'Session Duration'
        else:
            values = [s["images"] for s in view_stats]
            max_v = max(values) if values else 1
            if max_v == 0: max_v = 1
            log_max = math.log1p(max_v)
            def _v_to_y(v):
                if is_log:
                    if log_max == 0: return PAD_T + chart_h
                    ratio = math.log1p(max(v, 0)) / log_max
                else:
                    ratio = max(v, 0) / max_v
                return PAD_T + chart_h - int(chart_h * ratio)
            
            drawn_y = []
            if is_log:
                GRIDLINE_VALS = [1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200]
                for val in GRIDLINE_VALS:
                    if val > max_v * 1.05: break
                    y_px = _v_to_y(val)
                    if any(abs(y_px - prev) < 12 for prev in drawn_y): continue
                    drawn_y.append(y_px)
                    canvas.create_line(PAD_L, y_px, PAD_L + chart_w, y_px, fill='#475569', width=1)
                    canvas.create_text(PAD_L - 8, y_px, text=str(val),
                                       fill=C_MUTED, font=('Microsoft YaHei UI', 7), anchor='e')
                y_top = _v_to_y(max_v)
                if not any(abs(y_top - prev) < 12 for prev in drawn_y):
                    canvas.create_line(PAD_L, y_top, PAD_L + chart_w, y_top, fill='#475569', width=1)
                    canvas.create_text(PAD_L - 8, y_top, text=str(max_v),
                                       fill=C_MUTED, font=('Microsoft YaHei UI', 7), anchor='e')
            else:
                steps = 4
                for i in range(steps + 1):
                    val = int(max_v * i / steps)
                    y_px = _v_to_y(val)
                    if any(abs(y_px - prev) < 12 for prev in drawn_y): continue
                    drawn_y.append(y_px)
                    canvas.create_line(PAD_L, y_px, PAD_L + chart_w, y_px, fill='#475569', width=1)
                    canvas.create_text(PAD_L - 8, y_px, text=str(val),
                                       fill=C_MUTED, font=('Microsoft YaHei UI', 7), anchor='e')
            bar_color_a, bar_color_b = '#2ecc71', '#a0e6b5'
            legend_label = 'Images Downloaded'

        spacing = chart_w / n if n > 0 else chart_w
        bar_w = max(2, min(spacing - 2, 60))
        bars = []
        for i, s in enumerate(view_stats):
            x0 = PAD_L + i * spacing + (spacing - bar_w) / 2
            x1 = x0 + bar_w
            v = s["duration"] if mode == 'time' else s["images"]
            y0 = _v_to_y(max(v, 0.5 if mode == 'time' else 0))
            y1 = PAD_T + chart_h
            color = bar_color_a if i % 2 == 0 else bar_color_b
            if v > 0:
                canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline='')
            acct_display = s["account"].split('@')[0]
            bars.append((x0, PAD_T, x1, y1, acct_display, s["images"], s["duration"]))

        canvas.create_line(PAD_L, PAD_T + chart_h, PAD_L + chart_w, PAD_T + chart_h, fill=C_MUTED, width=1)
        lx, ly = PAD_L, PAD_T + chart_h + 14
        canvas.create_rectangle(lx, ly - 5, lx + 10, ly + 5, fill=bar_color_a, outline='')
        canvas.create_text(lx + 14, ly, text=legend_label, fill=C_MUTED,
                           font=('Microsoft YaHei UI Bold', 7), anchor='w')

        tooltip_bg = canvas.create_rectangle(0, 0, 0, 0, fill='#272d3d', outline='', state='hidden')
        tooltip = canvas.create_text(0, 0, text='', fill='#ffffff', font=('Microsoft YaHei UI Bold', 9), state='hidden', anchor='e')
        fixed_x = cw - 12
        fixed_y = PAD_T + chart_h + 14

        def _update_tooltip(x, y):
            for (x0, y0, x1, y1, acct, imgs, dur) in bars:
                if x0 <= x <= x1 and y0 <= y <= y1:
                    tip = (f"{acct}  |  {_fmt_dur(dur)}  |  Images: {imgs}"
                           if mode == 'time' else
                           f"{acct}  |  Images: {imgs}  |  Duration: {_fmt_dur(dur)}")
                    canvas.itemconfig(tooltip, text=tip, state='normal')
                    canvas.coords(tooltip, fixed_x, fixed_y)
                    bbox = canvas.bbox(tooltip)
                    if bbox:
                        canvas.coords(tooltip_bg, bbox[0]-8, bbox[1]-4, bbox[2]+8, bbox[3]+4)
                        canvas.itemconfig(tooltip_bg, state='normal')
                        canvas.tag_raise(tooltip_bg)
                        canvas.tag_raise(tooltip)
                    return
            canvas.itemconfig(tooltip, state='hidden')
            canvas.itemconfig(tooltip_bg, state='hidden')

        def on_motion(event):
            canvas._last_x, canvas._last_y = event.x, event.y
            _update_tooltip(event.x, event.y)

        def on_leave(event):
            canvas._last_x, canvas._last_y = -1, -1
            canvas.itemconfig(tooltip, state='hidden')
            canvas.itemconfig(tooltip_bg, state='hidden')

        canvas.bind('<Motion>', on_motion)
        canvas.bind('<Leave>', on_leave)
        if getattr(canvas, '_last_x', -1) >= 0 and getattr(canvas, '_last_y', -1) >= 0:
            _update_tooltip(canvas._last_x, canvas._last_y)

    # ── build window ─────────────────────────────────────────────────────────
    win = tk.Tk()
    win.title('GemiPersona Monitor')
    win.configure(bg=C_BORDER)
    win.resizable(False, False)
    win.attributes('-topmost', True)
    
    try:
        icon_path = os.path.join(_SCRIPT_DIR, 'sys_img', 'icon_no_BG.png')
        if os.path.exists(icon_path):
            img = tk.PhotoImage(file=icon_path)
            win.iconphoto(True, img)
    except Exception:
        pass

    def _safe_report_exception(exc, val, tb):
        import traceback as _tb
        _tb.print_exception(exc, val, tb)
    win.report_callback_exception = _safe_report_exception

    outer = tk.Frame(win, bg=C_BORDER, padx=1, pady=1)
    outer.pack(fill='both', expand=True)
    body = tk.Frame(outer, bg=C_BG)
    body.pack(fill='both', expand=True)

    def _close():
        win.destroy()

    win.protocol('WM_DELETE_WINDOW', _close)
    win.bind('<Escape>', lambda e: _close())

    # row 0: system status (compact one-line layout)
    sys_status_frame = tk.Frame(body, bg=C_BG, padx=14, pady=6)
    sys_status_frame.pack(fill='x')
    
    stat_labels = {}

    lbl_eng_title = tk.Label(sys_status_frame, text='Engine Service: ', bg=C_BG, fg=C_MUTED, font=('Microsoft YaHei UI Bold', 8))
    lbl_eng_title.pack(side='left')
    lbl_eng_val = tk.Label(sys_status_frame, text='—', bg=C_BG, fg=C_TEXT, font=('Microsoft YaHei UI Bold', 8))
    lbl_eng_val.pack(side='left')
    stat_labels['engine_status'] = lbl_eng_val

    tk.Label(sys_status_frame, text='  |  ', bg=C_BG, fg=C_SUB, font=('Microsoft YaHei UI Bold', 8)).pack(side='left')

    lbl_brw_title = tk.Label(sys_status_frame, text='Browser Engine: ', bg=C_BG, fg=C_MUTED, font=('Microsoft YaHei UI Bold', 8))
    lbl_brw_title.pack(side='left')
    lbl_brw_val = tk.Label(sys_status_frame, text='—', bg=C_BG, fg=C_TEXT, font=('Microsoft YaHei UI Bold', 8))
    lbl_brw_val.pack(side='left')
    stat_labels['browser_status'] = lbl_brw_val

    tk.Label(sys_status_frame, text='  |  ', bg=C_BG, fg=C_SUB, font=('Microsoft YaHei UI Bold', 8)).pack(side='left')

    lbl_cpu_title = tk.Label(sys_status_frame, text='CPU Usage: ', bg=C_BG, fg=C_MUTED, font=('Microsoft YaHei UI Bold', 8))
    lbl_cpu_title.pack(side='left')
    lbl_cpu_val = tk.Label(sys_status_frame, text='—', bg=C_BG, fg=C_TEXT, font=('Microsoft YaHei UI Bold', 8))
    lbl_cpu_val.pack(side='left')
    stat_labels['cpu_usage'] = lbl_cpu_val

    # row 1: cycle stats
    stats_frame1 = tk.Frame(body, bg=C_BG, padx=14, pady=4)
    stats_frame1.pack(fill='x')
    
    # row 2: account stats
    stats_frame2 = tk.Frame(body, bg=C_BG, padx=14, pady=4)
    stats_frame2.pack(fill='x')

    def _make_stat(parent, key, title):
        col = tk.Frame(parent, bg=C_CARD, padx=4, pady=6)
        col.pack(side='left', expand=True, fill='both', padx=(0, 6))
        tk.Label(col, text=title, bg=C_CARD, fg=C_MUTED,
                 font=('Microsoft YaHei UI', 8)).pack()
        val_lbl = tk.Label(col, text='—', bg=C_CARD, fg=C_TEXT,
                           font=('Microsoft YaHei UI Bold', 13))
        val_lbl.pack()
        stat_labels[key] = val_lbl

    _make_stat(stats_frame1, 'total_cycles', '🔄 Total Cycles')
    _make_stat(stats_frame1, 'cycle_dur',    '⏱ Cycle Duration')
    _make_stat(stats_frame1, 'images',       '✅ Total Images')
    _make_stat(stats_frame1, 'auto_new',     '📥 New Images')
    _make_stat(stats_frame1, 'refused',      '🚫 Total Refused')
    _make_stat(stats_frame1, 'reset',        '🔄 Total Reset')

    _make_stat(stats_frame2, 'account',      '👤 Account')
    _make_stat(stats_frame2, 'acct_switch',  '⏱ Switch At')
    _make_stat(stats_frame2, 'acct_images',  '🖼 Images')
    _make_stat(stats_frame2, 'acct_refused', '🚫 Refused')
    _make_stat(stats_frame2, 'acct_reset',   '🔄 Reset')

    for w in stats_frame1.winfo_children(): w.pack_configure(padx=(0, 6))
    if stats_frame1.winfo_children(): stats_frame1.winfo_children()[-1].pack_configure(padx=0)
    for w in stats_frame2.winfo_children(): w.pack_configure(padx=(0, 6))
    if stats_frame2.winfo_children(): stats_frame2.winfo_children()[-1].pack_configure(padx=0)

    # status badge
    badge_frame = tk.Frame(body, bg=C_BG, padx=14)
    badge_frame.pack(fill='x')
    status_badge = tk.Label(badge_frame, text='', bg=C_BG,
                            font=('Microsoft YaHei UI Bold', 8))
    status_badge.pack(side='left')

    # log line (fixed-size container clips overflow on right)
    _log_frame = tk.Frame(body, bg=C_BG, width=650, height=20)
    _log_frame.pack(fill='x', padx=14, pady=2)
    _log_frame.pack_propagate(False)
    log_line_lbl = tk.Label(_log_frame, text='reading log...', bg=C_BG, fg='#a8d8ff',
                            font=('Microsoft YaHei UI', 9), anchor='w')
    log_line_lbl.pack(fill='both', expand=True)

    # charts tab notebook
    CANVAS_W, CANVAS_H = 650, 180
    
    style = ttk.Style(win)
    style.theme_use('default')
    style.configure('TNotebook', background=C_BG, borderwidth=0)
    style.configure('TNotebook.Tab', background=C_CARD, foreground=C_MUTED, borderwidth=0, padding=[10, 2])
    style.map('TNotebook.Tab', background=[('selected', C_SUB)], foreground=[('selected', C_TEXT)])
    
    notebook = ttk.Notebook(body)
    notebook.pack(padx=14, pady=(4, 0), fill='both', expand=True)
    
    tab_health = tk.Frame(notebook, bg=C_BG)
    notebook.add(tab_health, text='By Cycle')
    chart_canvas = tk.Canvas(tab_health, width=CANVAS_W, height=CANVAS_H,
                             bg=C_CARD, highlightthickness=0)
    chart_canvas.pack(fill='both', expand=True)

    tab_stats = tk.Frame(notebook, bg=C_BG)
    notebook.add(tab_stats, text='By Image')
    stats_canvas = tk.Canvas(tab_stats, width=CANVAS_W, height=CANVAS_H,
                             bg=C_CARD, highlightthickness=0)
    stats_canvas.pack(fill='both', expand=True)

    tab_perf = tk.Frame(notebook, bg=C_BG)
    notebook.add(tab_perf, text='By Account')
    perf_canvas = tk.Canvas(tab_perf, width=CANVAS_W, height=CANVAS_H,
                            bg=C_CARD, highlightthickness=0)
    perf_canvas.pack(fill='both', expand=True)

    # ── Shared controls (fixed below notebook, window height stays constant) ──────
    _btn_tog_on  = dict(relief='flat', bg=C_BORDER, fg='#ffffff',
                        font=('Microsoft YaHei UI Bold', 8), padx=10, pady=2,
                        cursor='hand2', activebackground='#9d5df0', activeforeground='#ffffff')
    _btn_tog_off = dict(relief='flat', bg=C_SUB, fg=C_MUTED,
                        font=('Microsoft YaHei UI Bold', 8), padx=10, pady=2,
                        cursor='hand2', activebackground='#363d52', activeforeground=C_TEXT)

    ctrl_frame = tk.Frame(body, bg=C_BG, pady=4)
    ctrl_frame.pack(fill='x', padx=24) # Align with notebook padding
    
    tk.Label(ctrl_frame, text='Scale:', bg=C_BG, fg=C_MUTED,
             font=('Microsoft YaHei UI', 8)).pack(side='left', padx=(0, 8))
    
    btn_scale_linear = tk.Button(ctrl_frame, text='Linear', **_btn_tog_off)
    btn_scale_linear.pack(side='left', padx=(0, 4))
    btn_scale_log = tk.Button(ctrl_frame, text='Log', **_btn_tog_on)
    btn_scale_log.pack(side='left')

    perf_lbl = tk.Label(ctrl_frame, text='Y Axis:', bg=C_BG, fg=C_MUTED,
                        font=('Microsoft YaHei UI', 8))
    perf_btn_images = tk.Button(ctrl_frame, text='📊 Images', **_btn_tog_on)
    perf_btn_duration = tk.Button(ctrl_frame, text='⏱ Duration', **_btn_tog_off)

    def _update_scale_ui(mode):
        if mode == 'log':
            btn_scale_log.config(**_btn_tog_on)
            btn_scale_linear.config(**_btn_tog_off)
        else:
            btn_scale_log.config(**_btn_tog_off)
            btn_scale_linear.config(**_btn_tog_on)

    def _on_tab_changed(event):
        current_tab = notebook.index(notebook.select())
        ui_prefs['active_tab'] = current_tab
        _save_ui_prefs()
        
        mode = ui_prefs.get(f'scale_{current_tab}', 'log')
        _update_scale_ui(mode)
        
        if current_tab == 2: # By Account
            perf_lbl.pack(side='left', padx=(20, 8))
            perf_btn_images.pack(side='left', padx=(0, 4))
            perf_btn_duration.pack(side='left')
        else:
            perf_lbl.pack_forget()
            perf_btn_images.pack_forget()
            perf_btn_duration.pack_forget()
            
    notebook.bind('<<NotebookTabChanged>>', _on_tab_changed)

    def _redraw_all_charts():
        cw1, ch1 = chart_canvas.winfo_width(), chart_canvas.winfo_height()
        cw2, ch2 = stats_canvas.winfo_width(), stats_canvas.winfo_height()
        cw3, ch3 = perf_canvas.winfo_width(), perf_canvas.winfo_height()
        if _cached_detailed:
            _draw_chart(chart_canvas, _cached_detailed, cw1 if cw1 > 10 else CANVAS_W, ch1 if ch1 > 10 else CANVAS_H)
            _draw_perf_chart(perf_canvas, _cached_detailed, cw3 if cw3 > 10 else CANVAS_W, ch3 if ch3 > 10 else CANVAS_H, ui_prefs.get('perf_mode', 'images'))
        try:
            reject_stats = _load_stats_data()
            if reject_stats:
                _draw_stats_chart(stats_canvas, reject_stats, cw2 if cw2 > 10 else CANVAS_W, ch2 if ch2 > 10 else CANVAS_H)
        except Exception:
            pass

    def _set_scale_mode(mode):
        current_tab = notebook.index(notebook.select())
        ui_prefs[f'scale_{current_tab}'] = mode
        _save_ui_prefs()
        _update_scale_ui(mode)
        _redraw_all_charts()

    btn_scale_linear.config(command=lambda: _set_scale_mode('linear'))
    btn_scale_log.config(command=lambda: _set_scale_mode('log'))

    def _set_perf_mode(mode):
        ui_prefs['perf_mode'] = mode
        _save_ui_prefs()
        if mode == 'images':
            perf_btn_images.config(**_btn_tog_on)
            perf_btn_duration.config(**_btn_tog_off)
        else:
            perf_btn_images.config(**_btn_tog_off)
            perf_btn_duration.config(**_btn_tog_on)
        cw3, ch3 = perf_canvas.winfo_width(), perf_canvas.winfo_height()
        _draw_perf_chart(perf_canvas, _cached_detailed,
                         cw3 if cw3 > 10 else CANVAS_W,
                         ch3 if ch3 > 10 else CANVAS_H, mode)

    perf_btn_images.config(command=lambda: _set_perf_mode('images'))
    perf_btn_duration.config(command=lambda: _set_perf_mode('time'))
    
    # Initialize UI states from prefs
    try:
        notebook.select(ui_prefs.get('active_tab', 0))
    except Exception:
        pass
    _set_perf_mode(ui_prefs.get('perf_mode', 'images'))
    win.after(50, lambda: _on_tab_changed(None))

    # buttons & image processing styles
    _btn_style = dict(relief='flat', bg=C_SUB, fg=C_TEXT,
                      font=('Microsoft YaHei UI Bold', 9), padx=8, pady=4,
                      cursor='hand2', activebackground='#363d52',
                      activeforeground=C_TEXT)

    # image processing frame
    img_proc_frame = tk.LabelFrame(body, text='Process Latest Download Image', bg=C_BG, fg=C_MUTED, font=('Microsoft YaHei UI Bold', 9), padx=14, pady=0)
    img_proc_frame.pack(fill='x', padx=14, pady=(10, 0))
    
    def _get_latest_image():
        if not auto_folder or not os.path.exists(auto_folder):
            return []
        try:
            files = [os.path.join(auto_folder, f) for f in os.listdir(auto_folder) 
                     if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
            files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            return files[:1]
        except Exception:
            return []

    def _do_move_to():
        from tkinter import filedialog, messagebox
        import shutil
        latest_imgs = _get_latest_image()
        if not latest_imgs:
            messagebox.showinfo("Move", "No images found.", parent=win)
            return
        dest = filedialog.askdirectory(title="Move to New Folder", initialdir=auto_folder, parent=win)
        if not dest: return
        errors = []
        for img in latest_imgs:
            try: shutil.move(img, os.path.join(dest, os.path.basename(img)))
            except Exception as e: errors.append(f"Move original failed: {e}")
            try:
                proc_file = os.path.join(os.path.dirname(img), "processed", os.path.basename(img))
                if os.path.exists(proc_file):
                    proc_dest = os.path.join(dest, "processed")
                    os.makedirs(proc_dest, exist_ok=True)
                    shutil.move(proc_file, os.path.join(proc_dest, os.path.basename(proc_file)))
            except Exception as e: errors.append(f"Move processed failed: {e}")
        if errors:
            messagebox.showerror("Move Errors", "\n".join(errors), parent=win)

    def _do_delete():
        from tkinter import messagebox
        import ctypes
        from ctypes import wintypes
        
        def _send_to_recycle_bin(path):
            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR),
                    ("fFlags", wintypes.WORD),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", wintypes.LPVOID),
                    ("lpszProgressTitle", wintypes.LPCWSTR)
                ]
            path_with_double_null = os.path.abspath(path) + '\0'
            shfos = SHFILEOPSTRUCTW()
            shfos.hwnd = None
            shfos.wFunc = 3  # FO_DELETE
            shfos.pFrom = path_with_double_null
            shfos.pTo = None
            shfos.fFlags = 0x40 | 0x10  # FOF_ALLOWUNDO | FOF_NOCONFIRMATION
            shfos.fAnyOperationsAborted = False
            shfos.hNameMappings = None
            shfos.lpszProgressTitle = None
            result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(shfos))
            if result != 0:
                raise Exception(f"Error code {result}")

        latest_imgs = _get_latest_image()
        if not latest_imgs:
            messagebox.showinfo("Delete", "No images found.", parent=win)
            return
            
        errors = []
        for img in latest_imgs:
            try: _send_to_recycle_bin(img)
            except Exception as e: errors.append(f"Delete original failed: {e}")
            try:
                proc_file = os.path.join(os.path.dirname(img), "processed", os.path.basename(img))
                if os.path.exists(proc_file):
                    _send_to_recycle_bin(proc_file)
            except Exception as e: errors.append(f"Delete processed failed: {e}")
            
        if errors:
            messagebox.showerror("Delete Errors", "\n".join(errors), parent=win)

    def _do_view_image():
        from tkinter import messagebox
        latest_imgs = _get_latest_image()
        if not latest_imgs:
            messagebox.showinfo("View", "No images found.", parent=win)
            return
        for img in latest_imgs:
            try:
                _open_file_foreground(img)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open image:\n{e}", parent=win)

    tk.Button(img_proc_frame, text='View Image', command=_do_view_image, **_btn_style).pack(side='left', expand=True, fill='x', padx=(0, 6), pady=(8, 6))
    tk.Button(img_proc_frame, text='Move to New Folder', command=_do_move_to, **_btn_style).pack(side='left', expand=True, fill='x', padx=(0, 6), pady=(8, 6))
    tk.Button(img_proc_frame, text='Delete', command=_do_delete, **_btn_style).pack(side='left', expand=True, fill='x', padx=0, pady=(8, 6))

    # main action buttons
    btn_frame = tk.Frame(body, bg=C_BG, padx=14, pady=10)
    btn_frame.pack(fill='x')

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
              command=_open_auto, **_btn_style).pack(side='left', expand=True, fill='x', padx=(0, 6))
    tk.Button(btn_frame, text='📁 Upscale Folder',
              command=_open_upscale, **_btn_style).pack(side='left', expand=True, fill='x', padx=(0, 6))

    _gemi_running = _is_gemipersona_running()
    _gemi_btn = tk.Button(btn_frame, text='🌐 Open GemiPersona',
                          command=_open_gemi, **_btn_style)
    if _gemi_running:
        _gemi_btn.config(state='disabled', fg=C_MUTED, cursor='arrow')
    _gemi_btn.pack(side='left', expand=True, fill='x', padx=(0, 6))

    def _reset_new_images():
        last_ack = _load_notifier_state()
        if auto_folder and os.path.exists(auto_folder):
            last_ack['auto'] = set(os.listdir(auto_folder))
            try:
                data = {}
                if os.path.exists(_STATE_FILE):
                    with open(_STATE_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                data['last_ack_auto'] = list(last_ack['auto'])
                data['last_ack_upscale'] = list(last_ack.get('upscale', set()))
                
                with open(_STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f)
            except Exception:
                pass
            if 'auto_new' in stat_labels:
                stat_labels['auto_new'].config(text='0', fg=C_TEXT)

    tk.Button(btn_frame, text='Reset New Images Count', relief='flat',
              bg=C_SUB, fg=C_TEXT, font=('Microsoft YaHei UI Bold', 9),
              padx=10, pady=4, cursor='hand2',
              activebackground='#363d52', activeforeground=C_TEXT,
              command=_reset_new_images).pack(side='left', expand=True, fill='x', padx=(0, 6))

    tk.Button(btn_frame, text='Close', relief='flat',
              bg=C_SUB, fg=C_MUTED, font=('Microsoft YaHei UI Bold', 9),
              padx=10, pady=4, cursor='hand2',
              activebackground='#363d52', activeforeground=C_TEXT,
              command=_close).pack(side='left', expand=True, fill='x', padx=0)

    # ── polling loops ─────────────────────────────────────────────────────────
    # 所有阻塞 I/O（文件读取、socket 连接、log 解析）均在 daemon 线程中执行，
    # 仅通过 win.after(0, callback) 回调在 UI 线程更新控件，避免卡顿。

    def _apply_chart_data(detailed, cycles, stats, reject_stats):
        """在 UI 线程中将解析结果写入控件。"""
        try:
            if not win.winfo_exists():
                return
            if '_error' in stats:
                chart_canvas.delete('all')
                chart_canvas.create_text(
                    CANVAS_W // 2, CANVAS_H // 2,
                    text=f"Error loading data:\n{stats['_error']}",
                    fill='#ff6666', font=('Microsoft YaHei UI', 9), justify='center')
                status_badge.config(text='⚠ Load Error', fg='#ff6666')
                return
            stat_labels['account'].config(text=stats.get('account', 'N/A'))
            
            if reject_stats:
                # Images = historical completed rows (same as Dashboard)
                tot_img = sum(1 for r in reject_stats if r.get('filename') not in ["[Stopped/Interrupted]", "[Account Switched]"])
                stat_labels['images'].config(text=str(tot_img))
                
            is_running = stats.get('is_running', False)
            if is_running:
                # Refused/Reset = live API counters, exactly like Dashboard running summary
                tot_ref = int(stats.get('refused', 0))
                tot_res = int(stats.get('reset', 0))
            else:
                # Refused/Reset = historical sum from log (same as Dashboard stopped view)
                tot_ref = sum(int(r.get('refused_count', 0)) for r in reject_stats)
                tot_res = sum(int(r.get('reset_count', 0)) for r in reject_stats)
                
            stat_labels['refused'].config(text=str(tot_ref), fg='#a0a0ff' if tot_ref > 0 else C_TEXT)
            stat_labels['reset'].config(text=str(tot_res), fg='#f39c12' if tot_res > 0 else C_TEXT)
                
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
            stat_labels['cycle_dur'].config(text=stats.get('cycle_dur', '—') or '—')
            
            stat_labels['total_cycles'].config(text=str(stats.get('total_cycles', 0)))
            stat_labels['acct_switch'].config(text=str(stats.get('acct_switch', '—')))
            stat_labels['acct_images'].config(text=str(stats.get('acct_images', 0)))
            
            acct_ref_val = int(stats.get('acct_refused') or 0)
            acct_res_val = int(stats.get('acct_reset') or 0)
            
            stat_labels['acct_refused'].config(text=str(acct_ref_val),
                fg='#a0a0ff' if acct_ref_val > 0 else C_TEXT)
            stat_labels['acct_reset'].config(text=str(acct_res_val),
                fg='#f39c12' if acct_res_val > 0 else C_TEXT)
            if stats.get('is_running'):
                status_badge.config(text='● Running', fg='#2ecc71')
            else:
                status_badge.config(text='○ Stopped', fg=C_MUTED)
            cw1, ch1 = chart_canvas.winfo_width(), chart_canvas.winfo_height()
            cw2, ch2 = stats_canvas.winfo_width(), stats_canvas.winfo_height()
            cw3, ch3 = perf_canvas.winfo_width(), perf_canvas.winfo_height()
            _draw_chart(chart_canvas, detailed, cw1 if cw1 > 10 else CANVAS_W, ch1 if ch1 > 10 else CANVAS_H)
            _draw_stats_chart(stats_canvas, reject_stats, cw2 if cw2 > 10 else CANVAS_W, ch2 if ch2 > 10 else CANVAS_H)
            _draw_perf_chart(perf_canvas, detailed, cw3 if cw3 > 10 else CANVAS_W, ch3 if ch3 > 10 else CANVAS_H, ui_prefs.get('perf_mode', 'images'))
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

    def _apply_sys_status(engine_ok, browser_ok, cpu_val):
        """在 UI 线程中将系统状态写入控件。"""
        try:
            if not win.winfo_exists():
                return
            if engine_ok:
                stat_labels['engine_status'].config(text='Started', fg='#2ecc71')
            else:
                stat_labels['engine_status'].config(text='Stopped', fg='#ff4444')

            if browser_ok:
                stat_labels['browser_status'].config(text='Running', fg='#2ecc71')
            else:
                stat_labels['browser_status'].config(text='Closed', fg='#ff4444')

            cpu_str = f"{cpu_val:.1f}%"
            if cpu_val >= 80.0:
                cpu_fg = '#ff4444'
            elif cpu_val >= 50.0:
                cpu_fg = '#f39c12'
            else:
                cpu_fg = C_TEXT
            stat_labels['cpu_usage'].config(text=cpu_str, fg=cpu_fg)
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

            engine_ok = False
            browser_ok = False
            try:
                import requests
                resp = requests.get("http://127.0.0.1:8000/health", timeout=0.5)
                if resp.status_code == 200:
                    engine_ok = True
                    health_data = resp.json()
                    browser_ok = health_data.get("engine_running", False)
            except Exception:
                pass

            cpu_val = 0.0
            try:
                import psutil
                cpu_val = psutil.cpu_percent(interval=None)
            except Exception:
                pass

            try:
                if win.winfo_exists():
                    win.after(0, lambda: _apply_log_data(line, alive))
                    win.after(0, lambda: _apply_sys_status(engine_ok, browser_ok, cpu_val))
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
                reject_stats = _load_stats_data()
            except Exception:
                reject_stats = []
            try:
                if win.winfo_exists():
                    win.after(0, lambda: _apply_chart_data(detailed, cycles, stats, reject_stats))
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
