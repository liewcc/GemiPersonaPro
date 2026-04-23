
import re
from datetime import datetime

LOG_PATH = "engine.log"

def debug_parse():
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        current_account = "Unknown"
        session_index = 1
        last_noted_account = None
        
        last_session = None

        for i, line in enumerate(lines):
            acc_id = None
            if "Re-login detected for" in line:
                acc_id = line.split("Re-login detected for")[1].split()[0].strip().rstrip('.:')
            elif "switched to" in line:
                acc_id = line.split("switched to")[1].split()[0].strip().rstrip('.:')
            elif "current_account_id" in line:
                match = re.search(r"['\"]current_account_id['\"]\s*:\s*['\"]([^'\"]+)['\"]", line)
                if match: acc_id = match.group(1)
            
            if acc_id:
                normalized = acc_id.split('@')[0].lower().strip()
                if last_noted_account is not None and normalized != last_noted_account:
                    session_index += 1
                last_noted_account = normalized
                current_account = normalized
            
            if session_index != last_session:
                print(f"Line {i+1}: SESSION {session_index} START - Account: {current_account}")
                last_session = session_index

    except Exception as e:
        print(e)

debug_parse()
