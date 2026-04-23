
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
        
        results = []

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
            
            if "正在加载 Nano Banana 2..." in line:
                filename = ""
                # Look ahead for filename
                for j in range(i + 1, min(i + 200, len(lines))):
                    if "Saved: " in lines[j]:
                        filename = lines[j].split("Saved: ")[1].strip()
                        break
                
                if filename:
                    img_num = filename.replace(".png", "")
                    if img_num in ["857", "858", "859"]:
                        results.append({
                            "image": img_num,
                            "account": current_account,
                            "session": session_index,
                            "line": i + 1
                        })
        
        for r in results:
            print(r)

    except Exception as e:
        print(e)

debug_parse()
