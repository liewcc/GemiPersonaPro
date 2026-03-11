import streamlit as st
import json
import os
import asyncio
import time
import sys
import nest_asyncio
from api_client import EngineClient
from style_utils import apply_premium_style, render_dashboard_header
from config_utils import save_config

# Fix for Windows asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

nest_asyncio.apply()

# --- CONFIGURATION ---
DB_FILE = "Gems_bookmark.json"

def load_json(file_path):
    if not os.path.exists(file_path): return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error reading {file_path}: {e}")
    return None

def save_json(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        st.error(f"Error saving {file_path}: {e}")
    return False

async def check_busy(client):
    status = await client.check_health()
    if not status: return False, ""
    if status.get("automation_running"): return True, "Automation is currently running."
    if status.get("manual_operation_in_progress"): return True, "A manual browser operation is currently in progress."
    return False, ""

def main():
    st.set_page_config(page_title="Gems Bookmark", page_icon="🔖", layout="wide")
    apply_premium_style()

    # --- SESSION STATE INITIALIZATION ---
    if "client" not in st.session_state: st.session_state.client = EngineClient()
    if "edit_index" not in st.session_state: st.session_state.edit_index = None

    # --- ENGINE HEALTH & SAFETY ---
    health = asyncio.run(st.session_state.client.check_health())
    engine_running = health.get("engine_running", False) if health else False
    # Fetching both health and automation stats for a robust picture
    auto_stats = asyncio.run(st.session_state.client.get_automation_stats())
    auto_active = auto_stats.get("is_running", False) if auto_stats else False

    # Sync values from 'load_target' keys (set by buttons later in the script)
    if "load_target_url" in st.session_state:
        st.session_state.url_bar_widget = st.session_state.pop("load_target_url")
    if "load_target_name" in st.session_state:
        st.session_state.gem_name_key = st.session_state.pop("load_target_name")
    if "load_target_desc" in st.session_state:
        st.session_state.gem_desc_key = st.session_state.pop("load_target_desc")

    # Default widget keys if not set
    if "gem_name_key" not in st.session_state: st.session_state.gem_name_key = ""
    if "gem_desc_key" not in st.session_state: st.session_state.gem_desc_key = ""
    if "url_bar_widget" not in st.session_state: st.session_state.url_bar_widget = ""

    bookmarks = load_json(DB_FILE) or []
    is_edit_mode = st.session_state.edit_index is not None

    # Handle Edit Mode specific loading
    if is_edit_mode and not st.session_state.gem_name_key and not st.session_state.gem_desc_key:
        st.session_state.gem_name_key = bookmarks[st.session_state.edit_index]["name"]
        st.session_state.gem_desc_key = bookmarks[st.session_state.edit_index]["description"]
        st.session_state.url_bar_widget = bookmarks[st.session_state.edit_index]["url"]

    # --- GEM SCANNER (CLONED FROM GEMINI SETUP) ---
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>GEM SCANNER (BROWSER URL)</p>", unsafe_allow_html=True)
    with st.container(border=True):
        st.text_input("URL Input", key="url_bar_widget", label_visibility="collapsed", placeholder="https://gemini.google.com/app/gems/...")
        
        # Immediate Result Display (Like Gemini Setup Title)
        if st.session_state.gem_name_key:
            st.markdown(f"**Extracted Name:** {st.session_state.gem_name_key}")
            if st.session_state.gem_desc_key:
                st.caption(f"**Description:** {st.session_state.gem_desc_key}")
        else:
            st.caption("Press 'Send to Browser & Extract' to begin." if not auto_active else "⚠️ Scanner disabled while Automation is running.")

        # Action Buttons for Scanner
        u_col1, u_col2 = st.columns([1, 1])
        with u_col1:
            if st.button("Send to Browser & Extract", key="url_send", width="stretch", disabled=auto_active):
                if st.session_state.url_bar_widget:
                    async def do_nav():
                        target_url = st.session_state.url_bar_widget
                        
                        # Navigate
                        await st.session_state.client.navigate(target_url)
                        
                        # Stabilization (The 'Secret Sauce' from Setup)
                        if "gemini.google.com" in target_url:
                            await st.session_state.client.discover_capabilities()
                        
                        # Extraction Buffer
                        await asyncio.sleep(5.0)
                        res = await st.session_state.client.get_gem_info()
                        
                        if res.get("status") == "success":
                            st.session_state.gem_name_key = res.get("name", "Unknown Gem")
                            st.session_state.gem_desc_key = res.get("description", "")
                            st.toast("Extracted Gem info successfully!", icon="✅")
                        else:
                            st.error(f"Extraction failed: {res.get('message', 'Unknown error')}")
                    
                    asyncio.run(do_nav())
                    st.rerun()
                else:
                    st.error("Please enter a URL first.")
        
        with u_col2:
            if st.button("Clear Scanner", width="stretch", disabled=auto_active):
                st.session_state.edit_index = None
                for k in ["url_bar_widget", "gem_name_key", "gem_desc_key"]:
                    if k in st.session_state: del st.session_state[k]
                st.rerun()

    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

    # --- GEM DETAILS (EDITOR) ---
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>GEM DETAILS</p>", unsafe_allow_html=True)
    with st.container(border=True):
        st.caption("Confirm or edit the details below before saving.")
        
        name = st.text_input("Bookmark Name", key="gem_name_key")
        description = st.text_area("Description", key="gem_desc_key")
        url = st.session_state.url_bar_widget
        
        # Save / Cancel
        btn_col1, btn_col2 = st.columns([1, 5])
        with btn_col1:
            if st.button("Save Bookmark", type="primary", width='stretch', disabled=auto_active):
                if not name or not url:
                    st.error("Name and URL are required.")
                else:
                    new_entry = {"name": name, "url": url, "description": description}
                    if is_edit_mode:
                        bookmarks[st.session_state.edit_index] = new_entry
                    else:
                        bookmarks.append(new_entry)
                    
                    if save_json(DB_FILE, bookmarks):
                        st.session_state.edit_index = None
                        for k in ["gem_name_key", "gem_desc_key", "url_bar_widget"]:
                            if k in st.session_state: del st.session_state[k]
                        st.success("Saved!")
                        time.sleep(0.5)
                        st.rerun()
        
        with btn_col2:
            if is_edit_mode and st.button("Cancel Edit", disabled=auto_active):
                st.session_state.edit_index = None
                for k in ["gem_name_key", "gem_desc_key", "url_bar_widget"]:
                    if k in st.session_state: del st.session_state[k]
                st.rerun()

    st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
    
    # --- GALLERY SECTION ---
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>SAVED BOOKMARKS</p>", unsafe_allow_html=True)
    with st.container(border=True):
        if not bookmarks:
            st.info("No bookmarks yet. Add one above!")
        else:
            for index, b in enumerate(bookmarks):
                with st.container(border=True):
                    col_info, col_actions = st.columns([4, 1])
                    with col_info:
                        st.markdown(f"**{b['name']}**")
                        if b['description']:
                            st.markdown(f"<p style='color: #aaa; font-size: 0.9em; margin: 0;'>{b['description']}</p>", unsafe_allow_html=True)
                        st.markdown(f"<code style='color: #666; font-size: 0.8em;'>{b['url']}</code>", unsafe_allow_html=True)
                    
                    with col_actions:
                        s_col, e_col, d_col = st.columns(3)
                        with s_col:
                            if st.button("Send", key=f"snd_{index}", width='stretch', help="Update global config URL", disabled=auto_active):
                                save_config({"browser_url": b["url"]})
                                st.session_state["load_target_url"] = b["url"]
                                st.toast(f"Config updated: {b['name']}", icon="🚀")
                                time.sleep(0.5)
                                st.rerun()
                        with e_col:
                            if st.button("Edit", key=f"ed_{index}", width='stretch', disabled=auto_active):
                                st.session_state.edit_index = index
                                # Deleting keys allows the init block at top to reload them from bookmarks
                                for k in ["gem_name_key", "gem_desc_key", "url_bar_widget"]:
                                    if k in st.session_state: del st.session_state[k]
                                st.rerun()
                        with d_col:
                            if st.button("Delete", key=f"del_{index}", width='stretch', disabled=auto_active):
                                bookmarks.pop(index)
                                save_json(DB_FILE, bookmarks)
                                st.rerun()

if __name__ == "__main__":
    main()
