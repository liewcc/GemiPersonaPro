import streamlit as st

def apply_premium_style():
    """Applies the premium dark theme CSS to the page."""
    st.markdown("""
        <style>
        .main {
            background: linear-gradient(135deg, #1e1e2f 0%, #2d2d44 100%);
            color: #ffffff;
        }
        /* Keep header visible for sidebar toggle */
        /* #MainMenu {visibility: hidden;} */
        /* header {visibility: hidden;} */
        /* footer {visibility: hidden;} */
        /* Remove top and bottom margins for the main area */
        .block-container {
            padding-top: 3.5rem;
            padding-bottom: 2rem;
        }
        /* Dashboard Container */
        .dashboard-card {
            background: rgba(45, 45, 68, 0.7);
            border-radius: 15px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            margin-bottom: 20px;
        }
        /* Metric Styling */
        .metric-label {
            color: #a0a0ff;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .metric-value {
            font-size: 24px;
            font-weight: bold;
            color: #ffffff;
        }
        /* Buttons */
        .stButton>button {
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        </style>
        """, unsafe_allow_html=True)

def render_dashboard_header(title, subtitle):
    """Renders a premium looking header."""
    st.title(f"🪄 {title}")
    st.markdown(f"<p style='color: #a0a0ff; font-size: 1.1em;'>{subtitle}</p>", unsafe_allow_html=True)
    st.markdown("---")
