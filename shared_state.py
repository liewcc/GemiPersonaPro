# shared_state.py
# Module-level singletons that must persist across Streamlit page reruns.
#
# Streamlit re-executes the page script on every rerun, which resets any
# module-level variables defined IN the page script.  Variables defined in
# an IMPORTED module are safe because Python caches imported modules in
# sys.modules and never re-initialises them during the same process lifetime.

# LaMa model load state — written by background thread, polled by main thread.
lama_status: dict = {"ready": False, "error": None}

import streamlit as st
import torch
from lama_refiner import LaMaRefiner
from inverse_alpha_compositing import InverseAlphaCompositing

@st.cache_resource
def get_shared_remover():
    return InverseAlphaCompositing("sys_img/bg_48.png", "sys_img/bg_96.png")

@st.cache_resource
def get_shared_refiner(use_gpu=True):
    refiner = LaMaRefiner()
    target_device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
    refiner.load_model(force_device=target_device)
    return refiner

def clear_shared_refiner():
    get_shared_refiner.clear()
