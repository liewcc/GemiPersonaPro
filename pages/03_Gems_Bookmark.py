import streamlit as st
import json
import os
import asyncio
import time
from api_client import EngineClient
from style_utils import apply_premium_style, render_dashboard_header

# --- CONFIGURATION ---
DB_FILE = "Gems_bookmark.json"
CONFIG_PATH = "config.json"

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

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(updates):
    cfg = load_config()
    cfg.update(updates)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)
    return cfg

async def check_busy(client):
    """Checks if the engine is busy with manual or automated tasks via health endpoint."""
    try:
        health = await client.check_health()
        if health and health.get("is_busy"):
            # Check automation specifically for more detailed msg if possible
            stats = await client.get_automation_stats()
            if stats.get("is_running"):
                return True, "Automation is currently running."
            return True, "A manual browser operation is currently in progress."
        return False, ""
    except Exception as e:
        return False, f"Busy check failed: {e}"


def main():
    st.set_page_config(page_title="GemiPersona | GEMS BOOKMARK", page_icon="🔖", layout="wide")
    apply_premium_style()
    # render_dashboard_header removed as requested

    if "client" not in st.session_state:
        st.session_state.client = EngineClient()
    
    if "edit_index" not in st.session_state: st.session_state.edit_index = None
    if "temp_name" not in st.session_state: st.session_state.temp_name = ""
    if "temp_desc" not in st.session_state: st.session_state.temp_desc = ""

    bookmarks = load_json(DB_FILE) or []
    is_edit_mode = st.session_state.edit_index is not None

    # --- EDITOR SECTION ---
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>GEM EDITOR</p>", unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("Edit Bookmark" if is_edit_mode else "Add New Bookmark")
        
        # URL Input
        default_url = bookmarks[st.session_state.edit_index]["url"] if is_edit_mode else ""
        url = st.text_input("URL", value=default_url, placeholder="https://gemini.google.com/app/gems/...")
        
        # Auto-Fetch Button
        if st.button("🔍 Auto-Fetch Details via Engine", width='stretch'):
            if url:
                async def do_fetch():
                    # Navigation is required to fetch info
                    with st.status("Engine is navigating and scraping Gem info...", expanded=True) as status:
                        try:
                            # 1. Check health
                            health = await st.session_state.client.check_health()
                            if not health or not health.get("engine_running"):
                                status.update(label="Error: Browser engine is not running. Please start it from HOME.", state="error")
                                return
                            
                            # 2. Check busy
                            is_busy, msg = await check_busy(st.session_state.client)
                            if is_busy:
                                status.update(label=f"Busy: {msg}", state="error")
                                return

                            # 3. Navigate
                            status.update(label=f"Navigating to {url}...")
                            await st.session_state.client.navigate(url)
                            
                            # 4. Extract
                            status.update(label="Extracting Gem details...")
                            # Polling for a few seconds as per old version logic
                            for i in range(5):
                                await asyncio.sleep(2)
                                res = await st.session_state.client.get_gem_info()
                                if res.get("status") == "success" and res.get("name") and res.get("name") != "Unknown Gem":
                                    st.session_state.temp_name = res.get("name", "")
                                    st.session_state.temp_desc = res.get("description", "")
                                    status.update(label="Fetch Successful!", state="complete")
                                    return
                            
                            status.update(label="Extraction timed out or failed to find Gem details.", state="error")
                        except Exception as e:
                            status.update(label=f"Fetch Failed: {e}", state="error")

                asyncio.run(do_fetch())
                st.rerun()
            else:
                st.error("Please enter a URL first.")

        # Display Logic: Priority -> Temp Data > Existing Bookmark Data > Empty
        if is_edit_mode:
            display_name = st.session_state.temp_name if st.session_state.temp_name else bookmarks[st.session_state.edit_index]["name"]
            display_desc = st.session_state.temp_desc if st.session_state.temp_desc else bookmarks[st.session_state.edit_index]["description"]
        else:
            display_name = st.session_state.temp_name
            display_desc = st.session_state.temp_desc

        col_name, _ = st.columns([1, 1])
        with col_name:
            name = st.text_input("Bookmark Name", value=display_name)
        
        description = st.text_area("Description", value=display_desc)
        
        # Action Buttons
        btn_col1, btn_col2 = st.columns([1, 5])
        with btn_col1:
            if st.button("Save", type="primary", width='stretch'):
                if not name or not url:
                    st.error("Name and URL are required.")
                else:
                    new_entry = {"name": name, "url": url, "description": description}
                    if is_edit_mode:
                        bookmarks[st.session_state.edit_index] = new_entry
                    else:
                        bookmarks.append(new_entry)
                    
                    if save_json(DB_FILE, bookmarks):
                        # Clear states after save
                        st.session_state.edit_index = None
                        st.session_state.temp_name = ""
                        st.session_state.temp_desc = ""
                        st.success("Saved!")
                        time.sleep(1)
                        st.rerun()
        with btn_col2:
            if is_edit_mode and st.button("Cancel"):
                st.session_state.edit_index = None
                st.session_state.temp_name = ""
                st.session_state.temp_desc = ""
                st.rerun()

    st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
    
    # --- GALLERY SECTION ---
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>SAVED BOOKMARKS</p>", unsafe_allow_html=True)
    with st.container(border=True):
        if not bookmarks:
            st.info("No bookmarks yet. Add one above!")
        else:
            # Grid of 2 columns for a cleaner list view
            for index, b in enumerate(bookmarks):
                with st.container(border=True):
                    st.markdown(f"**{b['name']}**")
                    if b['description']:
                        st.markdown(f"<p style='color: #aaa; font-size: 0.9em; margin: 0;'>{b['description']}</p>", unsafe_allow_html=True)
                    st.markdown(f"<code style='color: #666; font-size: 0.8em;'>{b['url']}</code>", unsafe_allow_html=True)
                    
                    # Action buttons: Apply | Edit | Delete
                    a_col, e_col, d_col, _ = st.columns([1, 1, 1, 5])
                    with a_col:
                        if st.button("Apply", key=f"apply_{index}", width="stretch"):
                            # BUSY GUARD: Block update if engine is busy
                            is_busy, msg = asyncio.run(check_busy(st.session_state.client))
                            if is_busy:
                                st.error(f"**WAIT:** {msg}\nChanging configuration during an active process is blocked.")
                            else:
                                # Update config locally without browser navigation
                                save_config({"browser_url": b['url']})
                                st.toast(f"Applied {b['name']} to configuration!")
                                time.sleep(1)
                                st.rerun()

                    with e_col:
                        if st.button("Edit", key=f"ed_{index}", width='stretch'):
                            st.session_state.temp_name = ""
                            st.session_state.temp_desc = ""
                            st.session_state.edit_index = index
                            st.rerun()
                    with d_col:
                        if st.button("Delete", key=f"de_{index}", width='stretch'):
                            bookmarks.pop(index)
                            save_json(DB_FILE, bookmarks)
                            st.rerun()


if __name__ == "__main__":
    main()
