import streamlit as st
import os
import time
import json
import datetime
import tkinter as tk
import re
from tkinter import filedialog
from PIL import Image, PngImagePlugin
import asyncio

# --- Helper Functions & Nav Helpers ---
import base64

def natural_sort_key(s):
    """Helper for natural alphanumeric string sorting."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def sync_san_page(new_page):
    st.session_state.san_gal_page = new_page
    st.session_state.san_gal_page_top_widget = new_page
    st.session_state.san_gal_page_bot_widget = new_page
    st.session_state.san_gal_page_top = new_page
    st.session_state.san_gal_page_bot = new_page

def on_san_page_top_change():
    sync_san_page(st.session_state.san_gal_page_top_widget)

def on_san_page_bot_change():
    sync_san_page(st.session_state.san_gal_page_bot_widget)

def on_san_page_size_change():
    st.session_state.san_gal_page_size = st.session_state.san_page_size_slider
    sync_san_page(1)

def select_path(is_folder=True):
    """Opens a native Windows file/folder picker."""
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes('-topmost', True)
    if is_folder:
        path = filedialog.askdirectory()
    else:
        path = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp")])
    root.destroy()
    return path

def get_consolidated_metadata(img):
    """Extracts and consolidates metadata, especially for PNGs with redundant XMP keys."""
    raw_info = img.info.copy()
    meta = {}
    for k, v in raw_info.items():
        if k == "exif": continue
        val_str = v.decode('utf-8', errors='ignore') if isinstance(v, bytes) else str(v)
        if k == 'xmp' and 'XML:com.adobe.xmp' in raw_info:
            continue 
        meta[k] = val_str
    return meta

@st.fragment
def batch_processing_sidebar_fragment():
    """Sidebar fragment for batch processing, moved to global scope per rule.md for stability."""
    st.markdown("### Batch Processing")
    with st.container(border=True):
        if st.button("🪄 Batch Remove Watermarks", key="san_batch_rm_btn_frag", width="stretch", 
                     disabled=not st.session_state.sanitizer_is_dir):
            st.session_state.show_batch_dialog = True
            st.rerun(scope="fragment")
    
    if st.session_state.show_batch_dialog:
        batch_watermark_removal_dialog(st.session_state.sanitizer_path)

# --- Initialize Session State ---
if "config" not in st.session_state:
    st.session_state.config = load_config()
if "client" not in st.session_state:
    st.session_state.client = EngineClient()
if "sanitizer_path" not in st.session_state:
    st.session_state.sanitizer_path = ""
if "sanitizer_is_dir" not in st.session_state:
    st.session_state.sanitizer_is_dir = False

# --- Batch Processing State ---
if "batch_last_index" not in st.session_state: st.session_state.batch_last_index = 0
if "batch_is_running" not in st.session_state: st.session_state.batch_is_running = False
if "batch_stop_requested" not in st.session_state: st.session_state.batch_stop_requested = False
if "show_batch_dialog" not in st.session_state: st.session_state.show_batch_dialog = False
if "batch_files" not in st.session_state: st.session_state.batch_files = []

# --- Gallery Pagination State ---
if "san_gal_page" not in st.session_state: st.session_state.san_gal_page = 1
if "san_gal_page_size" not in st.session_state: st.session_state.san_gal_page_size = 8
if "san_gal_page_top" not in st.session_state: st.session_state.san_gal_page_top = 1
if "san_gal_page_bot" not in st.session_state: st.session_state.san_gal_page_bot = 1

# --- Sync Widget Keys with State on Initial Load/Rerun ---
if "san_gal_page_top_widget" not in st.session_state: st.session_state.san_gal_page_top_widget = st.session_state.san_gal_page
if "san_gal_page_bot_widget" not in st.session_state: st.session_state.san_gal_page_bot_widget = st.session_state.san_gal_page

if "san_sort_by" not in st.session_state: st.session_state.san_sort_by = "Name"
if "san_sort_desc" not in st.session_state: st.session_state.san_sort_desc = False
if "_edit_dialog_ver" not in st.session_state: st.session_state["_edit_dialog_ver"] = 0

# --- Page Persistence & Reset Logic ---
if "last_page" not in st.session_state:
    st.session_state.last_page = "Asset Sanitizer"
# --- Navigation & State Reset Logic ---
st.session_state.show_batch_dialog = False
st.session_state.batch_is_running = False
st.session_state.batch_stop_requested = False

# --- Force-Sync & Pre-calculate Gallery State ---
# Force sync widget keys with current shared state
st.session_state.san_gal_page_top_widget = st.session_state.san_gal_page
st.session_state.san_gal_page_bot_widget = st.session_state.san_gal_page

san_total_pages = 1
san_all_files = []
san_current_folder = ""

if st.session_state.sanitizer_is_dir and st.session_state.sanitizer_path and os.path.isdir(st.session_state.sanitizer_path):
    san_current_folder = st.session_state.sanitizer_path
    if st.session_state.san_show_cleaned:
        san_current_folder = os.path.join(san_current_folder, "processed")
    
    try:
        if os.path.isdir(san_current_folder):
            raw_files = [f for f in os.listdir(san_current_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
            
            # Apply Sorting
            sort_by = st.session_state.san_sort_by
            desc = st.session_state.san_sort_desc
            if sort_by == "Name":
                san_all_files = sorted(raw_files, key=natural_sort_key, reverse=desc)
            elif sort_by == "Create Date":
                san_all_files = sorted(raw_files, key=lambda x: os.path.getctime(os.path.join(san_current_folder, x)), reverse=desc)
            else:  # Modified Date (default)
                san_all_files = sorted(raw_files, key=lambda x: os.path.getmtime(os.path.join(san_current_folder, x)), reverse=desc)
            
            p_size = st.session_state.san_gal_page_size
            san_total_pages = max(1, (len(san_all_files) + p_size - 1) // p_size)
    except:
        pass

# Ensure current page is valid after sort/folder changes
if st.session_state.san_gal_page > san_total_pages:
    sync_san_page(san_total_pages)

# --- Custom Utilities (Legacy load order protection) ---
from style_utils import apply_premium_style, render_dashboard_header
from config_utils import load_config, save_config
from api_client import EngineClient
import shared_state

CONFIG_PATH = "config.json"
st.set_page_config(page_title="GemiPersona | ASSET SANITIZER", page_icon="sys_img/logo.png", layout="wide", initial_sidebar_state="expanded")
apply_premium_style()

# --- CSS FOR CLEAN DASHBOARD LOOK ---
st.markdown("""
    <style>
    /* 1. Hide Streamlit Chrome */
    [data-testid="stFooter"], footer {
        display: none !important;
        height: 0 !important;
    }

    /* 2. Start vertically at top in main panel */
    [data-testid="stMain"] {
        display: flex !important;
        flex-direction: column !important;
        justify-content: flex-start !important;
        min-height: 100vh !important;
    }

    /* 3. Global Image Cap to prevent scrolling */
    [data-testid="stMain"] img {
        max-height: 450px !important;
        width: auto;
        object-fit: contain !important;
        margin: 0 auto;
        display: block;
        text-align: center;
    }
    
    /* Center the stImage container itself */
    [data-testid="stMain"] [data-testid="stImage"] {
        text-align: center !important;
        display: flex !important;
        justify-content: center !important;
    }
    
    /* 4. Ensure container padding is natural */
    [data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0 !important;
    }

    /* 5. Borderless sidebar nav buttons (Dashboard Style) */
    /* We use 'primary' kind exclusively for the pagination arrows so we can target them. */
    [data-testid="stSidebar"] button[kind="primary"] {
        border: none !important;
        background-color: transparent !important;
        box-shadow: none !important;
        color: #444 !important;
        font-size: 1.4rem !important;
        padding: 0px !important;
        min-height: unset !important;
        height: auto !important;
    }
    [data-testid="stSidebar"] button[kind="primary"]:hover {
        color: #0366d6 !important;
        background-color: transparent !important;
    }
    [data-testid="stSidebar"] button[kind="primary"]:disabled {
        color: rgba(68, 68, 68, 0.3) !important;
        background-color: transparent !important;
    }

    </style>
""", unsafe_allow_html=True)

def save_metadata_final(file_path, new_metadata, preserve_dates=True):
    """Saves metadata while preserving original file timestamps."""
    try:
        import gc
        stats = os.stat(file_path)
        atime, mtime = stats.st_atime, stats.st_mtime
        
        with Image.open(file_path) as img:
            fmt = img.format
            mode = img.mode
            size = img.size
            png_meta = PngImagePlugin.PngInfo()
            for k, v in new_metadata.items():
                if v and str(v).strip():
                    png_meta.add_text(str(k), str(v))
            
            clean_img = Image.new(mode, size)
            clean_img.paste(img)
            exif = img.info.get("exif")
            if "transparency" in img.info:
                clean_img.info["transparency"] = img.info["transparency"]
        
        gc.collect()
        backup_path = file_path + ".bak"
        save_params = {"format": fmt}
        if fmt == "PNG": save_params["pnginfo"] = png_meta
        if exif: save_params["exif"] = exif
        
        clean_img.save(backup_path, **save_params)
        
        # Atomic Swap with retries for Windows
        def atomic_swap():
            if os.path.exists(file_path):
                os.remove(file_path)
            os.rename(backup_path, file_path)
            if preserve_dates:
                os.utime(file_path, (atime, mtime))
                # Restore creation time on Windows
                if os.name == 'nt':
                    import ctypes
                    from ctypes import wintypes
                    kernel32 = ctypes.windll.kernel32
                    FILE_WRITE_ATTRIBUTES, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS = 0x0100, 3, 0x02000000
                    def to_filetime(dt):
                        val = int((dt + 11644473600) * 10000000)
                        return wintypes.FILETIME(val & 0xFFFFFFFF, val >> 32)
                    ft_creation, ft_access, ft_write = to_filetime(stats.st_ctime), to_filetime(stats.st_atime), to_filetime(stats.st_mtime)
                    handle = kernel32.CreateFileW(file_path, FILE_WRITE_ATTRIBUTES, 0, None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, 0)
                    if handle != -1:
                        kernel32.SetFileTime(handle, ctypes.byref(ft_creation), ctypes.byref(ft_access), ctypes.byref(ft_write))
                        kernel32.CloseHandle(handle)

        for i in range(10):
            try:
                atomic_swap()
                break
            except Exception as e:
                if i == 9: raise e
                time.sleep(0.5)
                gc.collect()
        
        return True, "Success"
    except Exception as e:
        if 'backup_path' in locals() and os.path.exists(backup_path):
            try: os.remove(backup_path)
            except: pass
        return False, str(e)

def get_remover(): return shared_state.get_shared_remover()
def get_refiner(): return shared_state.get_shared_refiner()

def save_with_metadata(p_img, original_img, output_path_or_buf, original_stats=None):
    from PIL import PngImagePlugin
    save_params = {}
    if original_img.format == "PNG":
        meta = PngImagePlugin.PngInfo()
        for k, v in original_img.info.items():
            if isinstance(k, str) and k != "exif": meta.add_text(k, str(v))
        save_params["pnginfo"] = meta
    exif = original_img.info.get('exif')
    if not exif and hasattr(original_img, "getexif"): 
        exif_data = original_img.getexif()
        if exif_data: exif = exif_data.tobytes()
    if exif: save_params["exif"] = exif
    save_params["info"] = original_img.info.copy()
    
    def perform_save():
        if isinstance(output_path_or_buf, str):
            p_img.save(output_path_or_buf, **save_params)
            if original_stats:
                os.utime(output_path_or_buf, (original_stats.st_atime, original_stats.st_mtime))
                if os.name == 'nt':
                    import ctypes
                    from ctypes import wintypes
                    kernel32 = ctypes.windll.kernel32
                    FILE_WRITE_ATTRIBUTES, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS = 0x0100, 3, 0x02000000
                    def to_filetime(dt):
                        val = int((dt + 11644473600) * 10000000)
                        return wintypes.FILETIME(val & 0xFFFFFFFF, val >> 32)
                    ft_creation, ft_access, ft_write = to_filetime(original_stats.st_ctime), to_filetime(original_stats.st_atime), to_filetime(original_stats.st_mtime)
                    handle = kernel32.CreateFileW(output_path_or_buf, FILE_WRITE_ATTRIBUTES, 0, None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, 0)
                    if handle != -1:
                        kernel32.SetFileTime(handle, ctypes.byref(ft_creation), ctypes.byref(ft_access), ctypes.byref(ft_write))
                        kernel32.CloseHandle(handle)
        else:
            p_img.save(output_path_or_buf, format="PNG", **save_params)

    # Retry loop for Windows file locks
    for i in range(10):
        try:
            perform_save()
            break
        except Exception as e:
            if i == 9: raise e
            time.sleep(0.5)
            import gc
            gc.collect()

@st.dialog("⚠️ Model Busy")
def show_model_busy_warning_dialog():
    st.warning("Manual edit is currently unavailable. Stop automation first.")
    if st.button("Understood", width="stretch", type="primary"): st.rerun()

@st.dialog("⚠️ Missing Folder")
def show_missing_processed_warning_dialog():
    st.warning("The `processed` subfolder does not exist in the current directory. Please run batch removal first.")
    if st.button("Understood", width="stretch", type="primary"): 
        st.session_state.san_show_cleaned = False
        st.rerun()

@st.dialog("\u200b", width="large")
def manual_watermark_removal_dialog(file_path):
    if "manual_removal_preview_id" not in st.session_state: st.session_state.manual_removal_preview_id = 0
    if "manual_removal_preview" not in st.session_state: st.session_state.manual_removal_preview = {"hash": None, "img": None}
    filename = os.path.basename(file_path)
    
    save_dir = os.path.dirname(file_path)
    # Recursion Prevention: If already in 'processed', use current folder
    if os.path.basename(save_dir.rstrip("/\\")).lower() == "processed":
        processed_dir = save_dir
    else:
        processed_dir = os.path.join(save_dir, "processed")
    os.makedirs(processed_dir, exist_ok=True)
    
    try: from streamlit_drawable_canvas import st_canvas
    except: st.error("Missing library."); return
    try: 
        original_img = Image.open(file_path)
    except: st.error("Failed to load image."); return

    # --- Exhaustive Monkeypatch for Streamlit Compatibility ---
    try:
        import streamlit.elements.image as st_image
        if not hasattr(st_image, 'image_to_url'):
            found_func = None
            for path in ["streamlit.runtime.image_util", "streamlit.elements.image_utils", "streamlit.elements.lib.image_utils"]:
                try:
                    mod = __import__(path, fromlist=['image_to_url'])
                    if hasattr(mod, 'image_to_url'): found_func = mod.image_to_url; break
                except ImportError: continue
            if found_func:
                def compatible_image_to_url(data, width=-1, height=-1, *args, **kwargs):
                    if isinstance(width, int):
                        class FakeLayout:
                            def __init__(self, w, h): self.width, self.height = w, h
                        import hashlib
                        image_id = hashlib.md5(str(id(data)).encode()).hexdigest()
                        return found_func(data, FakeLayout(width, height), image_id, *args, **kwargs)
                    return found_func(data, width, height, *args, **kwargs)
                st_image.image_to_url = compatible_image_to_url
                try:
                    import streamlit.elements.lib.image_utils as lib_utils
                    lib_utils.image_to_url = compatible_image_to_url
                except ImportError: pass
    except Exception as e: pass

    # Brush Size slider removed from top as requested
    

    w, h = original_img.size
    max_w = 520  # Adjusted for better fit in "large" dialog columns
    scale = min(1.0, max_w / w)
    canvas_w, canvas_h = int(w * scale), int(h * scale)
    
    # --- Persistence Logic for Batch Settings ---
    if "p_wr_settings" not in st.session_state:
        # Defaults based on 04_Watermark_Removal.py and config
        st.session_state.p_wr_settings = {
            "approach": st.session_state.config.get("automation", {}).get("remove_watermark_approach", "Hybrid (Clean + Refine)"),
            "logo_val": 255.0,
            "alpha_con": 1.0,
            "off_x": 0,
            "off_y": 0,
            "refine_extra": 0.0,
            "brush_size": 25
        }
    settings = st.session_state.p_wr_settings

    # 1. Approach Selection (Radio) + Save Button in one row
    approaches = ["Inverse Alpha (Lossless)", "LaMa Inpainting (AI)", "Hybrid (Clean + Refine)", "Manual (Brush Only)"]
    prev_approach = settings["approach"]
    
    row1_cols = st.columns([4, 2.5])
    with row1_cols[0]:
        selected_approach = st.radio("Choose approach:", approaches, index=approaches.index(prev_approach), horizontal=True, label_visibility="collapsed")
    
    with row1_cols[1]:
        if st.button("💾 Save Settings for Batch Processing", help="Save settings for batch processing", width="stretch"):
            # Update config with these settings for future use
            updates = {
                "automation": {
                    "remove_watermark_approach": selected_approach,
                    "logo_value": settings["logo_val"],
                    "alpha_contrast": settings["alpha_con"],
                    "offset_x": settings["off_x"],
                    "offset_y": settings["off_y"],
                    "refine_extra": settings["refine_extra"]
                }
            }
            cfg = load_config()
            cfg.setdefault("automation", {}).update(updates["automation"])
            st.session_state.config = save_config(cfg)
            st.toast("Settings saved to config.json")

    # Fix: Explicit rerun on change to solve the "double-click" bug in dialogs
    if selected_approach != prev_approach:
        settings["approach"] = selected_approach
        st.rerun(scope="fragment") # Use fragment scope to keep the dialog open

    # 2. Dynamic Parameters Row
    param_cols = st.columns(5) # Reorganized to use all columns
    
    with param_cols[0]:
        if selected_approach != "Manual (Brush Only)":
            settings["off_x"] = st.number_input("Offset X", -50, 50, value=settings["off_x"], step=1, help="微调 mask 的水平位置")
        else:
            settings["brush_size"] = st.slider("Brush", 5, 100, value=settings["brush_size"])

    with param_cols[1]:
        if selected_approach != "Manual (Brush Only)":
            settings["off_y"] = st.number_input("Offset Y", -50, 50, value=settings["off_y"], step=1, help="微调 mask 的垂直位置")
            
    if selected_approach in ["Inverse Alpha (Lossless)", "Hybrid (Clean + Refine)"]:
        with param_cols[2]:
            settings["logo_val"] = st.slider("Logo", 150.0, 255.0, value=settings["logo_val"], step=1.0)
        with param_cols[3]:
            settings["alpha_con"] = st.slider("Alpha", 0.5, 2.0, value=settings["alpha_con"], step=0.1)
        if selected_approach == "Hybrid (Clean + Refine)":
            with param_cols[4]:
                settings["refine_extra"] = st.slider("Refine", 0.0, 0.5, value=settings["refine_extra"], step=0.05)

    # 3. Main Previews Layout (Centered with Spacers)
    spacer_l, col_left, spacer_m, col_right, spacer_r = st.columns([0.1, 1, 0.1, 1, 0.1])
    
    with col_left:
        st.write("**Canvas (Mask Drawing)**")
        # In Lossless mode, we don't necessarily NEED a brush, but keeping it for consistency if they want to override
        canvas_result = st_canvas(fill_color="rgba(255, 165, 0, 0.3)", stroke_width=settings["brush_size"] if selected_approach == "Manual (Brush Only)" else 20, 
                                stroke_color="#FFFFFF", background_image=original_img, height=canvas_h, width=canvas_w, 
                                drawing_mode="freedraw", update_streamlit=True, key=f"m_c_{filename}_{st.session_state.manual_removal_preview_id}")
    with col_right:
        st.write("**AI Refined Result**")
        
        # --- Processing Logic Integration ---
        import numpy as np
        import hashlib
        
        mask_data = None
        if canvas_result.image_data is not None:
            mask_data = canvas_result.image_data[:, :, 3]
            mask_data = np.where(mask_data > 10, 255, 0).astype(np.uint8)
            mask_img = Image.fromarray(mask_data).resize(original_img.size, Image.NEAREST)
            has_paint = np.any(mask_data > 0)
        else:
            has_paint = False
            mask_img = None

        # Logic for preview updates
        # We Hash inputs to avoid redundant AI calls
        current_input_hash = hashlib.md5(str((selected_approach, settings, mask_data.tobytes() if has_paint else None)).encode()).hexdigest()

        if st.session_state.manual_removal_preview["hash"] != current_input_hash:
            with st.spinner("Processing..."):
                try:
                    res_img = original_img.copy()
                    
                    # Pass 1: Inverse Alpha (if applicable)
                    if selected_approach in ["Inverse Alpha (Lossless)", "Hybrid (Clean + Refine)"]:
                        # Lazy load remover
                        remover = get_remover()
                        res_img = remover.process_image(
                            res_img,
                            logo_value=settings["logo_val"],
                            alpha_contrast=settings["alpha_con"],
                            offset_x=settings["off_x"],
                            offset_y=settings["off_y"]
                        )
                    
                    # Pass 2: LaMa / AI Refine (if applicable)
                    if selected_approach == "LaMa Inpainting (AI)":
                        refiner = get_refiner()
                        if has_paint:
                            res_img = refiner(original_img, mask_img)
                        else:
                            # Auto-detection for AI mode (Standard position + offsets)
                            remover = get_remover()
                            config = remover.detect_config(original_img.width, original_img.height)
                            auto_mask = Image.new("L", original_img.size, 0)
                            size = config["size"]
                            dilation = int(size * (0.4 + settings["refine_extra"]))
                            expanded_size = size + 2 * dilation
                            bx = original_img.width - config["margin_right"] - size + settings["off_x"] - dilation
                            by = original_img.height - config["margin_bottom"] - size + settings["off_y"] - dilation
                            from PIL import ImageDraw
                            draw = ImageDraw.Draw(auto_mask)
                            draw.rectangle([bx, by, bx + expanded_size, by + expanded_size], fill=255)
                            res_img = refiner(original_img, auto_mask)
                            
                    elif selected_approach == "Hybrid (Clean + Refine)":
                        # If no paint, use auto-detected box. If paint, use paint.
                        refiner = get_refiner()
                        if has_paint:
                            # Use user mask on the alpha-cleaned image
                            res_img = refiner(res_img, mask_img)
                        else:
                            # Auto-detection from Inverse Alpha
                            remover = get_remover()
                            config = remover.detect_config(original_img.width, original_img.height)
                            auto_mask = Image.new("L", original_img.size, 0)
                            size = config["size"]
                            dilation = int(size * (0.4 + settings["refine_extra"]))
                            expanded_size = size + 2 * dilation
                            bx = original_img.width - config["margin_right"] - size + settings["off_x"] - dilation
                            by = original_img.height - config["margin_bottom"] - size + settings["off_y"] - dilation
                            from PIL import ImageDraw
                            draw = ImageDraw.Draw(auto_mask)
                            draw.rectangle([bx, by, bx + expanded_size, by + expanded_size], fill=255)
                            res_img = refiner(res_img, auto_mask)
                    elif selected_approach == "Manual (Brush Only)" and has_paint:
                        refiner = get_refiner()
                        res_img = refiner(original_img, mask_img)
                        
                    st.session_state.manual_removal_preview["img"] = res_img
                    st.session_state.manual_removal_preview["hash"] = current_input_hash
                except Exception as e:
                    st.error(f"Processing failed: {e}")

        if st.session_state.manual_removal_preview["img"]:
            result_img = st.session_state.manual_removal_preview["img"]
            # Use width='stretch' to ensure button and image occupy the same width in the column
            st.image(result_img, width='stretch') 
            
            if st.button("💾 Save to Processed", width="stretch", type="primary"):
                final_path = os.path.join(processed_dir, filename)
                save_with_metadata(result_img, original_img, final_path, original_stats=os.stat(file_path))
                st.success(f"Saved to: `{os.path.basename(processed_dir)}/{filename}`")
                st.toast(f"✅ Saved to {final_path}")
                st.session_state.manual_removal_preview = {"hash": None, "img": None}
                st.session_state.manual_removal_preview_id += 1
                time.sleep(1); st.rerun()
        else:
            if selected_approach in ["LaMa Inpainting (AI)", "Manual (Brush Only)"]:
                st.info("Start drawing to see the AI result.")
            else:
                st.info("Adjust settings to see the preview.")

@st.dialog("📦 Batch Remove Watermarks", width="medium")
def batch_watermark_removal_dialog(folder_path):
    # Ensure we don't nest processed/processed
    base_folder_name = os.path.basename(folder_path.rstrip("/\\"))
    if base_folder_name.lower() == "processed":
        target_base = os.path.dirname(folder_path)
    else:
        target_base = folder_path
    
    processed_dir = os.path.join(target_base, "processed")

    # Filter and Sort Files (only once)
    if not st.session_state.batch_files:
        try:
            raw_files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
            st.session_state.batch_files = sorted(raw_files, key=natural_sort_key)
        except Exception as e:
            st.error(f"Cannot read folder: {e}")
            return

    raw_all_files = st.session_state.batch_files
    files = raw_all_files # Primary baseline
    
    if not files:
        st.warning("No images found in the selected folder.")
        if st.button("Close"): 
            st.session_state.show_batch_dialog = False
            st.rerun()
        return

    # Load config and approach
    config = load_config()
    automation = config.get("automation", {})
    approach = automation.get("remove_watermark_approach", "Hybrid (Clean + Refine)")
    
    # --- Safety Check: Check if main looping process is running ---
    is_auto_running = False
    try:
        auto_stats = asyncio.run(st.session_state.client.get_automation_stats())
        is_auto_running = auto_stats.get("is_running", False)
    except:
        pass

    st.write(f"📁 Folder: `{os.path.basename(folder_path)}`")
    
    # Range Focus calculation (needed for count)
    enable_range = st.session_state.get("batch_range_enabled", False)
    files = raw_all_files
    if enable_range:
        s_val = int(st.session_state.get("batch_range_start", "1")) if st.session_state.get("batch_range_start", "1").isdigit() else 0
        e_val = int(st.session_state.get("batch_range_end", "100")) if st.session_state.get("batch_range_end", "100").isdigit() else 999999
        
        def get_fn_num(fn):
            import re
            m = re.search(r'\d+', fn)
            return int(m.group()) if m else None

        filtered_files = []
        for f in raw_all_files:
            num = get_fn_num(f)
            if num is not None and s_val <= num <= e_val:
                filtered_files.append(f)
        files = filtered_files
    
    total_files = len(files)
    st.write(f"🖼️ Images in range: **{total_files}**")

    # Interactive Method Selection
    methods = ["Inverse Alpha (Lossless)", "Hybrid (Clean + Refine)"]
    try: current_idx = methods.index(approach)
    except ValueError: current_idx = 1
    
    selected_method = st.selectbox(
        "🪄 Removal Method",
        options=methods,
        index=current_idx,
        key="batch_approach_select",
        disabled=st.session_state.batch_is_running or is_auto_running,
        help="Select the algorithm for watermark removal. Changes are saved immediately."
    )
    
    if selected_method != approach:
        new_auto = config.get("automation", {}).copy()
        new_auto["remove_watermark_approach"] = selected_method
        st.session_state.config = save_config({"automation": new_auto})
        st.toast(f"✅ Method updated: {selected_method}")
        time.sleep(0.5)
        st.rerun(scope="fragment")

    # --- Range Focus UI ---
    enable_range = st.toggle("🎯 Enable Range Focus", key="batch_range_enabled", help="Process only a specific numeric range of images.")
    if enable_range:
        col_start, col_end = st.columns(2)
        with col_start:
            st.text_input("Start #", value="1", key="batch_range_start")
        with col_end:
            st.text_input("End #", value="100", key="batch_range_end")

    if is_auto_running:
        st.warning("⚠️ Looping Process is currently running. Batch processing is disabled to prevent conflicts.")
        
    # Button Row
    col1, col2, col3 = st.columns(3)
    with col1:
        is_disabled = st.session_state.batch_is_running or is_auto_running or total_files == 0
        if st.button("🚀 Proceed All", width="stretch", disabled=is_disabled):
            st.session_state.batch_last_index = 0
            st.session_state.batch_is_running = True
            st.session_state.batch_stop_requested = False
            st.rerun(scope="fragment")
    with col2:
        can_continue = st.session_state.batch_last_index > 0 and st.session_state.batch_last_index < total_files
        cont_disabled = st.session_state.batch_is_running or not can_continue or is_auto_running or enable_range
        if st.button("➡️ Continue", width="stretch", disabled=cont_disabled):
            st.session_state.batch_is_running = True
            st.session_state.batch_stop_requested = False
            st.rerun(scope="fragment")
    with col3:
        if st.button("🛑 Cancel", width="stretch", disabled=not st.session_state.batch_is_running or is_auto_running):
            st.session_state.batch_stop_requested = True
            # We don't rerun(scope="fragment") here because the loop will catch it and rerun

    progress_bar = st.progress(0)
    status_text = st.empty()

    currentIndex = st.session_state.batch_last_index
    if total_files > 0:
        progress_bar.progress(min(1.0, currentIndex / total_files))
    else:
        progress_bar.progress(0.0)

    if currentIndex >= total_files:
        st.success(f"✅ Successfully processed all {total_files} images!")
        st.session_state.batch_is_running = False
        if st.button("Close Window", width="stretch", type="primary"):
            st.session_state.show_batch_dialog = False
            st.session_state.batch_files = [] # Clear for next time
            st.rerun()
        return

    if st.session_state.batch_is_running:
        if st.session_state.batch_stop_requested:
            st.session_state.batch_is_running = False
            st.session_state.batch_stop_requested = False
            status_text.warning(f"🛑 Stopped at {currentIndex}/{total_files}. Click Continue to resume.")
            st.rerun(scope="fragment")
        
        filename = files[currentIndex]
        file_path = os.path.join(folder_path, filename)
        status_text.write(f"Processing ({currentIndex+1}/{total_files}): `{filename}`")
        
        try:
            os.makedirs(processed_dir, exist_ok=True)
            logo_val = automation.get("logo_value", 255.0)
            alpha_con = automation.get("alpha_contrast", 1.0)
            off_x = automation.get("offset_x", 0)
            off_y = automation.get("offset_y", 0)
            refine_extra = automation.get("refine_extra", 0.0)

            with Image.open(file_path) as original_img:
                res_img = original_img.copy()
                if approach in ["Inverse Alpha (Lossless)", "Hybrid (Clean + Refine)"]:
                    remover = get_remover()
                    res_img = remover.process_image(res_img, logo_value=logo_val, alpha_contrast=alpha_con, offset_x=off_x, offset_y=off_y)
                
                if approach in ["LaMa Inpainting (AI)", "Hybrid (Clean + Refine)"]:
                    refiner = get_refiner(); remover = get_remover()
                    cfg_det = remover.detect_config(original_img.width, original_img.height)
                    auto_mask = Image.new("L", original_img.size, 0)
                    size = cfg_det["size"]
                    dilation = int(size * (0.4 + refine_extra))
                    expanded_size = size + 2 * dilation
                    bx = original_img.width - cfg_det["margin_right"] - size + off_x - dilation
                    by = original_img.height - cfg_det["margin_bottom"] - size + off_y - dilation
                    from PIL import ImageDraw
                    draw = ImageDraw.Draw(auto_mask)
                    draw.rectangle([bx, by, bx + expanded_size, by + expanded_size], fill=255)
                    res_img = refiner(res_img if approach == "Hybrid (Clean + Refine)" else original_img, auto_mask)
                elif approach == "Manual (Brush Only)":
                    refiner = get_refiner(); remover = get_remover()
                    cfg_det = remover.detect_config(original_img.width, original_img.height)
                    auto_mask = Image.new("L", original_img.size, 0)
                    size = cfg_det["size"]
                    bx = original_img.width - cfg_det["margin_right"] - size + off_x
                    by = original_img.height - cfg_det["margin_bottom"] - size + off_y
                    from PIL import ImageDraw
                    draw = ImageDraw.Draw(auto_mask)
                    draw.rectangle([bx, by, bx + size, by + size], fill=255)
                    res_img = refiner(original_img, auto_mask)

                save_with_metadata(res_img, original_img, os.path.join(processed_dir, filename), original_stats=os.stat(file_path))
        except Exception as e:
            st.error(f"Error processing `{filename}`: {e}")
        
        st.session_state.batch_last_index += 1
        time.sleep(0.01)
        st.rerun(scope="fragment")
    else:
        # Only show pause info if we're midway and not running/stopping
        if 0 < currentIndex < total_files:
            status_text.info(f"⏸️ Paused at {currentIndex}/{total_files}. Click Continue to resume.")

# --- Dialogs ---
@st.dialog("\u200B", width="large")
def edit_asset_dialog(file_path):

    # Version is set BEFORE this dialog is called (in the button handler).
    # Each fresh dialog open gets a new ver → fresh versioned widget keys → value=v is used.
    # Reruns within the same dialog session keep the same ver → widget state persists correctly.
    ver = st.session_state["_edit_dialog_ver"]
    baseline_key = f"_edit_baseline_v{ver}"

    # Pre-fetch data and CLOSE handles immediately
    try:
        with Image.open(file_path) as img:
            metadata = get_consolidated_metadata(img)
            # Support common case variations
            img_prompt = metadata.get("parameters", metadata.get("prompt", metadata.get("Prompt", "")))
            img_url = metadata.get("url", metadata.get("URL", metadata.get("Url", "")))
            img_path = metadata.get("upload_path", metadata.get("Upload_Path", ""))
            img_format = img.format
    except Exception as e:
        st.error(f"Failed to read asset: {e}")
        return

    # Initialize versioned baseline on first render of this dialog version
    if baseline_key not in st.session_state:
        st.session_state[baseline_key] = metadata.copy()
    baseline = st.session_state[baseline_key]

    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.markdown("#### 📝 Edit Prompt")
        # Extract prompt from baseline with fallback
        img_prompt = baseline.get("parameters", baseline.get("prompt", baseline.get("Prompt", "")))
        up_prompt = st.text_area("Key: prompt", value=img_prompt, height=250, key=f"edit_v{ver}_prompt")
        
        if st.button("Apply Prompt to Config", key=f"btn_apply_prompt_v{ver}", width="stretch"):
            st.session_state.config = save_config({"prompt": up_prompt})
            st.toast("Prompt updated in config.json")
            time.sleep(0.5)

    with col_right:
        st.markdown("#### 🔗 Edit URL & Path")
        # URL field
        img_url = baseline.get("url", baseline.get("URL", baseline.get("Url", "")))
        up_url = st.text_input("Key: url", value=img_url, key=f"edit_v{ver}_URL")
        if st.button("Apply URL to Config", key=f"btn_apply_url_v{ver}", width="stretch"):
            st.session_state.config = save_config({"browser_url": up_url})
            st.toast("Browser URL updated in config.json")
            time.sleep(0.5)
        # Path field
        img_path = baseline.get("upload_path", baseline.get("Upload_Path", ""))
        up_path = st.text_input("Key: upload_path", value=img_path, disabled=False, key=f"edit_v{ver}_path")
        if st.button("Apply Path to Config", key=f"btn_apply_path_v{ver}", width="stretch"):
            st.session_state.config = save_config({"save_dir": up_path})
            st.toast("Save directory updated in config.json")
            time.sleep(0.5)

    st.markdown("---")
    
    # Bottom Buttons
    btn_col1, btn_col2 = st.columns([1, 1])
    with btn_col1:
        save_clicked = st.button("💾 Save to File", type="primary", width="stretch")
    with btn_col2:
        apply_all_clicked = st.button("🚀 Apply All to Config", width="stretch")

    if save_clicked:
        # Construct current_vals from all baseline keys, but override prompt and URL from our specific widgets
        current_vals = baseline.copy()
        
        # Determine the correct key for prompt (preserve existing casing)
        if "parameters" in baseline: p_key = "parameters"
        elif "Prompt" in baseline: p_key = "Prompt"
        else: p_key = "prompt"
        
        current_vals[p_key] = st.session_state.get(f"edit_v{ver}_prompt", img_prompt)
        
        # Determine the correct key for URL (preserve existing casing)
        if "URL" in baseline: url_key = "URL"
        elif "Url" in baseline: url_key = "Url"
        else: url_key = "url"
        
        current_vals[url_key] = st.session_state.get(f"edit_v{ver}_URL", img_url)
        
        # Determine the correct key for path (preserve existing casing)
        path_key = "Upload_Path" if "Upload_Path" in baseline else "upload_path"
        current_vals[path_key] = st.session_state.get(f"edit_v{ver}_path", img_path)
        
        if current_vals == baseline:
            st.warning("⚠️ No changes detected — save skipped.")
        else:
            ok, err = save_metadata_final(file_path, current_vals)
            if ok:
                st.markdown(f"""
                    <div style='width: 100%; padding: 10px; background-color: rgba(40, 167, 69, 0.2); border: 1px solid #28a745; border-radius: 5px; color: #28a745; text-align: center; font-weight: bold;'>
                        ✅ Metadata saved to file.
                    </div>
                """, unsafe_allow_html=True)
                st.session_state[baseline_key] = current_vals.copy()
            else:
                st.error(f"Save failed: {err}")

    if apply_all_clicked:
        new_prompt = st.session_state.get(f"edit_v{ver}_prompt", img_prompt)
        new_url = st.session_state.get(f"edit_v{ver}_URL", img_url)
        new_path = st.session_state.get(f"edit_v{ver}_path", img_path)
        st.session_state.config = save_config({
            "prompt": new_prompt,
            "browser_url": new_url,
            "save_dir": new_path
        })
        st.toast("✅ Prompt, URL, and Path updated in config.json")
        time.sleep(0.5)


@st.dialog("Confirm Delete")
def confirm_delete_dialog(file_path):
    st.warning(f"Are you sure you want to delete this file?\n\n`{os.path.basename(file_path)}`")
    if st.button("Yes, Delete Forever", type="primary", width="stretch"):
        try:
            # 1. Cascading delete for processed counterpart
            folder_path = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            
            # If current file is NOT in 'processed', look for its processed version
            if os.path.basename(folder_path.rstrip("/\\")).lower() != "processed":
                processed_file = os.path.join(folder_path, "processed", filename)
                if os.path.exists(processed_file):
                    try:
                        os.remove(processed_file)
                    except:
                        pass # Fail silently as requested

            # 2. Main deletion
            os.remove(file_path)

            # 3. Handle reload state
            if not st.session_state.get("sanitizer_is_dir", False):
                st.session_state.sanitizer_path = "" # Clear view only in File Mode
            st.toast("File deleted.")
            time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.error(f"Delete failed: {e}")

@st.dialog("Complete Metadata", width="large")
def view_metadata_dialog(file_path):
    st.markdown("### ℹ️ Complete Metadata")
    try:
        with Image.open(file_path) as img:
            metadata = get_consolidated_metadata(img)
            if metadata:
                st.json(metadata)
            else:
                st.info("No metadata found.")
    except Exception as e:
        st.error(f"Failed to read asset metadata: {e}")

def render_san_gallery_nav(total_pages, key_suffix):
    c1, c2, c3, c4, c5 = st.columns([0.5, 0.5, 2, 0.5, 0.5])
    with c1:
        st.button("|◀", key=f"san_first_{key_suffix}", width="stretch", type="primary",
                  disabled=total_pages <= 1 or st.session_state.san_gal_page <= 1,
                  on_click=sync_san_page, args=(1,))
    with c2:
        st.button("◀", key=f"san_prev_{key_suffix}", width="stretch", type="primary",
                  disabled=total_pages <= 1 or st.session_state.san_gal_page <= 1,
                  on_click=sync_san_page, args=(st.session_state.san_gal_page - 1,))
    with c3:
        st.number_input(f"Page (of {total_pages})", 
                        min_value=1, 
                        max_value=max(1, total_pages),
                        key=f"san_gal_page_{key_suffix}_widget",
                        on_change=on_san_page_top_change if key_suffix == "top" else on_san_page_bot_change, 
                        label_visibility="collapsed",
                        disabled=total_pages <= 1)
    with c4:
        st.button("▶", key=f"san_next_{key_suffix}", width="stretch", type="primary",
                  disabled=total_pages <= 1 or st.session_state.san_gal_page >= total_pages,
                  on_click=sync_san_page, args=(st.session_state.san_gal_page + 1,))
    with c5:
        st.button("▶|", key=f"san_last_{key_suffix}", width="stretch", type="primary",
                  disabled=total_pages <= 1 or st.session_state.san_gal_page >= total_pages,
                  on_click=sync_san_page, args=(total_pages,))

def img_to_b64(path):
    ext = os.path.splitext(path)[-1].lower().strip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "png")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return b64, mime

# --- UI Layout ---
with st.sidebar:
    # --- Path Selection ---
    st.markdown("### Select Path")
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📄 File", key="san_opt_file", width="stretch"):
                path = select_path(False)
                if path:
                    st.session_state.sanitizer_path = path
                    st.session_state.sanitizer_is_dir = False
                    st.rerun()

        with col2:
            if st.button("📁 Folder", key="san_opt_folder", width="stretch"):
                path = select_path(True)
                if path:
                    st.session_state.sanitizer_path = path
                    st.session_state.sanitizer_is_dir = True
                    sync_san_page(1)
                    st.rerun()
        
        # --- AI Cleaned Toggle ---
        is_folder = st.session_state.sanitizer_is_dir and st.session_state.sanitizer_path
        not_in_processed = os.path.basename(st.session_state.sanitizer_path.rstrip("/\\")).lower() != "processed"
        
        can_enable_toggle = is_folder and not_in_processed
        
        if "san_show_cleaned" not in st.session_state:
            st.session_state.san_show_cleaned = False
            
        show_cleaned = st.toggle(
            "Show AI Cleaned Image",
            value=st.session_state.san_show_cleaned,
            key="san_cleaned_toggle_widget",
            disabled=not can_enable_toggle,
            help="Switch view to the 'processed' subfolder if it exists."
        )
        
        if show_cleaned != st.session_state.san_show_cleaned:
            if show_cleaned:
                # Check existence
                p_dir = os.path.join(st.session_state.sanitizer_path, "processed")
                if not os.path.isdir(p_dir):
                    show_missing_processed_warning_dialog()
                else:
                    st.session_state.san_show_cleaned = True
                    st.rerun()
            else:
                st.session_state.san_show_cleaned = False
                st.rerun()


    # --- Album Navigation ---
    if st.session_state.sanitizer_is_dir and st.session_state.sanitizer_path and os.path.isdir(st.session_state.sanitizer_path):
        st.markdown("### Album Navigation")
        with st.container(border=True):
            # 1. Sorting Controls (Moved above Navigation to trigger reset BEFORE navigation widgets render)
            sort_options = ["Name", "Create Date", "Modified Date"]
            new_sort = st.selectbox("Sort by", sort_options,
                                    index=sort_options.index(st.session_state.san_sort_by),
                                    key="san_sort_by_select",
                                    label_visibility="visible")
            if new_sort != st.session_state.san_sort_by:
                st.session_state.san_sort_by = new_sort
                sync_san_page(1)
                st.rerun()

            new_dir = st.radio("Order", ["Ascending", "Descending"],
                               index=1 if st.session_state.san_sort_desc else 0,
                               key="san_sort_dir_radio",
                               horizontal=True,
                               label_visibility="collapsed")
            new_desc = (new_dir == "Descending")
            if new_desc != st.session_state.san_sort_desc:
                st.session_state.san_sort_desc = new_desc
                sync_san_page(1)
                st.rerun()

            # 2. Navigation
            render_san_gallery_nav(san_total_pages, "top")

            st.slider("Images per page", 4, 32,
                      value=st.session_state.san_gal_page_size,
                      step=4,
                      key="san_page_size_slider",
                      on_change=on_san_page_size_change)

        # --- Batch Processing Section ---
        batch_processing_sidebar_fragment()



# --- Main Panel ---

if st.session_state.sanitizer_path and os.path.exists(st.session_state.sanitizer_path):
    if not st.session_state.sanitizer_is_dir:
        # ── FILE MODE ────────────────────────────────────────────────────
        file_path = st.session_state.sanitizer_path
        filename = os.path.basename(file_path)

        col_l, col_mid, col_r = st.columns([1, 2, 1])
        with col_mid:
            with st.container(border=True):
                try:
                    img_b64, mime = img_to_b64(file_path)
                    st.markdown(f"""
                        <div style='text-align:center; padding: 8px 0;'>
                            <img src='data:image/{mime};base64,{img_b64}'
                                 style='max-height:450px; max-width:100%; width:auto; object-fit:contain; border-radius:6px;'>
                        </div>
                        <p style='text-align:center; font-size:0.8rem; color:#888; margin:4px 0 8px 0;'>{filename}</p>
                    """, unsafe_allow_html=True)

                    btn_col1, btn_col2, btn_col3, btn_col4, btn_col5 = st.columns(5)
                    with btn_col1:
                        if st.button("👁️", key="v_btn", width="stretch", help="View image"):
                            os.startfile(file_path)
                    with btn_col2:
                        if st.button("📝", key="e_btn", width="stretch", help="Edit metadata"):
                            # Increment version → guarantees fresh widget keys on new dialog open
                            st.session_state["_edit_dialog_ver"] += 1
                            edit_asset_dialog(file_path)
                    with btn_col3:
                        if st.button("ℹ️", key="i_btn", width="stretch", help="View complete metadata"):
                            view_metadata_dialog(file_path)
                    with btn_col4:
                        if st.button("🪄", key="w_btn", width="stretch", help="Remove watermarks"):
                            try:
                                auto_stats = asyncio.run(st.session_state.client.get_automation_stats())
                                is_auto_running = auto_stats.get("is_running", False)
                            except: is_auto_running = False
                            
                            if is_auto_running:
                                show_model_busy_warning_dialog()
                            else:
                                manual_watermark_removal_dialog(file_path)
                    with btn_col5:
                        if st.button("🗑️", key="d_btn", width="stretch", help="Delete asset"):
                            confirm_delete_dialog(file_path)

                except Exception as e:
                    st.error(f"Failed to load image: {e}")

    else:
        # ── FOLDER MODE ──────────────────────────────────────────────────
        folder_path = san_current_folder

        if not san_all_files:
            st.info("No images found in the selected folder.")
        else:
            p_size = st.session_state.san_gal_page_size
            page_files = san_all_files[
                (st.session_state.san_gal_page - 1) * p_size :
                st.session_state.san_gal_page * p_size
            ]

            COLS_PER_ROW = 4
            for i in range(0, len(page_files), COLS_PER_ROW):
                cols = st.columns(COLS_PER_ROW)
                for idx, fname in enumerate(page_files[i:i + COLS_PER_ROW]):
                    fpath = os.path.join(folder_path, fname)
                    with cols[idx]:
                        with st.container(border=True):
                            try:
                                img_b64, mime = img_to_b64(fpath)
                                st.markdown(f"""
                                    <div style='text-align:center; padding:4px 0;'>
                                        <img src='data:image/{mime};base64,{img_b64}'
                                             style='max-height:180px; max-width:100%; width:auto; object-fit:contain; border-radius:4px;'>
                                    </div>
                                """, unsafe_allow_html=True)
                                st.caption(fname)
                                b1, b2, b3, b4, b5 = st.columns(5)
                                with b1:
                                    if st.button("👁️", key=f"v_{fname}", width="stretch", help="View image"):
                                        os.startfile(fpath)
                                with b2:
                                    if st.button("📝", key=f"e_{fname}", width="stretch", help="Edit metadata"):
                                        # Increment version → guarantees fresh widget keys on new dialog open
                                        st.session_state["_edit_dialog_ver"] += 1
                                        edit_asset_dialog(fpath)
                                with b3:
                                    if st.button("ℹ️", key=f"i_{fname}", width="stretch", help="View complete metadata"):
                                        view_metadata_dialog(fpath)
                                with b4:
                                    if st.button("🪄", key=f"w_{fname}", width="stretch", help="Remove watermarks"):
                                        try:
                                            auto_stats = asyncio.run(st.session_state.client.get_automation_stats())
                                            is_auto_running = auto_stats.get("is_running", False)
                                        except: is_auto_running = False
                                        
                                        if is_auto_running:
                                            show_model_busy_warning_dialog()
                                        else:
                                            manual_watermark_removal_dialog(fpath)
                                with b5:
                                    if st.button("🗑️", key=f"d_{fname}", width="stretch", help="Delete asset"):
                                        confirm_delete_dialog(fpath)
                            except Exception as e:
                                st.caption(f"⚠️ {fname}")
else:
    # --- Welcome Guide / Intro (Shown when no path is selected) ---
    guide_path = os.path.join(os.getcwd(), "guides", "asset_sanitizer_intro.md")
    if os.path.exists(guide_path):
        with open(guide_path, "r", encoding="utf-8") as f:
            guide_md = f.read()
        with st.container(border=True):
            st.markdown(guide_md)
    else:
        st.info("👋 Welcome! Please select a Folder or File from the sidebar to begin.")

# Reset to empty state on first load
if "sanitizer_path_init_done" not in st.session_state:
    st.session_state.sanitizer_path = ""
    st.session_state.sanitizer_path_init_done = True
