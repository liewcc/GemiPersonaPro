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
st.set_page_config(page_title="GemiPersona Pro | Account Health", page_icon="🏥", layout="wide")
apply_premium_style()

# --- Page Data Initialization ---
config = load_config()
login_data = load_login_lookup()

# Fetch initial data for dropdowns and sidebar (non-fragmented)
# Note: Full data fetching for charts will happen inside fragments
summary_all, all_events_list, log_accs = parse_account_health(target_account="ALL_EVENTS", login_data=login_data)

# Extract unique accounts for the view mode dropdown
lookup_order = [u.get("username", "").lower() for u in login_data if u.get("username")]
log_accs_set = set(log_accs)
lookup_accs_set = set(lookup_order)
final_dropdown_accs = list(lookup_order) + sorted(list(log_accs_set - lookup_accs_set))
final_dropdown_accs = [acc for acc in final_dropdown_accs if acc and acc.lower() != "unknown"]

max_events_raw = max(10, len(all_events_list))
max_available_events = ((max_events_raw + 9) // 10) * 10

# Auto-refresh setting
auto_refresh = st.session_state.get("health_auto_refresh", True)
auto_val = 5 if auto_refresh else None

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

def _build_duration_chart(detailed_data, y_scale_type, event_only_success=False):
    """Build a bar chart of loading durations per event."""
    df = pd.DataFrame(detailed_data[::-1])
    df["Event"] = range(1, len(df) + 1)

    if event_only_success and "health_self" in df.columns:
        df["_dur_col"] = df.apply(
            lambda r: r["health_self"] if r["status"] == "Success" and pd.notna(r.get("health_self")) else r["health"], axis=1)
    else:
        df["_dur_col"] = df["health"]
        
    if "Absolute_Event_Num" in df.columns:
        df["Event"] = df["Absolute_Event_Num"]
    else:
        df["Event"] = range(1, len(df) + 1)
        
    df["Minutes"] = df["_dur_col"].str.replace("s", "").astype(float) / 60.0
    df["cycle"] = df["session_index"].rank(method="dense").astype(int)
    df["variant"] = df["cycle"].apply(lambda x: "Base" if x % 2 == 1 else "Light")
    df["display_status"] = df["status"].replace({"Reject": "Refused"})
    ll = ['Success (Base)', 'Refused (Base)', 'Reset (Base)', 'Fail',
          'Success (Light)', 'Refused (Light)', 'Reset (Light)']
    lr = ['#2ecc71', '#a0a0ff', '#f39c12', '#ff9999', '#a0e6b5', '#d0d0ff', '#f9e79f']
    df['legend'] = df.apply(lambda r: f"{r['display_status']} ({r['variant']})" if r['display_status'] != 'Fail' else 'Fail', axis=1)
    df["Duration"] = df["_dur_col"].str.replace("s", "").astype(float).apply(_fmt_dur)
    
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X('Event:Q', title="Sequence", scale=alt.Scale(nice=False), axis=alt.Axis(format='d', tickMinStep=1)),
        y=alt.Y('Minutes:Q', title="Duration (minutes)", scale=alt.Scale(type=y_scale_type)),
        color=alt.Color('legend:N', scale=alt.Scale(domain=ll, range=lr),
                        legend=alt.Legend(title=None, orient='bottom', columns=4)),
        tooltip=['round', 'time', 'account', 'Duration', 'filename', 'display_status:N']
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
            d["Event"] = row.get("Absolute_Event_Num", len(agg_data) + 1)
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
    agg_df["t_ref"] = agg_df["Rejects"]
    agg_df["t_res"] = agg_df["Resets"]
    agg_df["t_dur_fmt"] = agg_df["Duration"].apply(lambda x: f"{int(x // 60)}:{int(x % 60):02d}")
    melt_ids = ['Event', 'Display', 'Image', 'round', 'account', 'time', 'session_index', 't_dur_fmt', 't_ref', 't_res', 'status']
    plot_df = agg_df.melt(id_vars=melt_ids, value_vars=['t_dur', 'Rejects', 'Resets'], var_name='Metric', value_name='Value')
    plot_df['Metric'] = plot_df['Metric'].replace({'t_dur': 'Duration (minutes)', 'Rejects': 'Refused'})

    cs = alt.Scale(domain=['Duration (minutes)', 'Refused', 'Resets'], range=['#2ecc71', '#a0a0ff', '#f39c12'])
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
            alt.Tooltip('t_dur_fmt:N', title='Duration'), alt.Tooltip('t_ref:Q', title='Refused Count'),
            alt.Tooltip('t_res:Q', title='Reset Count'), alt.Tooltip('status:N', title='Status')
        ]
    )
    return alt.layer(bg_bands, lines, points).resolve_scale(color='independent').properties(height=400).interactive()

def _render_chart_or_table(data, graph_type, y_scale_type, show_graph, label, table_key, event_only_success=False):
    """Unified rendering: either chart or table for a given dataset."""
    if not data:
        st.info(f"No loading records found for {label}.")
        return
    if show_graph:
        st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 4px;'>Performance Graph: <b>{label}</b></p>", unsafe_allow_html=True)
        if graph_type == "Round Duration":
            st.altair_chart(_build_duration_chart(data, y_scale_type, event_only_success=event_only_success), width="stretch")
        else:
            st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 4px;'>Refused Rate: <b>{label}</b> (X-Axis: Successful Images)</p>", unsafe_allow_html=True)
            chart = _build_reject_chart(data, y_scale_type)
            if chart is None:
                st.info("No successful image downloads found to plot trends.")
            else:
                st.altair_chart(chart, width="stretch")
    else:
        st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 4px;'>Loading records: <b>{label}</b>.</p>", unsafe_allow_html=True)
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

def _on_change_event_only_success():
    save_config({"health_event_only_success": st.session_state.widget_event_only_success})

def _on_change_show_last_cycle():
    save_config({"health_show_last_cycle": st.session_state.widget_show_last_cycle})

# ── Render Logic ─────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(["Account Health Analysis", "Automation Cycle Management", "Cycle Performance Insights", "Engine Logs Debugging"])

with tab1:
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 2px; text-transform: uppercase;'>ACCOUNT HEALTH ANALYSIS</p>", unsafe_allow_html=True)
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2.2, 0.8, 0.8, 0.7])
        with c1:
            options = ["Full Loading History (All Events)", "Detailed History: Active Account"] + [f"Detailed History: {acc}" for acc in final_dropdown_accs]
            cfg_val = config.get("health_view_mode", "Full Loading History (All Events)")
            try: view_index = options.index(cfg_val)
            except ValueError: view_index = 0
            view_mode = st.selectbox("Select View Mode", options=options, index=view_index, key="widget_health_view_mode", on_change=_on_change_health_view, help="Choose between a complete history of all loading events or detailed history for a specific account.")
        
        is_full = view_mode == "Full Loading History (All Events)"
        is_active = view_mode == "Detailed History: Active Account"
        
        if "show_health_graph" not in st.session_state:
            st.session_state.show_health_graph = True

        with c2:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            if st.button("Refresh Log", icon="🔄", width="stretch"):
                st.rerun()
        with c3:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            lbl = "Show Table" if st.session_state.show_health_graph else "Plot Graph"
            ico = "📋" if st.session_state.show_health_graph else "📊"
            if st.button(lbl, icon=ico, width="stretch"):
                st.session_state.show_health_graph = not st.session_state.show_health_graph
                st.rerun()
        with c4:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            st.toggle("Auto-refresh", value=True, key="health_auto_refresh")

        cfg_n_rounds = st.session_state.get("widget_health_n_rounds", config.get("health_n_rounds", 100))
        safe_n_rounds = min(cfg_n_rounds, max_available_events)
        
        if st.session_state.show_health_graph:
            col_slider, col_rad, col_scale = st.columns([2.0, 1.4, 0.6])
            graph_opts = ["Round Duration", "Retry Analysis"]
            scale_opts = ["Linear", "Logarithmic"]
            cur_graph = st.session_state.get("widget_health_graph_type", config.get("health_graph_type", "Round Duration"))
            try: graph_idx = graph_opts.index(cur_graph)
            except ValueError: graph_idx = 0
            cur_scale = st.session_state.get("widget_health_y_scale", config.get("health_y_scale", "Linear"))
            try: scale_idx = scale_opts.index(cur_scale)
            except ValueError: scale_idx = 0
            
            with col_slider:
                with st.container(border=True):
                    st.slider("Show Last N Events", min_value=10, max_value=max_available_events, value=safe_n_rounds, step=10, key="widget_health_n_rounds", on_change=_on_change_health_n_rounds)
                    cfg_last_cycle = st.session_state.get("widget_show_last_cycle", config.get("health_show_last_cycle", False))
                    st.toggle(
                        "Show Last Cycle Only",
                        value=cfg_last_cycle,
                        key="widget_show_last_cycle",
                        on_change=_on_change_show_last_cycle,
                        help="ON: Limit the events to the most recent automation cycle only."
                    )
            with col_rad:
                with st.container(border=True):
                    cr1, cr2 = st.columns([1.0, 1.4])
                    with cr1:
                        st.radio("Graph Mode", graph_opts, index=graph_idx, horizontal=False, key="widget_health_graph_type", on_change=_on_change_health_graph)
                    with cr2:
                        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                        is_round_dur = (cur_graph == "Round Duration")
                        cfg_eos = st.session_state.get("widget_event_only_success", config.get("health_event_only_success", False))
                        st.toggle(
                            "Event-Only Success Duration",
                            value=cfg_eos if is_round_dur else False,
                            disabled=not is_round_dur,
                            key="widget_event_only_success",
                            on_change=_on_change_event_only_success,
                            help="ON: Success bars show only the final attempt duration (same as Refused/Reset). OFF: Success bars show the cumulative round duration (from last success to this success)."
                        )
            with col_scale:
                with st.container(border=True):
                    st.radio("Y-Axis Scale", scale_opts, index=scale_idx, horizontal=False, key="widget_health_y_scale", on_change=_on_change_health_y_scale, help="Y-Axis Scale: Linear or Logarithmic")

        # Fragment for independent refreshing
        @st.fragment(run_every=auto_val)
        def _health_fragment():
            fresh_login_data = load_login_lookup()
            # Pull immediate state from session_state for snappy UI adjustment
            graph_type = st.session_state.get("widget_health_graph_type", config.get("health_graph_type", "Round Duration"))
            y_scale_type = 'symlog' if st.session_state.get("widget_health_y_scale", config.get("health_y_scale", "Linear")) == "Logarithmic" else 'linear'
            n_rounds = st.session_state.get("widget_health_n_rounds", config.get("health_n_rounds", 100))
            show_last_cycle = st.session_state.get("widget_show_last_cycle", config.get("health_show_last_cycle", False))
            event_only_success = st.session_state.get("widget_event_only_success", config.get("health_event_only_success", False)) and graph_type == "Round Duration"
            show_graph = st.session_state.get("show_health_graph", True)

            def _apply_filters(data, all_events_ref):
                # Assign true sequence numbers before any slicing, so charts show actual chronological position
                total_events = len(data)
                for idx, record in enumerate(data):
                    record["Absolute_Event_Num"] = total_events - idx
                    
                # Filter for last cycle if enabled
                if show_last_cycle and data and all_events_ref:
                    latest_s_id = all_events_ref[0].get("session_index")
                    filtered_data = [d for d in data if d.get("session_index") == latest_s_id]
                else:
                    filtered_data = data
                    
                # Slice to requested N rounds (which are the newest N events)
                return filtered_data[:n_rounds]

            if is_full:
                _, fresh_all_detailed, _ = parse_account_health(target_account="ALL_EVENTS", login_data=fresh_login_data)
                _render_chart_or_table(_apply_filters(fresh_all_detailed, fresh_all_detailed), graph_type, y_scale_type, show_graph, "All Events", "health_full_history_table", event_only_success=event_only_success)
            elif is_active:
                _active_user = next((u.get("username", "") for u in fresh_login_data if u.get("active")), None)
                if not _active_user:
                    st.info("No active account is currently set.")
                else:
                    _, det, _ = parse_account_health(target_account=_active_user.lower(), login_data=fresh_login_data)
                    _, all_ref, _ = parse_account_health(target_account="ALL_EVENTS", login_data=fresh_login_data)
                    _render_chart_or_table(_apply_filters(det, all_ref), graph_type, y_scale_type, show_graph, f"{_active_user} (Active Account)", "health_active_account_table", event_only_success=event_only_success)
            else:
                target_acc = view_mode.replace("Detailed History: ", "")
                _, det, _ = parse_account_health(target_account=target_acc, login_data=fresh_login_data)
                _, all_ref, _ = parse_account_health(target_account="ALL_EVENTS", login_data=fresh_login_data)
                _render_chart_or_table(_apply_filters(det, all_ref), graph_type, y_scale_type, show_graph, target_acc, f"health_detailed_{target_acc}", event_only_success=event_only_success)

        _health_fragment()

with tab2:
    @st.fragment()
    def _cycle_management_fragment():
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
                        s_dt = datetime.strptime(c['start_time_str'], '%H:%M:%S')
                        e_dt = datetime.strptime(c.get('stop_time_str', c['start_time_str']), '%H:%M:%S')
                        t_sec = int((e_dt - s_dt).total_seconds())
                        if t_sec < 0: t_sec += 86400
                        avg_time_str = _fmt_dur(t_sec / success_count)
                    except: pass
                
                reject_count = c.get('reject_count', 0)
                avg_reject_str = _fmt_dur(c.get('reject_duration', 0) / reject_count) if reject_count > 0 else "N/A"
                reset_count = c.get('reset_count', 0)
                avg_reset_str = _fmt_dur(c.get('reset_duration', 0) / reset_count) if reset_count > 0 else "N/A"

                is_running = c.get('is_running', False)
                duration_str = "N/A"
                try:
                    s_dt = datetime.strptime(c['start_time_str'], '%H:%M:%S')
                    e_dt = datetime.strptime(c.get('stop_time_str', c['start_time_str']), '%H:%M:%S')
                    dsec = int((e_dt - s_dt).total_seconds())
                    if dsec < 0: dsec += 86400
                    duration_str = f"{dsec // 3600}:{(dsec % 3600) // 60:02d}"
                except: pass

                cycle_data.append({
                    "Select": False, "Cycle ID": "Running" if is_running else idx + 1, "Start Time": display_time,
                    "Stop Time": "Ongoing..." if is_running else c.get('stop_time_str', 'Unknown'),
                    "Duration": duration_str, "Images": success_count, "Avg Time/Img": avg_time_str,
                    "Refused": reject_count, "Avg Time/Refused": avg_reject_str,
                    "Reset": reset_count, "Avg Time/Reset": avg_reset_str,
                    "Log Lines": c['lines_count'], "Events": success_count + reject_count + reset_count, "_start_idx": c['start_idx'], "_end_idx": c['end_idx']
                })

            df = pd.DataFrame(cycle_data)
            edited_df = st.data_editor(
                df,
                column_config={
                    "Select": st.column_config.CheckboxColumn("Select for Deletion", default=False),
                    "Events": st.column_config.NumberColumn("Events", format="%d"),
                    "_start_idx": None, "_end_idx": None
                },
                disabled=["Cycle ID", "Start Time", "Stop Time", "Duration", "Images", "Avg Time/Img", "Refused", "Avg Time/Refused", "Reset", "Avg Time/Reset", "Log Lines", "Events"], 
                hide_index=True, width="stretch", key="automation_cycle_editor"
            )

            selected_rows = edited_df[edited_df["Select"] == True]
            valid_rows = selected_rows[selected_rows["Cycle ID"].astype(str) != "Running"]
            if not valid_rows.empty:
                st.warning(f"Delete {len(valid_rows)} cycle(s)?")
                if st.button("🗑️ Delete Selected Cycles", type="primary", width="stretch"):
                    cycles_to_del = [{'start_idx': row["_start_idx"], 'end_idx': row["_end_idx"]} for _, row in valid_rows.iterrows()]
                    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f: lines = f.readlines()
                    to_keep = [line for i, line in enumerate(lines) if not any(c['start_idx'] <= i <= c['end_idx'] for c in cycles_to_del)]
                    with open(LOG_PATH, "w", encoding="utf-8") as f: f.writelines(to_keep)
                    st.success("Deleted."); st.rerun()

    _cycle_management_fragment()

with tab3:
    @st.fragment()
    def _performance_insights_fragment():
        st.markdown("### ⏱️ Cycle Performance Insights")
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 2px; text-transform: uppercase;'>CYCLE PERFORMANCE INSIGHTS</p>", unsafe_allow_html=True)
        
        cycles = parse_engine_cycles()
        _, all_detailed, _ = parse_account_health(target_account="ALL_EVENTS", login_data=load_login_lookup())
        
        cycle_opts = [f"Cycle {i+1} ({c.get('full_start_time', c['start_time_str'])} - {c.get('stop_time_str', 'Ongoing...')})" for i, c in enumerate(cycles)]
        if not cycle_opts:
            st.info("No automation cycles recorded yet.")
            return

        with st.container(border=True):
            c1, c2 = st.columns([2.0, 1.0])
            with c1:
                selected_cycle_str = st.selectbox("Select Cycle", list(reversed(cycle_opts)), key="tab3_cycle_select")
                selected_cycle_id = int(selected_cycle_str.split(" ")[1])
                
            selected_cycle = cycles[selected_cycle_id - 1]
            cycle_events = [e for e in all_detailed if selected_cycle['start_idx'] <= e.get("log_line_idx", -1) <= (selected_cycle['end_idx'] or 999999999)]
            
            stats = []
            for e in reversed(cycle_events):
                s_id = e.get("session_index")
                dur = float(e.get("health_self", e.get("health", "0s")).replace("s", ""))
                st_val = e.get("status", "")
                success_val = 1 if st_val == "Success" else 0
                reject_val = 1 if st_val == "Reject" else 0
                reset_val = 1 if st_val == "Reset" else 0
                if stats and stats[-1]["session_index"] == s_id:
                    stats[-1]["duration"] += dur; stats[-1]["events"] += 1
                    stats[-1]["images"] += success_val; stats[-1]["refused"] += reject_val; stats[-1]["reset"] += reset_val
                else:
                    stats.append({"session_index": s_id, "account": e.get("account", "Unknown"), "duration": dur, "events": 1, "images": success_val, "refused": reject_val, "reset": reset_val, "start_time": e.get("time", "Unknown")})
            
            with c2:
                n_accs = st.slider("Show Last N Accounts", 1, max(1, len(stats)), len(stats), key="tab3_n_accounts") if stats else 0
                    
        if not stats: return
        view_stats = stats[-n_accs:] if n_accs < len(stats) else stats
        chart_data = []
        for i, s in enumerate(view_stats):
            c_type = "Even" if i % 2 == 0 else "Odd"
            color_val = f"Image_{c_type}" if s["images"] > 0 else c_type
            chart_data.append({"Switch": i+1, "Display": s['start_time'] + "\u200b"*i, "Account": s["account"], "Duration (Minutes)": s["duration"]/60.0, "Duration": _fmt_dur(s["duration"]), "Events": s["events"], "Images": s["images"], "Refused": s["refused"], "Reset": s["reset"], "Color": color_val})
        
        df_chart = pd.DataFrame(chart_data)
        st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 4px;'>Account Switch Duration Chart</p>", unsafe_allow_html=True)
        bar = alt.Chart(df_chart).mark_bar().encode(
            x=alt.X('Display:O', title="Switch Time", sort=alt.EncodingSortField(field="Switch")),
            y=alt.Y('Duration (Minutes):Q', title="Duration (minutes)"),
            color=alt.Color('Color:N', scale=alt.Scale(domain=["Even", "Odd", "Image_Even", "Image_Odd"], range=["#4f8bf9", "#a0c0ff", "#2ecc71", "#a0e6b5"]), legend=None),
            tooltip=['Account', 'Duration', 'Events', 'Images', 'Refused', 'Reset']
        )
        text = alt.Chart(df_chart).mark_text(
            align='center',
            baseline='bottom',
            dy=-3,
            color='white',
            fontSize=11,
            fontWeight='bold'
        ).encode(
            x=alt.X('Display:O', sort=alt.EncodingSortField(field="Switch")),
            y=alt.Y('Duration (Minutes):Q'),
            text=alt.Text('Images:Q')
        )
        chart = alt.layer(bar, text).properties(height=400).interactive(bind_y=False)
        st.altair_chart(chart, width="stretch")
        st.dataframe(df_chart, column_config={"Switch": "Seq", "Duration (Minutes)": None, "Color": None}, width="stretch", hide_index=True)

    _performance_insights_fragment()

with tab4:
    @st.fragment()
    def _engine_logs_debugging_fragment():
        def _clr(): st.session_state.debug_logs_output = ""
        cycles = parse_engine_cycles()
        c_opts = ["All"] + [f"Cycle {i+1}: {c['start_time_str']} - {c.get('stop_time_str', 'Ongoing...')}" for i, c in enumerate(cycles)]
            
        with st.container(border=True):
            c1, c2, c3, c4, c5, c6 = st.columns([1.6, 0.9, 0.5, 0.5, 1.2, 0.7])
            with c1:
                sel_cycle = st.selectbox("Select Cycle", c_opts, key="tab4_cycle_select", on_change=_clr)
            
            is_all = (sel_cycle == "All")
            l_count, e_count, cycle_events_natural = 0, 0, []
            if not is_all:
                try:
                    c_idx = int(sel_cycle.split(":")[0].replace("Cycle ", "")) - 1
                    c_info = cycles[c_idx]
                    l_count = c_info['lines_count']
                    _, all_ev, _ = parse_account_health(target_account="ALL_EVENTS", login_data=load_login_lookup())
                    cycle_events_natural = [e for e in reversed(all_ev) if c_info['start_idx'] <= e.get('log_line_idx', -1) <= (c_info['end_idx'] or 999999999)]
                    e_count = len(cycle_events_natural)
                    with c1: st.markdown(f"<p style='font-size: 0.8em; color: #a0a0ff; margin-top: -15px;'>📊 Lines: <b>{l_count}</b> | Events: <b>{e_count}</b></p>", unsafe_allow_html=True)
                except: pass

            with c2: mode = st.selectbox("Filter Mode", ["Log Lines", "Events"], key="tab4_filter_mode", on_change=_clr, disabled=is_all)
            mv = l_count if not is_all and mode == "Log Lines" else (e_count if not is_all else 1000000)

            with c3: sv = st.number_input("Start", 1, max(1, mv), 1, key="tab4_start", on_change=_clr, disabled=is_all)
            with c4: ev = st.number_input("End", 1, max(1, mv), mv if not is_all else 1, key="tab4_end", on_change=_clr, disabled=is_all)

            with c5:
                st.radio("First Line", ["Top", "Bottom"], index=1, horizontal=True, key="tab4_order", on_change=_clr)

            with c6:
                st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                if st.button("Show", icon="📋", width="stretch", key="tab4_show_btn"):
                    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f: lines = f.readlines()
                    if is_all: out = lines
                    else:
                        try:
                            if mode == "Log Lines":
                                out = lines[c_info['start_idx'] + (sv-1) : c_info['start_idx'] + (ev-1) + 1]
                            else:
                                s_idx = cycle_events_natural[sv-1].get('log_line_idx', c_info['start_idx'])
                                e_idx = cycle_events_natural[ev-1].get('log_line_idx', len(lines)-1)
                                out = lines[s_idx:e_idx+1]
                        except: out = []
                    logs_clean = [l.strip() for l in out if l.strip()]
                    if st.session_state.get("tab4_order") == "Top":
                        st.session_state.debug_logs_output = "\n".join(logs_clean)
                    else:
                        st.session_state.debug_logs_output = "\n".join(reversed(logs_clean))
        if st.session_state.get("debug_logs_output"):
            st.markdown("<p style='color: #a0a0ff; font-weight: bold; margin-top: 8px;'>ENGINE DEBUG LOGS</p>", unsafe_allow_html=True)
            with st.container(height=580, border=True): st.code(st.session_state.debug_logs_output, language="text")

    _engine_logs_debugging_fragment()
