import streamlit as st
print(f"Streamlit Version: {st.__version__}")
import inspect
sig = inspect.signature(st.bar_chart)
print(f"st.bar_chart signature: {sig}")
