"""Account Health Analysis & Cycle Management UI. Standalone Page."""
import streamlit as st
import os
import sys
import json
import re
import pandas as pd
import altair as alt
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config_utils import load_config, save_config, load_login_lookup
from health_parser import parse_account_health, parse_engine_cycles, LOG_PATH
from style_utils import apply_premium_style, render_dashboard_header

# --- Page Setup ---
st.set_page_config(page_title="GemiPersona | Account Health", page_icon="sys_img/logo.png", layout="wide")
apply_premium_style()

config = load_config()
login_data = load_login_lookup()

# --- Extract Account List & Active User ---
summary_all, _, log_accs = parse_account_health(login_data=login_data)
lookup_order = [u.get("username", "").lower() for u in login_data if u.get("username")]
log_accs_set = set(log_accs)
lookup_accs_set = set(lookup_order)
final_dropdown_accs = list(lookup_order) + sorted(list(log_accs_set - lookup_accs_set))
final_dropdown_accs = [acc for acc in final_dropdown_accs if acc and acc.lower() != "unknown"]
_active_user_top = next((u.get("username", "") for u in login_data if u.get("active")), None)

# --- Sidebar Content ---
@st.fragment(run_every=5 if st.session_state.get("health_auto_refresh", True) else None)
def _sidebar_fragment_content():
    # Fetch fresh login data to detect account switches without full page reload
    fresh_login_data = load_login_lookup()
    fresh_active = next((u.get("username", "") for u in fresh_login_data if u.get("active")), None)
    
    st.markdown("<p style='font-size: 1.15em; font-weight: bold; margin-top: 0px; margin-bottom: 5px;'>👥 Account List</p>", unsafe_allow_html=True)
    if not final_dropdown_accs:
        st.info("No accounts recorded yet.")
    else:
        acc_list_md = []
        for acc in final_dropdown_accs:
            user_data = next((u for u in fresh_login_data if u.get("username", "").lower() == acc.lower()), {})
            is_active = fresh_active and acc.lower() == fresh_active.lower()
            is_quota_full = bool(user_data.get("quota_full"))
            
            display_str = acc
            if is_quota_full:
                display_str = f"<span style='color: #ff6666;'>{acc} (Quota Full)</span>"
            
            if is_active:
                # Use blue for active account to make it stand out
                blue_name = f"<span style='color: #4b9cff;'>{acc}</span>"
                if is_quota_full:
                    display_str = f"{blue_name} <span style='color: #ff6666;'>(Quota Full)</span>"
                else:
                    display_str = blue_name
                acc_list_md.append(f"- **{display_str}** *(Active)*")
            else:
                acc_list_md.append(f"- {display_str}")
        st.markdown("\n".join(acc_list_md), unsafe_allow_html=True)
    st.markdown("<hr style='margin-top: 10px; margin-bottom: 10px; border-top: 1px solid rgba(255,255,255,0.1);' />", unsafe_allow_html=True)

with st.sidebar:
    _sidebar_fragment_content()



# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_dur(x):
    h = int(x // 3600); m = int((x % 3600) // 60); s = int(x % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else (f"{m:02d}:{s:02d}" if m > 0 else f"{s:02d}s")


def _build_duration_chart(detailed_data, y_scale_type):
    """Build a bar chart of loading durations per event."""
    df = pd.DataFrame(detailed_data[::-1])
    df["Event"] = range(1, len(df) + 1)

    df["Minutes"] = df["health"].str.replace("s", "").astype(float) / 60.0
    # Global dense rank of session_index so every new session (including account
    # switches) alternates Base ↔ Light. Per-account ranking caused all first
    # sessions of different accounts to share rank=1 and thus the same color.
    df["cycle"] = df["session_index"].rank(method="dense").astype(int)
    df["variant"] = df["cycle"].apply(lambda x: "Base" if x % 2 == 1 else "Light")
    ll = ['Success (Base)', 'Reject (Base)', 'Reset (Base)', 'Fail',
          'Success (Light)', 'Reject (Light)', 'Reset (Light)']
    lr = ['#2ecc71', '#a0a0ff', '#f39c12', '#ff9999', '#a0e6b5', '#d0d0ff', '#f9e79f']
    df['legend'] = df.apply(lambda r: f"{r['status']} ({r['variant']})" if r['status'] != 'Fail' else 'Fail', axis=1)
    df["Duration"] = df["health"].str.replace("s", "").astype(float).apply(_fmt_dur)
    
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X('Event:Q', title="Sequence", scale=alt.Scale(nice=False), axis=alt.Axis(format='d', tickMinStep=1)),
        y=alt.Y('Minutes:Q', title="Duration (minite)", scale=alt.Scale(type=y_scale_type)),
        color=alt.Color('legend:N', scale=alt.Scale(domain=ll, range=lr),
                        legend=alt.Legend(title=None, orient='bottom', columns=4)),
        tooltip=['round', 'time', 'account', 'Duration', 'filename', 'status']
    ).properties(height=400).interactive(bind_y=False)
    return chart


def _build_reject_chart(detailed_data, y_scale_type):
    """Build a reject-rate line+point chart (X = successful images)."""
    agg_data = []; curr_rej = 0; curr_res = 0; curr_dur = 0.0; seg_id = 0; prev_si = None
    for row in reversed(detailed_data):
        si = row["session_index"]
        if prev_si is not None and si != prev_si:
            curr_rej = 0; curr_res = 0; curr_dur = 0.0; seg_id += 1
        row_dur = float(row["health"].replace("s", ""))
        if row["status"] == "Reject":
            curr_rej += 1; curr_dur += row_dur
        elif row["status"] == "Reset":
            curr_res += 1; curr_dur += row_dur
        elif row["status"] in ("Success", "Fail"):
            d = row.copy()
            if "true_rej" in d:
                d["Rejects"] = d["true_rej"]; d["Resets"] = d["true_res"]
                d["Duration"] = row_dur
            else:
                d["Rejects"] = curr_rej; d["Resets"] = curr_res
                d["Duration"] = curr_dur + row_dur
            d["Image"] = row["filename"].replace(".png", "") if row["filename"] else "FAILED"
            d["seg_id"] = seg_id; d["bg"] = 'A' if seg_id % 2 == 0 else 'B'
            d["Event"] = len(agg_data) + 1
            d["Display"] = f"{d['Image']} (#{d['Event']})"
            d["round"] = row.get("round", "N/A")
            agg_data.append(d)
            curr_rej = 0; curr_res = 0; curr_dur = 0.0
        prev_si = si

    if not agg_data:
        return None

    agg_df = pd.DataFrame(agg_data)
    agg_df["Event_Start"] = agg_df["Event"] - 0.5
    agg_df["Event_End"] = agg_df["Event"] + 0.5
    bg_bands = alt.Chart(agg_df).mark_rect(opacity=0.25).encode(
        x=alt.X('Event_Start:Q', title="Image Sequence", scale=alt.Scale(nice=False)),
        x2='Event_End:Q',
        color=alt.Color('bg:N', scale=alt.Scale(domain=['A', 'B'], range=['#d0d0d0', '#f5f5f5']), legend=None),
        tooltip=['account:N', 'session_index:Q']
    )
    agg_df["t_dur"] = agg_df["Duration"] / 60.0
    agg_df["t_rej"] = agg_df["Rejects"]
    agg_df["t_res"] = agg_df["Resets"]
    agg_df["t_dur_fmt"] = agg_df["Duration"].apply(lambda x: f"{int(x // 60)}:{int(x % 60):02d}")
    melt_ids = ['Event', 'Display', 'Image', 'round', 'account', 'time', 'session_index', 't_dur_fmt', 't_rej', 't_res', 'status']
    plot_df = agg_df.melt(id_vars=melt_ids, value_vars=['t_dur', 'Rejects', 'Resets'], var_name='Metric', value_name='Value')
    plot_df['Metric'] = plot_df['Metric'].replace({'t_dur': 'Duration (minite)'})

    cs = alt.Scale(domain=['Duration (minite)', 'Rejects', 'Resets'], range=['#2ecc71', '#a0a0ff', '#f39c12'])
    base = alt.Chart(plot_df).encode(
        x=alt.X('Event:Q', title=None, axis=alt.Axis(format='d', tickMinStep=1)),
        y=alt.Y('Value:Q', title=None, scale=alt.Scale(type=y_scale_type)),
        color=alt.Color('Metric:N', scale=cs, legend=alt.Legend(title=None, orient='bottom', symbolType='stroke', symbolStrokeWidth=3))
    )
    lines = base.mark_line()
    points = base.mark_point(opacity=0.9, size=50, filled=True).encode(
        color=alt.condition("datum.status == 'Fail'", alt.value("#ff3333"), alt.Color('Metric:N', scale=cs, legend=None)),
        tooltip=[
            alt.Tooltip('Image:N', title='Filename'), alt.Tooltip('round:N', title='Round'),
            alt.Tooltip('account:N', title='Account'), alt.Tooltip('time:N', title='Time'),
            alt.Tooltip('t_dur_fmt:N', title='Duration'), alt.Tooltip('t_rej:Q', title='Reject Count'),
            alt.Tooltip('t_res:Q', title='Reset Count'), alt.Tooltip('status:N', title='Status')
        ]
    )
    return alt.layer(bg_bands, lines, points).resolve_scale(color='independent').properties(height=400).interactive()


def _render_chart_or_table(data, graph_type, y_scale_type, show_graph, label, table_key):
    """Unified rendering: either chart or table for a given dataset."""
    if not data:
        st.info(f"No loading records found for {label}.")
        return
    if show_graph:
        st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Performance Graph for <b>{label}</b></p>", unsafe_allow_html=True)
        if graph_type == "Loading Duration":
            st.altair_chart(_build_duration_chart(data, y_scale_type), width="stretch")
        else:
            st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Reject Rate for <b>{label}</b> (X-Axis: Successful Images)</p>", unsafe_allow_html=True)
            chart = _build_reject_chart(data, y_scale_type)
            if chart is None:
                st.info("No successful image downloads found to plot trends.")
            else:
                st.altair_chart(chart, width="stretch")
    else:
        st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Loading records for <b>{label}</b>.</p>", unsafe_allow_html=True)
        st.data_editor(
            pd.DataFrame(data),
            column_config={
                "round": st.column_config.NumberColumn("Round", format="%d"),
                "account": st.column_config.TextColumn("Account"),
                "time": st.column_config.TextColumn("Time"),
                "health": st.column_config.TextColumn("Health"),
                "filename": st.column_config.TextColumn("Filename"),
                "status": st.column_config.TextColumn("Status")
            },
            disabled=True, width="stretch", hide_index=True, height=450, key=table_key
        )


# ── Callbacks ────────────────────────────────────────────────────────────────

def _on_change_health_graph():
    save_config({"health_graph_type": st.session_state.widget_health_graph_type})

def _on_change_health_view():
    save_config({"health_view_mode": st.session_state.widget_health_view_mode})

def _on_change_health_y_scale():
    save_config({"health_y_scale": st.session_state.widget_health_y_scale})

def _on_change_health_n_rounds():
    save_config({"health_n_rounds": st.session_state.widget_health_n_rounds})


# ── Render Logic ─────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["Account Health Analysis", "Automation Cycle Management"])

with tab1:
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>ACCOUNT HEALTH ANALYSIS</p>", unsafe_allow_html=True)
    with st.container(border=True):


        col_sel, col_ref, col_btn1, col_btn2 = st.columns([2, 0.8, 0.6, 0.6])
        with col_ref:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            st.toggle("Auto-refresh", value=True, key="health_auto_refresh", help="Disable to prevent chart reset while zooming.")
        with col_sel:
            options = ["Full Loading History (All Events)", "Detailed History: Active Account", "Latest Summary (All Accounts)"] + [f"Detailed History: {acc}" for acc in final_dropdown_accs]
            cfg_val = config.get("health_view_mode", "Full Loading History (All Events)")
            try:
                view_index = options.index(cfg_val)
            except ValueError:
                view_index = 0
            view_mode = st.selectbox("Select View Mode", options=options, index=view_index, key="widget_health_view_mode", on_change=_on_change_health_view, help="Choose between a complete history of all loading events, a summary of all accounts, or detailed history for a specific account.")

        is_full = view_mode == "Full Loading History (All Events)"
        is_active = view_mode == "Detailed History: Active Account"
        is_summary = view_mode == "Latest Summary (All Accounts)"

        if "show_health_graph" not in st.session_state:
            st.session_state.show_health_graph = True

        with col_btn1:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            if st.button("Refresh Log", icon="🔄", width="stretch"):
                st.rerun()
        with col_btn2:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            if not is_summary:
                lbl = "Show Table" if st.session_state.show_health_graph else "Plot Graph"
                ico = "📋" if st.session_state.show_health_graph else "📊"
                if st.button(lbl, icon=ico, width="stretch", type="secondary"):
                    st.session_state.show_health_graph = not st.session_state.show_health_graph
                    st.rerun()
            else:
                st.button("Plot Graph", icon="📊", width="stretch", disabled=True)

        if not is_summary:
            st.markdown("<div style='margin-bottom: 5px;'></div>", unsafe_allow_html=True)
            cfg_n_rounds = config.get("health_n_rounds", 100)
            
            if st.session_state.show_health_graph:
                col_slider, col_rad, col_scale = st.columns([1.5, 1.5, 1])
                graph_opts = ["Loading Duration", "Reject Rates"]
                scale_opts = ["Linear", "Logarithmic"]
                cfg_graph = config.get("health_graph_type", "Loading Duration")
                try:
                    graph_idx = graph_opts.index(cfg_graph)
                except ValueError:
                    graph_idx = 0
                cfg_scale = config.get("health_y_scale", "Linear")
                try:
                    scale_idx = scale_opts.index(cfg_scale)
                except ValueError:
                    scale_idx = 0
                
                with col_slider:
                    st.slider("Show Last N Events", min_value=10, max_value=2000, value=cfg_n_rounds, step=10, key="widget_health_n_rounds", on_change=_on_change_health_n_rounds)
                with col_rad:
                    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                    st.radio("Graph Mode", graph_opts, index=graph_idx, horizontal=True, key="widget_health_graph_type", on_change=_on_change_health_graph, label_visibility="collapsed")
                with col_scale:
                    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                    st.radio("Y-Axis Scale", scale_opts, index=scale_idx, horizontal=True, key="widget_health_y_scale", on_change=_on_change_health_y_scale, help="Use Logarithmic scale to see small counts (Rejects/Resets) alongside large durations.")
            else:
                col_slider, _ = st.columns([1.5, 2.5])
                with col_slider:
                    st.slider("Show Last N Events", min_value=10, max_value=2000, value=cfg_n_rounds, step=10, key="widget_health_n_rounds", on_change=_on_change_health_n_rounds)

        # Read settings once for the fragment
        y_scale_type = 'symlog' if config.get("health_y_scale", "Linear") == "Logarithmic" else 'linear'
        graph_type = config.get("health_graph_type", "Loading Duration")
        n_rounds = config.get("health_n_rounds", 100)

        # Fragment for auto-refreshing content
        auto_refresh = st.session_state.get("health_auto_refresh", True)

        @st.fragment(run_every=5 if auto_refresh else None)
        def _health_fragment():
            # Fetch fresh login data to ensure chart updates on account switch
            fresh_login_data = load_login_lookup()
            show_graph = st.session_state.get("show_health_graph", True)
            if is_full:
                st.markdown("<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Showing recorded loading events in chronological order (latest first).</p>", unsafe_allow_html=True)
                _, all_detailed, _ = parse_account_health(target_account="ALL_EVENTS", login_data=fresh_login_data)
                _render_chart_or_table(all_detailed[:n_rounds], graph_type, y_scale_type, show_graph, "All Events", "health_full_history_table")
            elif is_active:
                _active_user = next((u.get("username", "") for u in fresh_login_data if u.get("active")), None)
                if not _active_user:
                    st.info("No active account is currently set.")
                else:
                    _, det, _ = parse_account_health(target_account=_active_user.lower(), login_data=fresh_login_data)
                    _render_chart_or_table(det[:n_rounds], graph_type, y_scale_type, show_graph, f"{_active_user} (Active Account)", "health_active_account_table")
            elif is_summary:
                _summary_all, _, _ = parse_account_health(login_data=fresh_login_data)
                st.markdown("<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Showing the last recorded loading performance for each account.</p>", unsafe_allow_html=True)
                if not _summary_all:
                    st.info("No loading records found in engine.log.")
                else:
                    st.data_editor(
                        pd.DataFrame(_summary_all),
                        column_config={
                            "round": st.column_config.NumberColumn("Round", format="%d"),
                            "account": st.column_config.TextColumn("Account"),
                            "time": st.column_config.TextColumn("Time"),
                            "health": st.column_config.TextColumn("Health"),
                            "filename": st.column_config.TextColumn("Filename"),
                            "status": st.column_config.TextColumn("Status")
                        },
                        disabled=True, width="stretch", hide_index=True, height=450, key="health_summary_table"
                    )
            else:
                target_acc = view_mode.replace("Detailed History: ", "")
                _, det, _ = parse_account_health(target_account=target_acc, login_data=fresh_login_data)
                _render_chart_or_table(det[:n_rounds], graph_type, y_scale_type, show_graph, target_acc, f"health_detailed_{target_acc}")

        _health_fragment()

with tab2:
    st.markdown("### 🔄 Automation Cycle Management")
    st.write("This tool analyzes `engine.log` for complete automation cycles (Start -> Stop). **Continue Session** triggers are grouped within their original parent cycle.")

    cycles = parse_engine_cycles()
    if not cycles:
        st.info("No complete cycles found in the log.")
    else:
        st.write(f"Found **{len(cycles)}** complete cycle(s).")
        cycle_data = []
        for idx, c in enumerate(cycles):
            display_time = c.get('full_start_time', c['start_time_str'])
            
            avg_time_str = "N/A"
            success_count = c.get('success_count', 0)
            if success_count > 0:
                try:
                    start_dt = datetime.strptime(c['start_time_str'], '%H:%M:%S')
                    stop_dt = datetime.strptime(c.get('stop_time_str', c['start_time_str']), '%H:%M:%S')
                    total_seconds = int((stop_dt - start_dt).total_seconds())
                    if total_seconds < 0:
                        total_seconds += 86400
                    avg_seconds = total_seconds / success_count
                    avg_time_str = _fmt_dur(avg_seconds)
                except:
                    pass
            
            reject_count = c.get('reject_count', 0)
            avg_reject_str = "N/A"
            if reject_count > 0:
                avg_reject = c.get('reject_duration', 0) / reject_count
                avg_reject_str = _fmt_dur(avg_reject)

            reset_count = c.get('reset_count', 0)
            avg_reset_str = "N/A"
            if reset_count > 0:
                avg_reset = c.get('reset_duration', 0) / reset_count
                avg_reset_str = _fmt_dur(avg_reset)

            is_running = c.get('is_running', False)
            cycle_id_val = "Running" if is_running else idx + 1
            stop_time_val = "Ongoing..." if is_running else c.get('stop_time_str', 'Unknown')

            cycle_data.append({
                "Select": False, "Cycle ID": cycle_id_val, "Start Time": display_time,
                "Stop Time": stop_time_val,
                "Images": success_count,
                "Avg Time/Img": avg_time_str,
                "Refused": reject_count,
                "Avg Time/Refused": avg_reject_str,
                "Reset": reset_count,
                "Avg Time/Reset": avg_reset_str,
                "Log Lines": c['lines_count'], "_start_idx": c['start_idx'], "_end_idx": c['end_idx']
            })

        df = pd.DataFrame(cycle_data)
        edited_df = st.data_editor(
            df,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select for Deletion", default=False),
                "Stop Time": st.column_config.TextColumn("Stop Time"),
                "Images": st.column_config.NumberColumn("Images", format="%d"),
                "Avg Time/Img": st.column_config.TextColumn("Avg Time/Img"),
                "Refused": st.column_config.NumberColumn("Refused", format="%d"),
                "Avg Time/Refused": st.column_config.TextColumn("Avg Time/Refused"),
                "Reset": st.column_config.NumberColumn("Reset", format="%d"),
                "Avg Time/Reset": st.column_config.TextColumn("Avg Time/Reset"),
                "_start_idx": None, "_end_idx": None
            },
            disabled=["Cycle ID", "Start Time", "Stop Time", "Images", "Avg Time/Img", "Refused", "Avg Time/Refused", "Reset", "Avg Time/Reset", "Log Lines"], 
            hide_index=True,
            width=950
        )

        selected_rows = edited_df[edited_df["Select"] == True]
        valid_rows = selected_rows[selected_rows["Cycle ID"].astype(str) != "Running"]
        
        if not selected_rows.empty and selected_rows.shape[0] > valid_rows.shape[0]:
            st.info("The currently running cycle cannot be deleted. Any selection on it will be ignored.")
            
        if not valid_rows.empty:
            st.warning(f"You have selected {len(valid_rows)} cycle(s) to delete. This action will permanently remove their associated logs from `engine.log`.")
            if st.button("🗑️ Delete Selected Cycles", type="primary", width="stretch"):
                cycles_to_delete = [{'start_idx': row["_start_idx"], 'end_idx': row["_end_idx"]} for _, row in valid_rows.iterrows()]
                with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                to_keep = []
                for i, line in enumerate(lines):
                    if not any(c['start_idx'] <= i <= c['end_idx'] for c in cycles_to_delete):
                        to_keep.append(line)
                with open(LOG_PATH, "w", encoding="utf-8") as f:
                    f.writelines(to_keep)
                st.success(f"Successfully deleted {len(cycles_to_delete)} cycle(s).")
                st.rerun()
