import streamlit as st
import json
import os
import pandas as pd
from style_utils import apply_premium_style, render_dashboard_header
from config_utils import load_config as load_cfg_disk, save_config as save_cfg_disk, load_login_lookup, save_login_lookup

# --- Page Config ---
st.set_page_config(page_title="GemiPersona | SYSTEM CONFIG", page_icon="sys_img/logo.png", layout="wide")
apply_premium_style()

# --- Data Loading Functions ---
def load_config():
    return load_cfg_disk()

def save_config(updates):
    return save_cfg_disk(updates)

# --- Engine Config Callbacks ---
def on_change_console():
    save_config({"show_engine_console": st.session_state.cfg_show_console})

def on_change_headless():
    save_config({"headless": st.session_state.cfg_headless})

def on_change_timeout():
    save_config({"heartbeat_timeout": st.session_state.cfg_timeout})

def on_change_watchdog_delay():
    save_config({"watchdog_initial_delay": st.session_state.cfg_watchdog_delay})

def on_change_quota_cooldown():
    save_config({"quota_cooldown_hours": st.session_state.cfg_quota_cooldown_hrs})

# --- Main Logic ---

config = load_config()
login_data = load_login_lookup()

# --- Always reload fresh data on every page entry / rerun ---
# Engine settings are saved to disk immediately via on_change callbacks,
# so disk values always reflect the current state — safe to unconditionally restore.
st.session_state.cfg_show_console = config.get("show_engine_console", True)
st.session_state.cfg_headless = config.get("headless", False)
st.session_state.cfg_timeout = config.get("heartbeat_timeout", 3600)
st.session_state.cfg_watchdog_delay = config.get("watchdog_initial_delay", 20)
st.session_state.cfg_quota_cooldown_hrs = config.get("quota_cooldown_hours", 0)

# Reload login rows from disk on every rerun.
# Since all edits in the data_editor are saved to disk instantly,
# reloading ensures the UI and JSON are always in perfect synchronization.
st.session_state.login_rows = list(login_data)
st.session_state._login_reload = False

WATCHDOG_LOG_PATH = "watchdog.log"

def get_watchdog_log():
    if not os.path.exists(WATCHDOG_LOG_PATH):
        return None
    try:
        with open(WATCHDOG_LOG_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading log: {e}"

def clear_watchdog_log():
    try:
        # Open in write mode to clear contents, preventing conflict if watchdog is just appending
        with open(WATCHDOG_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("")
    except Exception as e:
        st.error(f"Failed to clear log: {e}")

# Section 1 & Watchdog Log: Split into two columns
col_engine, col_watchdog = st.columns([1, 1])

# --- Section 1: Engine Settings ---
with col_engine:
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>ENGINE SETTINGS</p>", unsafe_allow_html=True)
    with st.container(border=True):
        st.toggle(
            "Show Engine Console Window",
            key="cfg_show_console",
            on_change=on_change_console,
            help="If enabled, the background service will run in a visible console window."
        )

        st.toggle(
            "Run Browser Headless",
            key="cfg_headless",
            on_change=on_change_headless,
            help="If enabled, the browser will run in the background."
        )

        st.number_input(
            "Heartbeat Timeout (seconds)",
            min_value=0,
            max_value=86400,
            key="cfg_timeout",
            on_change=on_change_timeout,
            help="0 = Always stays alive."
        )

        st.number_input(
            "Watchdog Initial Delay (seconds)",
            min_value=5,
            max_value=120,
            step=5,
            key="cfg_watchdog_delay",
            on_change=on_change_watchdog_delay,
            help="How long the Watchdog waits after automation starts before its first session check. Increase if Gem pages take long to load."
        )

        st.number_input(
            "Quota Cooldown (hours)",
            min_value=0,
            max_value=168,
            step=1,
            key="cfg_quota_cooldown_hrs",
            on_change=on_change_quota_cooldown,
            help="If > 0, accounts are locked for this many hours after hitting quota (unlock = quota_full_time + hours). 0 = disabled."
        )

# --- Watchdog Log ---
with col_watchdog:
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>WATCHDOG LOG</p>", unsafe_allow_html=True)
    with st.container(border=True):
        log_content = get_watchdog_log()
        
        # Display Reload and Clear Log buttons side-by-side
        btn_col1, btn_col2 = st.columns([1, 1])
        with btn_col1:
            if st.button("Reload Log", key="btn_reload_watchdog", icon="🔄", help="Reload the latest watchdog log", type="secondary", width='stretch'):
                st.rerun()
        with btn_col2:
            if st.button("Clear Log", key="btn_clear_watchdog", icon="🗑️", help="Clear the watchdog log completely", type="secondary", width='stretch'):
                clear_watchdog_log()
                st.rerun()

        st.markdown("") # Spacer
        if log_content is None:
            st.info("Watchdog log not found or no errors detected.")
        elif not log_content.strip():
            st.info("Watchdog log is empty.")
        else:
            st.text_area("Log Output", value=log_content, height=200, disabled=True, label_visibility="collapsed")


# Layout for Quota & Credentials -> 1:3 ratio
col_quota, col_cred = st.columns([1, 3])

# --- Section 2: Quota Detection Settings ---
with col_quota:
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>QUOTA FULL PHRASES</p>", unsafe_allow_html=True)
    with st.container(border=True):
        quota_phrases = config.get("quota_full", [])
        quota_df = pd.DataFrame([{"phrase": p} for p in quota_phrases])

        edited_quota_df = st.data_editor(
            quota_df,
            column_config={
                "phrase": st.column_config.TextColumn("Identification Phrase", width="stretch"),
            },
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            height=415,
            key="quota_editor"
        )
        
        # Spacer padding to visually align the bottom contour of this container with the taller right container
        st.markdown("<div style='height: 85px;'></div>", unsafe_allow_html=True)

        if st.button("Save Quota Phrases", icon="📝", width='stretch'):
            new_phrases = edited_quota_df["phrase"].tolist()
            new_phrases = [p.strip() for p in new_phrases if p is not None and p.strip()]
            save_config({"quota_full": new_phrases})
            st.success("Quota phrases updated!")
            st.rerun()

# --- Section 3: Credential Management ---
with col_cred:
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>USER LOGIN CREDENTIALS</p>", unsafe_allow_html=True)
    with st.container(border=True):
        # login_rows is always reloaded from disk at the top of the script;
        # no additional check needed here.

        rows = st.session_state.login_rows
        usernames = [r.get("username", "") for r in rows if r.get("username")]

        active_index = 0
        for i, r in enumerate(rows):
            if r.get("active"):
                active_index = i
                break

        if usernames:
            sel_col, btn_col = st.columns([3, 1])
            with sel_col:
                selected_active = st.selectbox(
                    "Active Account",
                    options=usernames,
                    index=min(active_index, len(usernames) - 1),
                    help="Select the account to use for the current session",
                    key="active_account_select"
                )
            with btn_col:
                st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                if st.button("Set Active Account", icon="🔒", type="primary", width="stretch"):
                    current_rows = load_login_lookup()
                    final = [
                        {
                            **r,
                            "active": (r.get("username") == selected_active),
                        }
                        for r in current_rows
                    ]
                    save_login_lookup(final)
                    st.session_state._login_reload = True
                    if "active_account_select" in st.session_state:
                        del st.session_state["active_account_select"]
                    st.success("Active account updated!")
                    st.rerun()
        else:
            selected_active = None
            st.info("Add a new credential row below to get started.")

        st.markdown("")

        editor_data = [
            {
                "active": r.get("active", False),
                "bypass": r.get("bypass", False),
                "username": r.get("username", ""), 
                "auto_delete": r.get("auto_delete", False),
                "delete_range": r.get("delete_range", "Last hour"),
                "quota_full": r.get("quota_full", ""),
                "last_switched_at": r.get("last_switched_at", ""),
                "session_images":   r.get("session_images", ""),
                "session_refused":  r.get("session_refused", ""),
                "session_resets":   r.get("session_resets", ""),
            }
            for r in rows
        ]
        editor_df = pd.DataFrame(editor_data) if editor_data else pd.DataFrame(columns=["active", "bypass", "username", "auto_delete", "delete_range", "quota_full", "last_switched_at", "session_images", "session_refused", "session_resets"])

        # 这里的 width 设为 "content" 以确保紧凑且不报错
        edited_df = st.data_editor(
            editor_df,
            column_config={
                "active": st.column_config.CheckboxColumn(
                    "Active",
                    help="Current active account",
                    disabled=True,
                    width="small"
                ),
                "bypass": st.column_config.CheckboxColumn(
                    "Bypass",
                    help="Skip this account during automated looping",
                    width="small"
                ),
                "username": st.column_config.TextColumn("Username", width="medium"),
                "auto_delete": st.column_config.CheckboxColumn("Auto Delete", help="Auto delete history on switch", width="small"),
                "delete_range": st.column_config.SelectboxColumn("Range", options=["Last hour", "Last day", "All time"], help="Deletion time range", width="small"),
                "quota_full": st.column_config.TextColumn("Quota Full At", help="Date/time when quota was hit", width="stretch"),
                "last_switched_at": st.column_config.TextColumn("Switched At", help="Timestamp when this account was last switched away", width="medium"),
                "session_images":   st.column_config.NumberColumn("Images",  help="Images downloaded during this account's last session", width="small"),
                "session_refused":  st.column_config.NumberColumn("Refused", help="Refused count during this account's last session",   width="small"),
                "session_resets":   st.column_config.NumberColumn("Resets",  help="Reset count during this account's last session",     width="small"),
            },
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            height=430,
            key="login_editor"
        )

        # --- Instant save for all editable columns ---
        # st.data_editor has no per-column on_change; we compare before/after render.
        # Index-based patching is used so username renames are handled correctly.
        _INSTANT_COLS = [
            "bypass", "auto_delete", "delete_range", "username",
            "quota_full", "last_switched_at",
            "session_images", "session_refused", "session_resets"
        ]
        _row_count_same = (
            not editor_df.empty
            and not edited_df.empty
            and len(editor_df) == len(edited_df)
        )
        if _row_count_same:
            # Row-count unchanged: index-based patch (handles username renames safely)
            orig_check = editor_df[_INSTANT_COLS].reset_index(drop=True)
            new_check  = edited_df[_INSTANT_COLS].reset_index(drop=True)
            if not orig_check.equals(new_check):
                edited_records = edited_df.to_dict("records")
                patched = []
                for idx, disk_row in enumerate(rows):
                    if idx < len(edited_records):
                        e = edited_records[idx]
                        new_uname = str(e.get("username", disk_row.get("username", ""))).strip()
                        patched.append({
                            **disk_row,
                            "bypass":           bool(e.get("bypass", False)),
                            "auto_delete":      bool(e.get("auto_delete", False)),
                            "delete_range":     str(e.get("delete_range", disk_row.get("delete_range", "All time"))),
                            "username":         new_uname if new_uname else disk_row.get("username", ""),
                            "quota_full":       e.get("quota_full") if pd.notna(e.get("quota_full")) and e.get("quota_full") is not None else "",
                            "last_switched_at": e.get("last_switched_at") if pd.notna(e.get("last_switched_at")) and e.get("last_switched_at") is not None else "",
                            "session_images":   e.get("session_images") if pd.notna(e.get("session_images")) and e.get("session_images") is not None else "",
                            "session_refused":  e.get("session_refused") if pd.notna(e.get("session_refused")) and e.get("session_refused") is not None else "",
                            "session_resets":   e.get("session_resets") if pd.notna(e.get("session_resets")) and e.get("session_resets") is not None else "",
                        })
                    else:
                        patched.append(disk_row)
                save_login_lookup(patched)
                st.toast("Credentials updated.", icon="💾")
        elif not edited_df.empty:
            # Row count changed (row added or deleted): write full table immediately.
            # Filter out blank rows (username empty) to avoid phantom entries.
            records = edited_df.to_dict("records")
            valid = [r for r in records if str(r.get("username", "")).strip()]
            if valid:
                save_login_lookup(valid)
                st.toast("Credentials updated.", icon="💾")

        btn_reload, btn_clear, btn_clear_stats = st.columns([1, 1.2, 1.2])

        with btn_reload:
            if st.button("Reload Credentials Table", icon="🔄", type="secondary", width="stretch"):
                st.session_state._login_reload = True
                if "active_account_select" in st.session_state:
                    del st.session_state["active_account_select"]
                st.success("Credentials reloaded!")
                st.rerun()

        with btn_clear:
            if st.button("Clear Quota Full Recorded Date", icon="🧹", help="Manually reset all quota timestamps", type="secondary", width="stretch"):
                for r in rows:
                    r["quota_full"] = ""
                save_login_lookup(rows)
                st.session_state._login_reload = True
                st.success("All quota timestamps cleared!")
                st.rerun()

        with btn_clear_stats:
            if st.button("Reset Session Stats", icon="🧹", help="Clear all session statistics (Switched At, Images, Refused, Resets) for all accounts", type="secondary", width="stretch"):
                for r in rows:
                    r["last_switched_at"] = ""
                    r["session_images"]   = ""
                    r["session_refused"]  = ""
                    r["session_resets"]   = ""
                save_login_lookup(rows)
                st.session_state._login_reload = True
                st.success("All session stats cleared!")
                st.rerun()

        st.markdown("<p style='font-size: 0.8em; margin-bottom: 2px; margin-top: 10px; text-transform: uppercase;'>Batch Actions:</p>", unsafe_allow_html=True)
        b_col1, b_col2, b_col3, b_col4 = st.columns(4)

        with b_col1:
            if st.button("✓ All Bypass", type="secondary", width="stretch"):
                for r in rows: r["bypass"] = True
                save_login_lookup(rows)
                st.session_state._login_reload = True
                st.rerun()

        with b_col2:
            if st.button("✗ Clear Bypass", type="secondary", width="stretch"):
                for r in rows: r["bypass"] = False
                save_login_lookup(rows)
                st.session_state._login_reload = True
                st.rerun()

        with b_col3:
            if st.button("✓ All Auto Delete", type="secondary", width="stretch"):
                for r in rows: r["auto_delete"] = True
                save_login_lookup(rows)
                st.session_state._login_reload = True
                st.rerun()

        with b_col4:
            if st.button("✗ Clear Auto Delete", type="secondary", width="stretch"):
                for r in rows: r["auto_delete"] = False
                save_login_lookup(rows)
                st.session_state._login_reload = True
                st.rerun()

# --- Technical Details ---
with st.expander("Technical Details (config.json)"):
    st.json(config)

with st.expander("Technical Details (user_login_lookup.json)"):
    st.json(load_login_lookup())