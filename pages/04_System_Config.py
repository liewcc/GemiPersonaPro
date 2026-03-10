import streamlit as st
import json
import os
import pandas as pd
from style_utils import apply_premium_style, render_dashboard_header
from config_utils import load_config as load_cfg_disk, save_config as save_cfg_disk

# --- Page Config ---
st.set_page_config(page_title="GemiPersona | System Config", page_icon="⚙️", layout="wide")
apply_premium_style()

CONFIG_PATH = "config.json"
LOGIN_LOOKUP_PATH = "user_login_lookup.json"

# --- Data Loading Functions ---
def load_config():
    return load_cfg_disk()

def load_login_lookup():
    if os.path.exists(LOGIN_LOOKUP_PATH):
        try:
            with open(LOGIN_LOOKUP_PATH, "r") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except:
            pass
    return []

def save_config(updates):
    return save_cfg_disk(updates)

def save_login_lookup(data):
    with open(LOGIN_LOOKUP_PATH, "w") as f:
        json.dump(data, f, indent=4)

# --- Engine Config Callbacks ---
def on_change_console():
    save_config({"show_engine_console": st.session_state.cfg_show_console})

def on_change_headless():
    save_config({"headless": st.session_state.cfg_headless})

def on_change_timeout():
    save_config({"heartbeat_timeout": st.session_state.cfg_timeout})

# --- Main Logic ---

config = load_config()
login_data = load_login_lookup()

# --- Page Entry Detection & Force Reload ---
if st.session_state.get("_last_config_page") != "System_Config":
    st.session_state._last_config_page = "System_Config"
    
    # Force fresh reload from disk to ensure we have the latest data
    config = load_config()
    login_data = load_login_lookup()
    
    # Overwrite session state with latest config values
    st.session_state.cfg_show_console = config.get("show_engine_console", True)
    st.session_state.cfg_headless = config.get("headless", False)
    st.session_state.cfg_timeout = config.get("heartbeat_timeout", 3600)
    
    # Force reload of login rows and clear any unsaved editor states
    st.session_state.login_rows = list(login_data)
    st.session_state._login_reload = False
    
    # Clear Streamlit data_editor widget states to discard unsaved UI edits
    if "quota_editor" in st.session_state:
        del st.session_state["quota_editor"]
    if "login_editor" in st.session_state:
        del st.session_state["login_editor"]

# Ensure keys exist if it IS the first run of the session
if "cfg_show_console" not in st.session_state:
    st.session_state.cfg_show_console = config.get("show_engine_console", True)
if "cfg_headless" not in st.session_state:
    st.session_state.cfg_headless = config.get("headless", False)
if "cfg_timeout" not in st.session_state:
    st.session_state.cfg_timeout = config.get("heartbeat_timeout", 3600)

# Section 1: Engine Settings
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

# Section 2: Quota Detection Settings
st.subheader("Quota Full Phrases")
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
        key="quota_editor"
    )

    if st.button("Save Quota Phrases", icon="📝"):
        new_phrases = edited_quota_df["phrase"].tolist()
        new_phrases = [p.strip() for p in new_phrases if p.strip()]
        save_config({"quota_full": new_phrases})
        st.success("Quota phrases updated!")
        st.rerun()

# Section 3: Credential Management
st.subheader("User Login Credentials")
with st.container(border=True):
    # login_rows is now handled by the page entry reload logic at the top,
    # but we keep this check for manual trigger or safety.
    if "login_rows" not in st.session_state or st.session_state.get("_login_reload"):
        st.session_state.login_rows = list(login_data)
        st.session_state._login_reload = False

    rows = st.session_state.login_rows
    usernames = [r.get("username", "") for r in rows if r.get("username")]

    active_index = 0
    for i, r in enumerate(rows):
        if r.get("active"):
            active_index = i
            break

    if usernames:
        selected_active = st.selectbox(
            "Active Account",
            options=usernames,
            index=min(active_index, len(usernames) - 1),
            help="Select the account to use for the current session",
            key="active_account_select"
        )
    else:
        selected_active = None
        st.info("Add a new credential row below to get started.")

    st.markdown("")

    editor_data = [
        {
            "active": r.get("active", False), 
            "username": r.get("username", ""), 
            "note": r.get("note", ""),
            "quota_full": r.get("quota_full", "")
        }
        for r in rows
    ]
    editor_df = pd.DataFrame(editor_data) if editor_data else pd.DataFrame(columns=["active", "username", "note", "quota_full"])

    # 这里的 width 设为 "content" 以确保紧凑且不报错
    edited_df = st.data_editor(
        editor_df,
        column_config={
            "active": st.column_config.CheckboxColumn(
                "Active Credential",
                help="Current active account",
                disabled=True
            ),
            "username": st.column_config.TextColumn("Username"),
            "note": st.column_config.TextColumn("Note"),
            "quota_full": st.column_config.TextColumn("Quota Full At", help="Date/time when quota was hit", width="stretch", disabled=True),
        },
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key="login_editor"
    )

    btn_save, btn_reload, btn_clear = st.columns([1.2, 1.2, 1.6])

    with btn_save:
        if st.button("Save Credentials Table", icon="🔒", type="primary", width="stretch"):
            records = edited_df.to_dict("records")
            records = [r for r in records if r.get("username") or r.get("note")]
            
            # Map existing quota_full if not present in records 
            # (though it should be there as a column)
            final = [
                {"active": (r.get("username") == selected_active),
                 "username": r.get("username", ""),
                 "note": r.get("note", ""),
                 "quota_full": r.get("quota_full", "")}
                for r in records
            ]
            save_login_lookup(final)
            st.session_state._login_reload = True
            if "active_account_select" in st.session_state:
                del st.session_state["active_account_select"]
            st.success("Credentials saved!")
            st.rerun()

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

# --- Technical Details ---
with st.expander("Technical Details (config.json)"):
    st.json(config)

with st.expander("Technical Details (user_login_lookup.json)"):
    st.json(load_login_lookup())