"""Account Health log parsing utilities. Extracted from 04_System_Config.py."""
import json
import os
import re
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LOG_PATH = os.path.join(BASE_DIR, "engine.log")


def parse_engine_cycles():
    if not os.path.exists(LOG_PATH):
        return []
    cycles = []
    current_cycle = None
    pending_boundary = False
    boundary_account = None

    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            line = line.strip()
            
            # --- JSON PARSING ---
            if line.startswith("{"):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                event = rec.get("event", "")
                acct = rec.get("account", "unknown")
                round_id = rec.get("round", 1)
                
                if event == "BOUNDARY":
                    pending_boundary = True
                    boundary_account = acct
                    
                if event == "START":
                    is_new_cycle = False
                    if pending_boundary:
                        if round_id == 1 or acct != boundary_account:
                            is_new_cycle = True
                        pending_boundary = False
                        boundary_account = None
                    else:
                        if round_id == 1:
                            is_new_cycle = True
                            
                    if is_new_cycle:
                        if current_cycle is not None:
                            current_cycle['end_idx'] = i - 1
                            cycles.append(current_cycle)
                        try:
                            dt = datetime.fromisoformat(rec.get("ts", ""))
                            ts = dt.strftime("%H:%M:%S")
                        except:
                            ts = "Unknown"
                        current_cycle = {
                            'start_idx': i, 'start_time_str': ts,
                            'end_idx': None, 'lines_count': 0,
                            'stop_time_str': ts, 'success_count': 0
                        }
                if current_cycle is not None:
                    current_cycle['lines_count'] += 1
                    if event == "SUCCESS" and rec.get("filename"):
                        current_cycle['success_count'] += 1
                    if "ts" in rec:
                        try:
                            dt = datetime.fromisoformat(rec.get("ts", ""))
                            current_cycle['stop_time_str'] = dt.strftime("%H:%M:%S")
                        except:
                            pass
                continue
                
            # --- TEXT PARSING (Legacy) ---
            if "--- [AUTO] RUNNING ROUND: 1 ---" in line:
                if current_cycle is not None:
                    current_cycle['end_idx'] = i - 1
                    cycles.append(current_cycle)
                match = re.search(r"\[(\d{2}:\d{2}:\d{2})\]", line)
                ts = match.group(1) if match else "Unknown"
                current_cycle = {
                    'start_idx': i, 'start_time_str': ts,
                    'end_idx': None, 'lines_count': 0,
                    'stop_time_str': ts, 'success_count': 0
                }
            if current_cycle is not None:
                current_cycle['lines_count'] += 1
                
                if "saved: " in line.lower() and ".png" in line.lower():
                    current_cycle['success_count'] += 1
                
                ts_match = re.search(r"\[(\d{2}:\d{2}:\d{2})\]", line)
                if ts_match:
                    current_cycle['stop_time_str'] = ts_match.group(1)
                
                if "Final Stats:" in line and "'start_time': '" in line:
                    match = re.search(r"'start_time': '([^']+)'", line)
                    if match:
                        current_cycle['full_start_time'] = match.group(1)
    
    return cycles


def parse_account_health(target_account=None, login_data=None):
    if not os.path.exists(LOG_PATH):
        return [], [], []
    summary_results = {}
    detailed_results = []
    found_accounts_set = set()
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        current_account = "Unknown"
        last_stable_account = "Unknown"  # Tracks account established by major events
        current_session_id = 1
        active_event = None
        last_boundary_idx = -1
        pending_new_session = False   # True after BOUNDARY, resolved on next START
        boundary_account = None       # Account that triggered the pending BOUNDARY
        for i, line in enumerate(lines):
            line_raw = line
            line = line.strip()
            # --- JSON PARSING ---
            if line.startswith("{"):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                acct = rec.get("account", "unknown")
                # Skip system entries (e.g. LOG_CLEARED)
                if acct == "system":
                    continue
                found_accounts_set.add(acct)
                current_account = acct
                event = rec.get("event", "").upper()
                round_id = rec.get("round", 0)
                try:
                    dt = datetime.fromisoformat(rec.get("ts", ""))
                    ts = dt.strftime("%H:%M:%S")
                except:
                    ts = "00:00:00"
                if event in ("BOUNDARY", "ACCOUNT_SWITCH"):
                    if event == "ACCOUNT_SWITCH":
                        # Same account → re-login → keep the same session.
                        # Different account → immediate new session.
                        if acct != last_stable_account and last_boundary_idx != i - 1:
                            current_session_id += 1
                            pending_new_session = False  # Account switch supersedes any pending bump
                            boundary_account = None
                    else:  # BOUNDARY (deliberate stop)
                        # Don't increment yet — defer to next START so that
                        # "continue session" (round_id > 1) stays in the same session.
                        pending_new_session = True
                        boundary_account = acct
                    last_boundary_idx = i
                    last_stable_account = acct
                    active_event = None
                    continue
                if event == "START":
                    if pending_new_session:
                        # Fresh start (round 1) or different account → genuine new session.
                        # Continue session (round_id > 1, same account) → same session.
                        if round_id == 1 or acct != boundary_account:
                            current_session_id += 1
                        pending_new_session = False
                        boundary_account = None
                    last_stable_account = acct
                    active_event = {
                        "start_time": ts, "account": acct,
                        "session_index": current_session_id,
                        "line_idx": i, "closed": False,
                        "round": round_id
                    }
                    continue
                if event == "REJECT_STAT":
                    fname = rec.get("filename", "")
                    for prev in reversed(detailed_results[-5:]):
                        if prev.get("filename") == fname:
                            prev["true_rej"] = rec.get("reject", 0)
                            prev["true_res"] = rec.get("reset", 0)
                            prev["health"] = f"{rec.get('duration', 0)}s"
                            break
                    continue
                if event == "SUCCESS":
                    fname = rec.get("filename", "")
                    if not fname:
                        search_range = range(max(0, i), min(i + 50, len(lines)))
                        for k in search_range:
                            line_k = lines[k].strip()
                            if line_k.startswith("{"):
                                try:
                                    f_rec = json.loads(line_k)
                                    if f_rec.get("filename"):
                                        fname = f_rec["filename"]
                                        break
                                except: pass
                            else:
                                if "saved: " in line_k.lower():
                                    try: fname = line_k.split("Saved: ")[1].strip()
                                    except: pass
                                    if fname: break
                    temp_start_time = active_event["start_time"] if active_event else ts
                    temp_session_idx = active_event["session_index"] if active_event else current_session_id
                    temp_account = active_event["account"] if active_event else acct
                    is_dup = False
                    if fname:
                        for prev in detailed_results[-5:]:
                            if prev.get("filename") == fname and prev.get("session_index") == temp_session_idx:
                                is_dup = True; break
                    if not is_dup:
                        true_dur = 0
                        if active_event:
                            try:
                                fmt = '%H:%M:%S'
                                tdelta = datetime.strptime(ts, fmt) - datetime.strptime(active_event["start_time"], fmt)
                                true_dur = int(tdelta.total_seconds())
                                if true_dur < 0: true_dur += 86400
                            except: true_dur = 0
                        record = {
                            "account": temp_account, "time": temp_start_time,
                            "health": f"{true_dur}s", "filename": fname,
                            "status": "Success" if fname else "Fail",
                            "session_index": temp_session_idx,
                            "round": active_event.get("round", round_id) if active_event else round_id
                        }
                        detailed_results.append(record)
                        summary_results[record["account"]] = record
                        active_event = None
                    continue
                if event in ("REJECT", "RESET"):
                    temp_start_time = active_event["start_time"] if active_event else ts
                    temp_session_idx = active_event["session_index"] if active_event else current_session_id
                    temp_account = active_event["account"] if active_event else acct
                    current_round = active_event.get("round", round_id) if active_event else round_id
                    
                    if detailed_results:
                        last_rec = detailed_results[-1]
                        if last_rec.get("round") == current_round and last_rec.get("status") == event.title():
                            continue

                    try:
                        fmt = '%H:%M:%S'
                        tdelta = datetime.strptime(ts, fmt) - datetime.strptime(temp_start_time, fmt)
                        fail_dur = int(tdelta.total_seconds())
                        if fail_dur < 0: fail_dur += 86400
                    except: fail_dur = 0
                    record = {
                        "account": temp_account, "time": temp_start_time,
                        "health": f"{fail_dur}s", "filename": "",
                        "status": event.title(), "session_index": temp_session_idx,
                        "round": active_event.get("round", round_id) if active_event else round_id
                    }
                    detailed_results.append(record)
                    if record["account"] not in summary_results or summary_results[record["account"]]["status"] != "Success":
                        summary_results[record["account"]] = record
                    if active_event: active_event["start_time"] = ts
                    continue
                continue
            # --- TEXT PARSING (Legacy) ---
            line_lower = line_raw.lower()
            potential_new_acc = None
            if "profile switched to" in line_lower:
                try: potential_new_acc = line_raw.split("switched to")[1].split()[0].strip().rstrip('.:').split('@')[0].lower()
                except: pass
            elif "re-login detected for" in line_lower:
                try: potential_new_acc = line_raw.split("detected for")[1].split()[0].strip().rstrip('.:').split('@')[0].lower()
                except: pass
            elif "switched to" in line_lower:
                try: potential_new_acc = line_raw.split("switched to")[1].split()[0].strip().rstrip('.:').split('@')[0].lower()
                except: pass
            is_auto_finished = "automation finished" in line_lower
            is_acc_switch = bool(potential_new_acc and potential_new_acc != current_account)
            if is_auto_finished:
                # Defer session bump to next START (same logic as JSON BOUNDARY)
                pending_new_session = True
                boundary_account = current_account
                last_boundary_idx = i
                active_event = None
            elif is_acc_switch:
                # Real account switch → immediate new session
                if last_boundary_idx != i - 1:
                    current_session_id += 1
                    pending_new_session = False
                    boundary_account = None
                last_boundary_idx = i
                active_event = None
            if potential_new_acc:
                current_account = potential_new_acc
                found_accounts_set.add(potential_new_acc)
            if "current_account_id" in line_raw:
                match = re.search(r"['\"]current_account_id['\"]\s*:\s*['\"]([^'\"]+)['\"]", line_raw)
                if match:
                    current_account = match.group(1).split('@')[0].lower()
                    found_accounts_set.add(current_account)
            if "正在加载 Nano Banana 2..." in line_raw or "API>> Gemini:" in line_raw and "加载" in line_raw or "--- [auto] running round" in line_lower:
                if active_event is None:
                    try: ts_raw = re.search(r"\[(\d{2}:\d{2}:\d{2})\]", line_raw).group(1)
                    except: ts_raw = "00:00:00"
                    active_event = {
                        "start_time": ts_raw, "account": current_account,
                        "session_index": current_session_id,
                        "line_idx": i, "closed": False
                    }
            status = None
            if "response successful" in line_lower: status = "Success"
            elif "saved: " in line_lower and ".png" in line_lower: status = "Success"
            elif "response failed (refused)" in line_lower: status = "Reject"
            elif "gemini page was unexpectedly reset" in line_lower: status = "Reset"
            elif "automation loop encountered an issue" in line_lower: status = "Reset"
            if status:
                try: ts_raw = re.search(r"\[(\d{2}:\d{2}:\d{2})\]", line_raw).group(1)
                except: ts_raw = "00:00:00"
                temp_start_time = active_event["start_time"] if active_event else ts_raw
                temp_session_idx = active_event["session_index"] if active_event else current_session_id
                temp_account = active_event["account"] if active_event else current_account
                if status == "Success":
                    fname = ""
                    if "saved: " in line_lower:
                        try: fname = line_raw.split("Saved: ")[1].strip()
                        except: pass
                    true_dur = None; true_rej = 0; true_res = 0
                    search_range = range(max(0, i - 10), min(i + 50, len(lines)))
                    for k in search_range:
                        if not fname and "saved: " in lines[k].lower():
                            try: fname = lines[k].split("Saved: ")[1].strip()
                            except: pass
                        if "rejectstat: wrote record for" in lines[k].lower() and fname and fname in lines[k]:
                            stat_match = re.search(r"dur=([\d.]+)s, ref=(\d+), rst=(\d+)", lines[k])
                            if stat_match:
                                true_dur = float(stat_match.group(1))
                                true_rej = int(stat_match.group(2))
                                true_res = int(stat_match.group(3))
                                break
                    is_dup = False
                    if fname:
                        for prev in detailed_results[-5:]:
                            if prev.get("filename") == fname and prev.get("session_index") == temp_session_idx:
                                is_dup = True; break
                    if not is_dup and (true_dur is not None or active_event or fname):
                        if true_dur is None and active_event:
                            try:
                                fmt = '%H:%M:%S'
                                tdelta = datetime.strptime(ts_raw, fmt) - datetime.strptime(active_event["start_time"], fmt)
                                true_dur = int(tdelta.total_seconds())
                                if true_dur < 0: true_dur += 86400
                            except: true_dur = 0
                        if true_dur is None: true_dur = 0
                        record = {
                            "account": temp_account, "time": temp_start_time,
                            "health": f"{true_dur}s", "filename": fname,
                            "status": "Success" if fname else "Fail",
                            "session_index": temp_session_idx,
                            "true_rej": true_rej, "true_res": true_res
                        }
                        detailed_results.append(record)
                        summary_results[record["account"]] = record
                    if not is_dup: active_event = None
                else:
                    try:
                        fmt = '%H:%M:%S'
                        tdelta = datetime.strptime(ts_raw, fmt) - datetime.strptime(temp_start_time, fmt)
                        fail_dur = int(tdelta.total_seconds())
                        if fail_dur < 0: fail_dur += 86400
                    except: fail_dur = 0
                    record = {
                        "account": temp_account, "time": temp_start_time,
                        "health": f"{fail_dur}s", "filename": "",
                        "status": status, "session_index": temp_session_idx
                    }
                    detailed_results.append(record)
                    if record["account"] not in summary_results or summary_results[record["account"]]["status"] != "Success":
                        summary_results[record["account"]] = record
                    if active_event: active_event["start_time"] = ts_raw
        # Backfill Unknown accounts
        first_real = None
        for r in detailed_results:
            if r["account"] and r["account"] != "Unknown":
                first_real = r["account"]
                break
        if not first_real and login_data:
            try:
                active_acc = next((u.get("username", "").lower().strip() for u in login_data if u.get("active")), None)
                if active_acc:
                    first_real = active_acc
                else:
                    latest_acc = None; latest_ts = None
                    for u in login_data:
                        ts_str = u.get("last_switched_at")
                        if ts_str:
                            try:
                                ts = datetime.strptime(ts_str, "%d/%m/%Y %H:%M:%S")
                                if latest_ts is None or ts > latest_ts:
                                    latest_ts = ts; latest_acc = u.get("username", "").lower().strip()
                            except: continue
                    first_real = latest_acc
            except: pass
        if first_real:
            for r in detailed_results:
                if r["account"] == "Unknown" or not r["account"]:
                    r["account"] = first_real
            if "Unknown" in summary_results:
                if first_real not in summary_results:
                    summary_results[first_real] = summary_results["Unknown"]
                    summary_results[first_real]["account"] = first_real
                del summary_results["Unknown"]
        if first_real:
            summary_results = {(first_real if k == "Unknown" else k): v for k, v in summary_results.items()}
            for v in summary_results.values():
                if v["account"] == "Unknown": v["account"] = first_real
        if target_account == "ALL_EVENTS":
            pass
        elif target_account:
            detailed_results = [r for r in detailed_results if r["account"].lower() == target_account.lower()]
        else:
            detailed_results = []
    except Exception as e:
        import traceback, streamlit as st
        st.error(f"Error parsing log: {e}")
        print(traceback.format_exc())
    summary_list = list(reversed(list(summary_results.values())))
    detailed_list = list(reversed(detailed_results))
    valid_accounts = [acc for acc in found_accounts_set if acc is not None and isinstance(acc, str)]
    return summary_list, detailed_list, sorted(valid_accounts)
