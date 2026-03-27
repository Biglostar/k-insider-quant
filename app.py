"""
K-Insider Quant Monitor v2.0 - 메인 대시보드
기본 대시보드 + 헤지펀드 스타일 고급 분석 4종
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime, timedelta

from config import DEMO_MODE, DEFAULT_MIN_RATIO, POSITION_WEIGHTS
from database import (
    init_db, upsert_trades, query_trades,
    query_sector_summary, query_daily_counts, get_all_dates,
)
from collector import collect_data
from filter_engine import apply_quant_filter, add_signal_scores, get_top_signals
from advanced_analytics import (
    detect_clusters,
    classify_trader_pattern,
    calculate_skin_in_game,
    calculate_net_buying,
    run_event_study,
)


# ─────────────────────────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="K-Insider Quant Monitor",
    page_icon="K",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 커스텀 CSS ───────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }

    .kpi-card {
        background: linear-gradient(135deg, #1A1F2E 0%, #252B3B 100%);
        border: 1px solid #2D3748;
        border-radius: 12px;
        padding: 20px 24px;
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 20px rgba(0, 212, 170, 0.15);
    }
    .kpi-value {
        font-size: 2.4rem; font-weight: 700; color: #00D4AA;
        margin: 8px 0 4px 0; line-height: 1.1;
    }
    .kpi-label {
        font-size: 0.85rem; color: #8892A4;
        text-transform: uppercase; letter-spacing: 1px;
    }
    .kpi-sub { font-size: 0.78rem; color: #5A6577; margin-top: 4px; }

    .badge-kospi {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 0.75rem; font-weight: 600;
        background: #007BFF22; color: #4DA3FF; border: 1px solid #007BFF44;
    }
    .badge-kosdaq {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 0.75rem; font-weight: 600;
        background: #FF6B3522; color: #FF8F60; border: 1px solid #FF6B3544;
    }

    .score-badge {
        display: inline-block; padding: 4px 12px; border-radius: 20px;
        font-weight: 600; font-size: 0.85rem;
    }
    .score-high   { background: #00D4AA22; color: #00D4AA; border: 1px solid #00D4AA44; }
    .score-medium { background: #FFB02022; color: #FFB020; border: 1px solid #FFB02044; }
    .score-low    { background: #FF606022; color: #FF6060; border: 1px solid #FF606044; }

    .signal-strong { color: #00D4AA; font-weight: 700; }
    .signal-mid    { color: #FFB020; font-weight: 700; }
    .signal-weak   { color: #FF6060; font-weight: 700; }

    .demo-banner {
        background: linear-gradient(90deg, #FF6B3520, #FF6B3510);
        border: 1px solid #FF6B3540; border-radius: 8px;
        padding: 10px 16px; margin-bottom: 16px;
        text-align: center; color: #FF6B35; font-size: 0.9rem;
    }

    section[data-testid="stSidebar"] {
        background-color: #141820; border-right: 1px solid #2D3748;
    }

    .header-line {
        height: 3px;
        background: linear-gradient(90deg, #00D4AA, #007BFF, #00D4AA);
        border-radius: 2px; margin: 8px 0 24px 0;
    }
    .section-title {
        color: #E0E0E0; font-size: 1.15rem; font-weight: 600;
        margin: 32px 0 12px 0; padding-left: 12px;
        border-left: 3px solid #00D4AA;
    }

    .data-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    .data-table th {
        background: #1A1F2E; color: #8892A4; padding: 10px 12px;
        text-align: left; border-bottom: 2px solid #2D3748;
        font-weight: 600; font-size: 0.8rem;
        text-transform: uppercase; letter-spacing: 0.5px;
    }
    .data-table td {
        padding: 10px 12px; border-bottom: 1px solid #1E2436; color: #C8CED8;
    }
    .data-table tr:hover td { background: #1A1F2E; }

    /* 패턴 뱃지 */
    .badge-opp {
        display: inline-block; padding: 3px 10px; border-radius: 4px;
        font-size: 0.8rem; font-weight: 600;
        background: #FF220022; color: #FF4444; border: 1px solid #FF444444;
    }
    .badge-routine {
        display: inline-block; padding: 3px 10px; border-radius: 4px;
        font-size: 0.8rem; font-weight: 600;
        background: #66666622; color: #888888; border: 1px solid #88888844;
    }
    .badge-single {
        display: inline-block; padding: 3px 10px; border-radius: 4px;
        font-size: 0.8rem; font-weight: 600;
        background: #007BFF22; color: #4DA3FF; border: 1px solid #007BFF44;
    }

    /* Net 방향 */
    .net-buy  { color: #00D4AA; font-weight: 700; }
    .net-sell { color: #FF6060; font-weight: 700; }
    .net-neutral { color: #888888; }

    /* 정보 누출 */
    .leak-suspect { color: #FF4444; font-weight: 700; }
    .leak-minor   { color: #FFB020; }
    .leak-none    { color: #5A6577; }

    a { color: #00D4AA !important; }
    a:hover { color: #00FFD0 !important; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# 데이터 초기화
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def initialize():
    init_db()
    df = collect_data()
    if not df.empty:
        upsert_trades(df)
    return True

initialize()


# ─────────────────────────────────────────────────────────────
# 공통 유틸
# ─────────────────────────────────────────────────────────────
def market_badge(market_val):
    if market_val == "KOSPI":
        return "<span class='badge-kospi'>KOSPI</span>"
    elif market_val == "KOSDAQ":
        return "<span class='badge-kosdaq'>KOSDAQ</span>"
    return "<span style='color:#5A6577;'>-</span>"


# ─────────────────────────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## K-Insider Quant")
    st.markdown("---")

    available_dates = get_all_dates()
    if available_dates:
        date_mode = st.radio(
            "조회 기간", ["오늘", "최근 7일", "최근 30일", "직접 선택"],
            horizontal=True,
        )
        if date_mode == "오늘":
            start_date = end_date = available_dates[0]
        elif date_mode == "최근 7일":
            end_date = available_dates[0]
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        elif date_mode == "최근 30일":
            end_date = available_dates[0]
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
        else:
            c1, c2 = st.columns(2)
            with c1:
                start_date = st.date_input("시작일", value=datetime.strptime(available_dates[-1], "%Y-%m-%d")).strftime("%Y-%m-%d")
            with c2:
                end_date = st.date_input("종료일", value=datetime.strptime(available_dates[0], "%Y-%m-%d")).strftime("%Y-%m-%d")
    else:
        start_date = end_date = datetime.now().strftime("%Y-%m-%d")

    st.markdown("---")
    min_ratio = st.slider("최소 매수 비중 (%)", 0.01, 1.0, DEFAULT_MIN_RATIO, 0.01, format="%.2f%%")
    st.markdown("---")
    selected_positions = st.multiselect("직위 필터", list(POSITION_WEIGHTS.keys()), default=None, placeholder="전체")
    st.markdown("---")
    market_filter = st.multiselect("시장 필터", ["KOSPI", "KOSDAQ"], default=None, placeholder="전체")
    st.markdown("---")
    show_noise = st.checkbox("노이즈 포함 (증여/상속 등)", value=False)
    st.markdown("---")
    st.markdown("<div style='text-align:center; color:#5A6577; font-size:0.75rem;'>K-Insider Quant Monitor v2.0</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# 데이터 조회
# ─────────────────────────────────────────────────────────────
signal_types = ["BUY"] if not show_noise else ["BUY", "NOISE", "NORMAL"]

raw_df = query_trades(
    start_date=start_date, end_date=end_date,
    signal_only=not show_noise, min_ratio=min_ratio,
    positions=selected_positions if selected_positions else None,
)
# 노이즈 포함 전체 데이터 (고급 분석용)
full_df = query_trades(
    start_date=start_date, end_date=end_date,
    signal_only=False, min_ratio=0,
)

filtered_df = apply_quant_filter(
    raw_df, min_ratio=min_ratio,
    positions=selected_positions if selected_positions else None,
    signal_types=signal_types,
)
if market_filter and not filtered_df.empty:
    filtered_df = filtered_df[filtered_df["market"].isin(market_filter)]
if market_filter and not full_df.empty:
    full_df = full_df[full_df["market"].isin(market_filter)]

scored_df = add_signal_scores(filtered_df)


# ─────────────────────────────────────────────────────────────
# 헤더
# ─────────────────────────────────────────────────────────────
st.markdown("<h1 style='margin-bottom:0; color:#E0E0E0;'>K-Insider Quant Monitor</h1>", unsafe_allow_html=True)
st.markdown("<div class='header-line'></div>", unsafe_allow_html=True)

if DEMO_MODE:
    st.markdown(
        "<div class='demo-banner'>"
        "<b>DEMO MODE</b> — 시뮬레이션 데이터입니다. "
        "<code>DART_API_KEY</code> 환경 변수를 설정하면 실제 데이터로 전환됩니다."
        "</div>", unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════
# 탭 구성
# ═════════════════════════════════════════════════════════════
tab_main, tab_cluster, tab_pattern, tab_skin, tab_event = st.tabs([
    "Dashboard",
    "Cluster Analysis",
    "Routine vs Opportunistic",
    "Skin in the Game",
    "Event Study",
])


# ═════════════════════════════════════════════════════════════
# TAB 1: DASHBOARD (기존 메인)
# ═════════════════════════════════════════════════════════════
with tab_main:
    # KPI 카드
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'>포착된 매수 신호</div><div class='kpi-value'>{len(scored_df)}</div><div class='kpi-sub'>필터 조건 충족 건수</div></div>", unsafe_allow_html=True)
    with c2:
        uq = scored_df["stock_code"].nunique() if not scored_df.empty else 0
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'>고유 종목 수</div><div class='kpi-value'>{uq}</div><div class='kpi-sub'>중복 제거 기준</div></div>", unsafe_allow_html=True)
    with c3:
        if not scored_df.empty:
            tr = scored_df.iloc[0]; tn = tr["corp_name"]; tp = tr["buy_ratio"]
        else:
            tn = "-"; tp = 0
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'>최대 매수 종목</div><div class='kpi-value' style='font-size:1.4rem;'>{tn}</div><div class='kpi-sub'>매수 비중 {tp:.2f}%</div></div>", unsafe_allow_html=True)
    with c4:
        avg_s = scored_df["signal_score"].mean() if not scored_df.empty else 0
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'>평균 신호 점수</div><div class='kpi-value'>{avg_s:.1f}</div><div class='kpi-sub'>0~100 스케일</div></div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 테이블
    st.markdown("<div class='section-title'>필터링된 내부자 매수 리스트</div>", unsafe_allow_html=True)
    if not scored_df.empty:
        tbl = "<table class='data-table'><tr><th>보고일</th><th>종목명</th><th>시장</th><th>섹터</th><th>보고자</th><th>직위</th><th>변동사유</th><th>변동수량</th><th>매수비중</th><th>신호점수</th><th>현재가</th><th>원문</th></tr>"
        for _, r in scored_df.iterrows():
            sc = r.get("signal_score", 0)
            sc_cls = "score-high" if sc >= 70 else ("score-medium" if sc >= 45 else "score-low")
            tbl += f"<tr><td>{r['report_date']}</td><td style='color:#E0E0E0;font-weight:600;'>{r['corp_name']} <span style='color:#5A6577;font-size:0.78rem;'>({r['stock_code']})</span></td><td>{market_badge(r.get('market',''))}</td><td style='color:#8892A4;'>{r.get('sector','기타')}</td><td>{r['reporter_name']}</td><td>{r['position']}</td><td>{r['change_reason']}</td><td style='text-align:right;'>{int(r['shares_changed']):,}</td><td style='text-align:right;color:#00D4AA;font-weight:600;'>{r['buy_ratio']:.3f}%</td><td><span class='score-badge {sc_cls}'>{sc}</span></td><td style='text-align:right;'>W{int(r['current_price']):,}</td><td><a href='{r['dart_url']}' target='_blank'>보기</a></td></tr>"
        tbl += "</table>"
        st.markdown(tbl, unsafe_allow_html=True)
        st.download_button("CSV 다운로드", scored_df.to_csv(index=False, encoding="utf-8-sig"), f"k_insider_{start_date}_{end_date}.csv", "text/csv")
    else:
        st.info("선택한 조건에 맞는 매수 신호가 없습니다.")

    st.markdown("<br>", unsafe_allow_html=True)

    # 차트
    ch1, ch2 = st.columns(2)
    with ch1:
        st.markdown("<div class='section-title'>섹터별 매수 현황 (최근 30일)</div>", unsafe_allow_html=True)
        sector_df = query_sector_summary(days=30)
        if not sector_df.empty:
            fig = px.bar(sector_df, x="sector", y="buy_count", color="avg_ratio",
                         color_continuous_scale=["#1A1F2E", "#00D4AA"],
                         labels={"buy_count":"매수 건수","sector":"섹터","avg_ratio":"평균 비중(%)"},
                         text="buy_count")
            fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font_color="#E0E0E0", margin=dict(l=20,r=20,t=30,b=20), height=380)
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

    with ch2:
        st.markdown("<div class='section-title'>일별 매수 신호 추이 (최근 30일)</div>", unsafe_allow_html=True)
        daily_df = query_daily_counts(days=30)
        if not daily_df.empty:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=daily_df["report_date"], y=daily_df["signal_count"],
                                      mode="lines+markers", name="전체 매수 신호",
                                      line=dict(color="#00D4AA",width=2), fill="tozeroy",
                                      fillcolor="rgba(0,212,170,0.1)"))
            fig2.add_trace(go.Scatter(x=daily_df["report_date"], y=daily_df["top_exec_count"],
                                      mode="lines+markers", name="C-Level 매수",
                                      line=dict(color="#FFB020",width=2,dash="dot"),
                                      marker=dict(symbol="diamond")))
            fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                               font_color="#E0E0E0", margin=dict(l=20,r=20,t=30,b=20), height=380,
                               legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1))
            st.plotly_chart(fig2, use_container_width=True)


# ═════════════════════════════════════════════════════════════
# TAB 2: CLUSTER ANALYSIS
# ═════════════════════════════════════════════════════════════
with tab_cluster:
    st.markdown("<div class='section-title'>Cluster &amp; Breadth Analysis</div>", unsafe_allow_html=True)
    st.markdown("""
    <div style='color:#8892A4; font-size:0.9rem; margin-bottom:20px; line-height:1.6;'>
    동일 종목에 대해 <b style='color:#E0E0E0;'>여러 임원이 동시에 매수</b>한 경우를 감지합니다.
    한 명의 CEO가 사는 것보다, 서로 다른 직급의 임원들이 함께 사는 것이 통계적으로 더 강력한 상승 신호입니다.
    클러스터 강도는 참여 직급의 다양성(Breadth), 직위 수준, 매수 규모를 종합하여 산출합니다.
    </div>
    """, unsafe_allow_html=True)

    cl1, cl2 = st.columns([1, 3])
    with cl1:
        cluster_window = st.slider("클러스터 탐지 기간 (일)", 7, 30, 14)
        cluster_min = st.slider("최소 매수자 수", 2, 5, 2)

    cluster_df = detect_clusters(full_df, window_days=cluster_window, min_buyers=cluster_min)

    with cl2:
        if not cluster_df.empty:
            # KPI
            kc1, kc2, kc3 = st.columns(3)
            with kc1:
                st.markdown(f"<div class='kpi-card'><div class='kpi-label'>클러스터 감지</div><div class='kpi-value'>{len(cluster_df)}</div><div class='kpi-sub'>종목 수</div></div>", unsafe_allow_html=True)
            with kc2:
                max_strength = cluster_df["cluster_strength"].max()
                st.markdown(f"<div class='kpi-card'><div class='kpi-label'>최대 강도</div><div class='kpi-value'>{max_strength:.0f}</div><div class='kpi-sub'>0~100 스케일</div></div>", unsafe_allow_html=True)
            with kc3:
                avg_buyers = cluster_df["buyer_count"].mean()
                st.markdown(f"<div class='kpi-card'><div class='kpi-label'>평균 매수자</div><div class='kpi-value'>{avg_buyers:.1f}</div><div class='kpi-sub'>명/클러스터</div></div>", unsafe_allow_html=True)

    if not cluster_df.empty:
        st.markdown("<br>", unsafe_allow_html=True)

        for _, cl in cluster_df.iterrows():
            strength = cl["cluster_strength"]
            if strength >= 70:
                s_cls = "score-high"
            elif strength >= 45:
                s_cls = "score-medium"
            else:
                s_cls = "score-low"

            st.markdown(f"""
            <div style='background:linear-gradient(135deg,#1A1F2E,#1E2436);border:1px solid #2D3748;border-radius:10px;padding:16px 20px;margin-bottom:10px;'>
                <div style='display:flex;justify-content:space-between;align-items:center;'>
                    <div>
                        <span style='font-size:1.1rem;font-weight:700;color:#E0E0E0;'>{cl["corp_name"]}</span>
                        <span style='color:#5A6577;margin-left:8px;'>({cl["stock_code"]})</span>
                        {market_badge(cl.get("market",""))}
                    </div>
                    <span class='score-badge {s_cls}'>Strength {strength:.0f}</span>
                </div>
                <div style='display:flex;gap:24px;margin-top:10px;color:#8892A4;font-size:0.88rem;'>
                    <span>매수자 {cl["buyer_count"]}명: {cl["buyers"]}</span>
                </div>
                <div style='display:flex;gap:24px;margin-top:4px;color:#8892A4;font-size:0.88rem;'>
                    <span>직급: {cl["positions"]}</span>
                    <span>평균 비중: {cl["avg_ratio"]:.3f}%</span>
                    <span>기간: {cl["window_start"]} ~ {cl["window_end"]}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("현재 조건에서 클러스터 매수가 감지되지 않았습니다. 탐지 기간을 늘리거나 최소 매수자 수를 줄여보세요.")


# ═════════════════════════════════════════════════════════════
# TAB 3: ROUTINE vs OPPORTUNISTIC
# ═════════════════════════════════════════════════════════════
with tab_pattern:
    st.markdown("<div class='section-title'>Routine vs Opportunistic Trader Classification</div>", unsafe_allow_html=True)
    st.markdown("""
    <div style='color:#8892A4; font-size:0.9rem; margin-bottom:20px; line-height:1.6;'>
    내부자의 과거 매수 패턴을 분석하여 <b style='color:#FF4444;'>Opportunistic (기회주의적)</b> 매수와
    <b style='color:#888888;'>Routine (정기적)</b> 매수를 구분합니다.
    평소 안 사다가 갑자기 매수하는 패턴이 정보 가치가 훨씬 높습니다.
    매수 간격의 변동계수(CV)를 이용하여 규칙성을 수치화합니다.
    </div>
    """, unsafe_allow_html=True)

    pattern_df = classify_trader_pattern(full_df)

    if not pattern_df.empty:
        # 요약 KPI
        pk1, pk2, pk3, pk4 = st.columns(4)
        opp_count = len(pattern_df[pattern_df["pattern"] == "Opportunistic"])
        routine_count = len(pattern_df[pattern_df["pattern"].isin(["Routine", "Semi-Routine"])])
        single_count = len(pattern_df[pattern_df["pattern"] == "Single"])

        with pk1:
            st.markdown(f"<div class='kpi-card'><div class='kpi-label'>Opportunistic</div><div class='kpi-value' style='color:#FF4444;'>{opp_count}</div><div class='kpi-sub'>신호 배수 x1.5</div></div>", unsafe_allow_html=True)
        with pk2:
            st.markdown(f"<div class='kpi-card'><div class='kpi-label'>Single</div><div class='kpi-value' style='color:#4DA3FF;'>{single_count}</div><div class='kpi-sub'>판별 불가 (1건)</div></div>", unsafe_allow_html=True)
        with pk3:
            st.markdown(f"<div class='kpi-card'><div class='kpi-label'>Routine</div><div class='kpi-value' style='color:#888888;'>{routine_count}</div><div class='kpi-sub'>신호 배수 x0.5~0.8</div></div>", unsafe_allow_html=True)
        with pk4:
            st.markdown(f"<div class='kpi-card'><div class='kpi-label'>전체 트레이더</div><div class='kpi-value'>{len(pattern_df)}</div><div class='kpi-sub'>보고자-종목 조합</div></div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # 테이블
        tbl = "<table class='data-table'><tr><th>보고자</th><th>종목</th><th>시장</th><th>직위</th><th>패턴</th><th>거래횟수</th><th>평균간격(일)</th><th>평균비중</th><th>신호배수</th><th>기간</th></tr>"
        for _, r in pattern_df.iterrows():
            if r["pattern"] == "Opportunistic":
                p_badge = "<span class='badge-opp'>Opportunistic</span>"
            elif r["pattern"] in ["Routine", "Semi-Routine"]:
                p_badge = f"<span class='badge-routine'>{r['pattern']}</span>"
            else:
                p_badge = "<span class='badge-single'>Single</span>"

            boost_color = "#FF4444" if r["signal_boost"] >= 1.5 else ("#888888" if r["signal_boost"] < 1.0 else "#C8CED8")

            tbl += f"<tr><td style='color:#E0E0E0;font-weight:600;'>{r['reporter_name']}</td><td>{r['corp_name']} ({r['stock_code']})</td><td>{market_badge(r.get('market',''))}</td><td>{r['position']}</td><td>{p_badge}</td><td style='text-align:center;'>{r['trade_count']}</td><td style='text-align:right;'>{r['avg_interval']:.0f}</td><td style='text-align:right;color:#00D4AA;'>{r['avg_ratio']:.3f}%</td><td style='text-align:center;color:{boost_color};font-weight:700;'>x{r['signal_boost']}</td><td style='color:#5A6577;'>{r['first_trade']} ~ {r['last_trade']}</td></tr>"
        tbl += "</table>"
        st.markdown(tbl, unsafe_allow_html=True)
    else:
        st.info("분석할 매수 데이터가 없습니다.")


# ═════════════════════════════════════════════════════════════
# TAB 4: SKIN IN THE GAME
# ═════════════════════════════════════════════════════════════
with tab_skin:
    st.markdown("<div class='section-title'>Skin in the Game Analysis</div>", unsafe_allow_html=True)
    st.markdown("""
    <div style='color:#8892A4; font-size:0.9rem; margin-bottom:20px; line-height:1.6;'>
    매수 금액 자체보다 <b style='color:#E0E0E0;'>기존 보유량 대비 얼마나 추가 매수했는지</b>가 핵심입니다.
    지분 증가율이 높을수록 내부자가 자신의 '돈'을 걸고 베팅한 것이므로 신호 가치가 큽니다.
    Net Buying은 같은 종목 내 매수-매도를 합산하여 조직 전체의 방향을 보여줍니다.
    </div>
    """, unsafe_allow_html=True)

    skin_df = calculate_skin_in_game(filtered_df)
    net_df = calculate_net_buying(full_df)

    sk1, sk2 = st.columns(2)

    with sk1:
        st.markdown("<div class='section-title'>지분 증가율 TOP</div>", unsafe_allow_html=True)
        if not skin_df.empty:
            for _, r in skin_df.head(15).iterrows():
                sc = r["skin_score"]
                sc_cls = "score-high" if sc >= 60 else ("score-medium" if sc >= 35 else "score-low")

                st.markdown(f"""
                <div style='background:#1A1F2E;border:1px solid #2D3748;border-radius:8px;padding:12px 16px;margin-bottom:8px;'>
                    <div style='display:flex;justify-content:space-between;align-items:center;'>
                        <div>
                            <span style='color:#E0E0E0;font-weight:600;'>{r["corp_name"]}</span>
                            {market_badge(r.get("market",""))}
                            <span style='color:#5A6577;margin-left:6px;'>{r["reporter_name"]} ({r["position"]})</span>
                        </div>
                        <span class='score-badge {sc_cls}'>Skin {sc:.0f}</span>
                    </div>
                    <div style='display:flex;gap:20px;margin-top:8px;color:#8892A4;font-size:0.85rem;'>
                        <span>증가율: <b style='color:#00D4AA;'>{r["increase_rate"]:.1f}%</b></span>
                        <span>투입액: W{r["est_investment"]:,.0f}</span>
                        <span>매수후 지분: {r["ownership_after"]:.4f}%</span>
                        <span>{r["report_date"]}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("분석할 매수 데이터가 없습니다.")

    with sk2:
        st.markdown("<div class='section-title'>Net Buying (매수-매도 합산)</div>", unsafe_allow_html=True)
        if not net_df.empty:
            tbl = "<table class='data-table'><tr><th>종목</th><th>시장</th><th>매수(주)</th><th>매도(주)</th><th>Net</th><th>방향</th></tr>"
            for _, r in net_df.head(20).iterrows():
                if r["direction"] == "Net BUY":
                    dir_html = "<span class='net-buy'>Net BUY</span>"
                elif r["direction"] == "Net SELL":
                    dir_html = "<span class='net-sell'>Net SELL</span>"
                else:
                    dir_html = "<span class='net-neutral'>Neutral</span>"

                net_color = "#00D4AA" if r["net_shares"] > 0 else ("#FF6060" if r["net_shares"] < 0 else "#888")
                tbl += f"<tr><td style='color:#E0E0E0;font-weight:600;'>{r['corp_name']}</td><td>{market_badge(r.get('market',''))}</td><td style='text-align:right;'>{r['buy_shares']:,}</td><td style='text-align:right;'>{r['sell_shares']:,}</td><td style='text-align:right;color:{net_color};font-weight:700;'>{r['net_shares']:,}</td><td>{dir_html}</td></tr>"
            tbl += "</table>"
            st.markdown(tbl, unsafe_allow_html=True)
        else:
            st.info("Net Buying 데이터가 없습니다.")


# ═════════════════════════════════════════════════════════════
# TAB 5: EVENT STUDY
# ═════════════════════════════════════════════════════════════
with tab_event:
    st.markdown("<div class='section-title'>Event Study: Pre/Post Filing Analysis</div>", unsafe_allow_html=True)
    st.markdown("""
    <div style='color:#8892A4; font-size:0.9rem; margin-bottom:20px; line-height:1.6;'>
    내부자 매수 공시일 전후의 주가와 거래량 변화를 분석합니다.
    <b style='color:#E0E0E0;'>정보 선반영(Information Leakage)</b> 여부를 거래량 급증으로 감지하고,
    <b style='color:#E0E0E0;'>누적 초과수익률(CAR)</b>로 공시 후 주가 반응을 측정합니다.
    </div>
    """, unsafe_allow_html=True)

    ev1, ev2 = st.columns([1, 3])
    with ev1:
        event_window = st.slider("분석 기간 (공시 전후 일수)", 5, 20, 10)
        event_top_n = st.slider("분석할 상위 신호 수", 3, 20, 10)

    event_result = run_event_study(filtered_df, days_before=event_window, days_after=event_window, top_n=event_top_n)
    summary = event_result["summary"]
    events = event_result["events"]

    with ev2:
        if summary.get("total_events", 0) > 0:
            ek1, ek2, ek3, ek4 = st.columns(4)
            with ek1:
                car_color = "#00D4AA" if summary["avg_car"] > 0 else "#FF6060"
                st.markdown(f"<div class='kpi-card'><div class='kpi-label'>평균 CAR</div><div class='kpi-value' style='color:{car_color};'>{summary['avg_car']:+.2f}%</div><div class='kpi-sub'>누적 초과수익률</div></div>", unsafe_allow_html=True)
            with ek2:
                st.markdown(f"<div class='kpi-card'><div class='kpi-label'>Hit Rate</div><div class='kpi-value'>{summary['hit_rate']:.0f}%</div><div class='kpi-sub'>양(+) CAR 비율</div></div>", unsafe_allow_html=True)
            with ek3:
                st.markdown(f"<div class='kpi-card'><div class='kpi-label'>분석 이벤트</div><div class='kpi-value'>{summary['total_events']}</div><div class='kpi-sub'>건</div></div>", unsafe_allow_html=True)
            with ek4:
                st.markdown(f"<div class='kpi-card'><div class='kpi-label'>정보 선반영 의심</div><div class='kpi-value' style='color:#FF4444;'>{summary['leakage_count']}</div><div class='kpi-sub'>거래량 급증 감지</div></div>", unsafe_allow_html=True)

    if events:
        st.markdown("<br>", unsafe_allow_html=True)

        for ev in events:
            price_data = ev["price_data"]
            car_val = ev["car_post"]
            car_color = "#00D4AA" if car_val > 0 else "#FF6060"

            if ev["info_leakage"] == "의심":
                leak_html = "<span class='leak-suspect'>의심 (거래량 {:.1f}x 급증)</span>".format(ev["volume_surge"])
            elif ev["info_leakage"] == "경미":
                leak_html = "<span class='leak-minor'>경미 ({:.1f}x)</span>".format(ev["volume_surge"])
            else:
                leak_html = "<span class='leak-none'>없음</span>"

            st.markdown(f"""
            <div style='background:#1A1F2E;border:1px solid #2D3748;border-radius:8px;padding:14px 18px;margin-bottom:6px;'>
                <div style='display:flex;justify-content:space-between;align-items:center;'>
                    <div>
                        <span style='color:#E0E0E0;font-weight:700;font-size:1.05rem;'>{ev["corp_name"]}</span>
                        {market_badge(ev.get("market",""))}
                        <span style='color:#5A6577;margin-left:8px;'>{ev["reporter_name"]} ({ev["position"]})</span>
                        <span style='color:#5A6577;margin-left:8px;'>| {ev["filing_date"]}</span>
                    </div>
                    <div>
                        <span style='color:{car_color};font-weight:700;font-size:1.1rem;'>CAR {car_val:+.2f}%</span>
                        <span style='margin-left:12px;'>정보선반영: {leak_html}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 차트: 주가 + 거래량
            if not price_data.empty:
                fig = go.Figure()

                # 주가 라인
                colors = ["#FF6060" if x < 0 else "#00D4AA" for x in price_data["day_offset"]]
                fig.add_trace(go.Scatter(
                    x=price_data["day_offset"], y=price_data["close"],
                    mode="lines+markers", name="종가",
                    line=dict(color="#00D4AA", width=2),
                    marker=dict(size=5),
                ))

                # 공시일 표시선
                fig.add_vline(x=0, line_dash="dash", line_color="#FFB020", line_width=1,
                              annotation_text="공시일", annotation_position="top")

                # 거래량 바
                fig.add_trace(go.Bar(
                    x=price_data["day_offset"], y=price_data["volume"],
                    name="거래량", yaxis="y2",
                    marker_color=["rgba(255,176,32,0.6)" if abs(x) <= 3 else "rgba(100,100,100,0.3)"
                                  for x in price_data["day_offset"]],
                ))

                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#E0E0E0",
                    xaxis=dict(title="공시일 대비 (일)", gridcolor="#2D3748", zeroline=True),
                    yaxis=dict(title="종가 (W)", gridcolor="#2D3748", side="left"),
                    yaxis2=dict(title="거래량", overlaying="y", side="right", showgrid=False),
                    margin=dict(l=10, r=10, t=30, b=10), height=280,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    showlegend=True,
                )
                st.plotly_chart(fig, use_container_width=True)
    elif summary.get("total_events", 0) == 0:
        st.info("분석할 매수 신호가 없습니다. 필터 조건을 완화해 보세요.")


# ─────────────────────────────────────────────────────────────
# 푸터
# ─────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#5A6577;font-size:0.8rem;padding:16px;'>"
    "K-Insider Quant Monitor v2.0 | "
    "데이터: DART + pykrx | "
    "본 프로그램은 투자 조언이 아니며, 투자 판단의 책임은 본인에게 있습니다."
    "</div>", unsafe_allow_html=True,
)
