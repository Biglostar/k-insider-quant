"""
K-Insider Quant Monitor - 메인 대시보드
한국 DART 내부자 거래 분석 & 시각화
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from config import DEMO_MODE, DEFAULT_MIN_RATIO, POSITION_WEIGHTS
from database import (
    init_db, upsert_trades, query_trades,
    query_sector_summary, query_daily_counts, get_all_dates,
)
from collector import collect_data
from filter_engine import apply_quant_filter, add_signal_scores, get_top_signals


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
    .stApp {
        background-color: #0E1117;
    }

    /* KPI 카드 */
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
        font-size: 2.4rem;
        font-weight: 700;
        color: #00D4AA;
        margin: 8px 0 4px 0;
        line-height: 1.1;
    }
    .kpi-label {
        font-size: 0.85rem;
        color: #8892A4;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .kpi-sub {
        font-size: 0.78rem;
        color: #5A6577;
        margin-top: 4px;
    }

    /* 시장 뱃지 */
    .badge-kospi {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        background: #007BFF22;
        color: #4DA3FF;
        border: 1px solid #007BFF44;
    }
    .badge-kosdaq {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        background: #FF6B3522;
        color: #FF8F60;
        border: 1px solid #FF6B3544;
    }

    /* 신호 점수 뱃지 */
    .score-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .score-high   { background: #00D4AA22; color: #00D4AA; border: 1px solid #00D4AA44; }
    .score-medium { background: #FFB02022; color: #FFB020; border: 1px solid #FFB02044; }
    .score-low    { background: #FF606022; color: #FF6060; border: 1px solid #FF606044; }

    /* 신호 강도 표시 */
    .signal-strong { color: #00D4AA; font-weight: 700; }
    .signal-mid    { color: #FFB020; font-weight: 700; }
    .signal-weak   { color: #FF6060; font-weight: 700; }

    /* 데모 배너 */
    .demo-banner {
        background: linear-gradient(90deg, #FF6B3520, #FF6B3510);
        border: 1px solid #FF6B3540;
        border-radius: 8px;
        padding: 10px 16px;
        margin-bottom: 16px;
        text-align: center;
        color: #FF6B35;
        font-size: 0.9rem;
    }

    /* 사이드바 */
    section[data-testid="stSidebar"] {
        background-color: #141820;
        border-right: 1px solid #2D3748;
    }

    /* 헤더 라인 */
    .header-line {
        height: 3px;
        background: linear-gradient(90deg, #00D4AA, #007BFF, #00D4AA);
        border-radius: 2px;
        margin: 8px 0 24px 0;
    }

    /* 섹션 타이틀 */
    .section-title {
        color: #E0E0E0;
        font-size: 1.15rem;
        font-weight: 600;
        margin: 32px 0 12px 0;
        padding-left: 12px;
        border-left: 3px solid #00D4AA;
    }

    /* 테이블 스타일 */
    .data-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.88rem;
    }
    .data-table th {
        background: #1A1F2E;
        color: #8892A4;
        padding: 10px 12px;
        text-align: left;
        border-bottom: 2px solid #2D3748;
        font-weight: 600;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .data-table td {
        padding: 10px 12px;
        border-bottom: 1px solid #1E2436;
        color: #C8CED8;
    }
    .data-table tr:hover td {
        background: #1A1F2E;
    }

    /* 링크 */
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
# 사이드바
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## K-Insider Quant")
    st.markdown("---")

    available_dates = get_all_dates()
    if available_dates:
        date_mode = st.radio(
            "조회 기간",
            ["오늘", "최근 7일", "최근 30일", "직접 선택"],
            horizontal=True,
        )

        if date_mode == "오늘":
            start_date = available_dates[0]
            end_date = available_dates[0]
        elif date_mode == "최근 7일":
            end_date = available_dates[0]
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        elif date_mode == "최근 30일":
            end_date = available_dates[0]
            start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
        else:
            col1, col2 = st.columns(2)
            with col1:
                start_dt = st.date_input(
                    "시작일",
                    value=datetime.strptime(available_dates[-1], "%Y-%m-%d"),
                )
                start_date = start_dt.strftime("%Y-%m-%d")
            with col2:
                end_dt = st.date_input(
                    "종료일",
                    value=datetime.strptime(available_dates[0], "%Y-%m-%d"),
                )
                end_date = end_dt.strftime("%Y-%m-%d")
    else:
        start_date = end_date = datetime.now().strftime("%Y-%m-%d")

    st.markdown("---")

    min_ratio = st.slider(
        "최소 매수 비중 (%)",
        min_value=0.01,
        max_value=1.0,
        value=DEFAULT_MIN_RATIO,
        step=0.01,
        format="%.2f%%",
        help="발행주식 총수 대비 매수 수량의 비율",
    )

    st.markdown("---")

    all_positions = list(POSITION_WEIGHTS.keys())
    selected_positions = st.multiselect(
        "직위 필터",
        options=all_positions,
        default=None,
        placeholder="전체 (필터 없음)",
        help="특정 직위만 보려면 선택하세요",
    )

    st.markdown("---")

    # 시장 필터
    market_filter = st.multiselect(
        "시장 필터",
        options=["KOSPI", "KOSDAQ"],
        default=None,
        placeholder="전체 (필터 없음)",
        help="KOSPI 또는 KOSDAQ만 보려면 선택",
    )

    st.markdown("---")

    show_noise = st.checkbox("노이즈 포함 (증여/상속 등)", value=False)

    st.markdown("---")
    st.markdown(
        "<div style='text-align:center; color:#5A6577; font-size:0.75rem;'>"
        "Built with Streamlit + OpenDART + pykrx<br>"
        "K-Insider Quant Monitor v1.1"
        "</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# 메인 대시보드
# ─────────────────────────────────────────────────────────────

st.markdown(
    "<h1 style='margin-bottom:0; color:#E0E0E0;'>K-Insider Quant Monitor</h1>",
    unsafe_allow_html=True,
)
st.markdown("<div class='header-line'></div>", unsafe_allow_html=True)

if DEMO_MODE:
    st.markdown(
        "<div class='demo-banner'>"
        "<b>DEMO MODE</b> — 실제 데이터가 아닌 시뮬레이션 데이터입니다. "
        "환경 변수 <code>DART_API_KEY</code>를 설정하면 실제 DART 공시 데이터로 전환됩니다."
        "</div>",
        unsafe_allow_html=True,
    )


# ── 데이터 조회 ──────────────────────────────────────────────
signal_types = ["BUY"]
if show_noise:
    signal_types = ["BUY", "NOISE", "NORMAL"]

raw_df = query_trades(
    start_date=start_date,
    end_date=end_date,
    signal_only=not show_noise,
    min_ratio=min_ratio,
    positions=selected_positions if selected_positions else None,
)

filtered_df = apply_quant_filter(
    raw_df,
    min_ratio=min_ratio,
    positions=selected_positions if selected_positions else None,
    signal_types=signal_types,
)

# 시장 필터 적용
if market_filter and not filtered_df.empty:
    filtered_df = filtered_df[filtered_df["market"].isin(market_filter)]

scored_df = add_signal_scores(filtered_df)


# ── KPI 카드 ─────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-label'>포착된 매수 신호</div>
            <div class='kpi-value'>{len(scored_df)}</div>
            <div class='kpi-sub'>필터 조건 충족 건수</div>
        </div>
    """, unsafe_allow_html=True)

with col2:
    unique_stocks = scored_df["stock_code"].nunique() if not scored_df.empty else 0
    st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-label'>고유 종목 수</div>
            <div class='kpi-value'>{unique_stocks}</div>
            <div class='kpi-sub'>중복 제거 기준</div>
        </div>
    """, unsafe_allow_html=True)

with col3:
    if not scored_df.empty:
        top_row = scored_df.iloc[0]
        top_name = top_row["corp_name"]
        top_ratio = top_row["buy_ratio"]
    else:
        top_name = "-"
        top_ratio = 0
    st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-label'>최대 매수 종목</div>
            <div class='kpi-value' style='font-size:1.4rem;'>{top_name}</div>
            <div class='kpi-sub'>매수 비중 {top_ratio:.2f}%</div>
        </div>
    """, unsafe_allow_html=True)

with col4:
    avg_score = scored_df["signal_score"].mean() if not scored_df.empty else 0
    st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-label'>평균 신호 점수</div>
            <div class='kpi-value'>{avg_score:.1f}</div>
            <div class='kpi-sub'>0~100 스케일</div>
        </div>
    """, unsafe_allow_html=True)


st.markdown("<br>", unsafe_allow_html=True)


# ── 메인 테이블 ──────────────────────────────────────────────
st.markdown("<div class='section-title'>필터링된 내부자 매수 리스트</div>", unsafe_allow_html=True)

if not scored_df.empty:
    # 테이블 HTML 직접 구성 (시장 뱃지 포함)
    table_html = "<table class='data-table'>"
    table_html += """<tr>
        <th>보고일</th><th>종목명</th><th>시장</th><th>섹터</th>
        <th>보고자</th><th>직위</th><th>변동사유</th>
        <th>변동수량</th><th>매수비중</th><th>신호점수</th>
        <th>현재가</th><th>원문</th>
    </tr>"""

    for _, row in scored_df.iterrows():
        market_val = row.get("market", "")
        if market_val == "KOSPI":
            market_badge = "<span class='badge-kospi'>KOSPI</span>"
        elif market_val == "KOSDAQ":
            market_badge = "<span class='badge-kosdaq'>KOSDAQ</span>"
        else:
            market_badge = "<span style='color:#5A6577;'>-</span>"

        score = row.get("signal_score", 0)
        if score >= 70:
            score_class = "score-high"
        elif score >= 45:
            score_class = "score-medium"
        else:
            score_class = "score-low"

        table_html += f"""<tr>
            <td>{row['report_date']}</td>
            <td style='color:#E0E0E0; font-weight:600;'>{row['corp_name']}
                <span style='color:#5A6577; font-size:0.78rem;'>({row['stock_code']})</span></td>
            <td>{market_badge}</td>
            <td style='color:#8892A4;'>{row.get('sector', '기타')}</td>
            <td>{row['reporter_name']}</td>
            <td>{row['position']}</td>
            <td>{row['change_reason']}</td>
            <td style='text-align:right;'>{int(row['shares_changed']):,}</td>
            <td style='text-align:right; color:#00D4AA; font-weight:600;'>{row['buy_ratio']:.3f}%</td>
            <td><span class='score-badge {score_class}'>{score}</span></td>
            <td style='text-align:right;'>W{int(row['current_price']):,}</td>
            <td><a href='{row['dart_url']}' target='_blank'>보기</a></td>
        </tr>"""

    table_html += "</table>"
    st.markdown(table_html, unsafe_allow_html=True)

    # CSV 다운로드
    csv_data = scored_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        label="CSV 다운로드",
        data=csv_data,
        file_name=f"k_insider_{start_date}_{end_date}.csv",
        mime="text/csv",
    )
else:
    st.info("선택한 조건에 맞는 매수 신호가 없습니다. 필터 조건을 완화해 보세요.")


st.markdown("<br>", unsafe_allow_html=True)


# ── 차트 영역 ────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("<div class='section-title'>섹터별 매수 현황 (최근 30일)</div>", unsafe_allow_html=True)

    sector_df = query_sector_summary(days=30)
    if not sector_df.empty:
        fig_sector = px.bar(
            sector_df,
            x="sector",
            y="buy_count",
            color="avg_ratio",
            color_continuous_scale=["#1A1F2E", "#00D4AA"],
            labels={"buy_count": "매수 건수", "sector": "섹터", "avg_ratio": "평균 비중(%)"},
            text="buy_count",
        )
        fig_sector.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#E0E0E0",
            xaxis=dict(gridcolor="#2D3748"),
            yaxis=dict(gridcolor="#2D3748"),
            margin=dict(l=20, r=20, t=30, b=20),
            height=380,
            coloraxis_colorbar=dict(title="평균 비중(%)"),
        )
        fig_sector.update_traces(textposition="outside")
        st.plotly_chart(fig_sector, use_container_width=True)
    else:
        st.info("섹터 데이터가 없습니다.")

with chart_col2:
    st.markdown("<div class='section-title'>일별 매수 신호 추이 (최근 30일)</div>", unsafe_allow_html=True)

    daily_df = query_daily_counts(days=30)
    if not daily_df.empty:
        fig_daily = go.Figure()
        fig_daily.add_trace(go.Scatter(
            x=daily_df["report_date"],
            y=daily_df["signal_count"],
            mode="lines+markers",
            name="전체 매수 신호",
            line=dict(color="#00D4AA", width=2),
            marker=dict(size=6),
            fill="tozeroy",
            fillcolor="rgba(0, 212, 170, 0.1)",
        ))
        fig_daily.add_trace(go.Scatter(
            x=daily_df["report_date"],
            y=daily_df["top_exec_count"],
            mode="lines+markers",
            name="C-Level 매수",
            line=dict(color="#FFB020", width=2, dash="dot"),
            marker=dict(size=6, symbol="diamond"),
        ))
        fig_daily.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#E0E0E0",
            xaxis=dict(gridcolor="#2D3748"),
            yaxis=dict(gridcolor="#2D3748", title="건수"),
            margin=dict(l=20, r=20, t=30, b=20),
            height=380,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1
            ),
        )
        st.plotly_chart(fig_daily, use_container_width=True)
    else:
        st.info("일별 데이터가 없습니다.")


st.markdown("<br>", unsafe_allow_html=True)


# ── TOP 시그널 상세 ──────────────────────────────────────────
st.markdown("<div class='section-title'>TOP 10 매수 시그널</div>", unsafe_allow_html=True)

top_signals = get_top_signals(scored_df, top_n=10)

if not top_signals.empty:
    for idx, row in top_signals.iterrows():
        score = row["signal_score"]
        if score >= 70:
            badge_class = "score-high"
            signal_class = "signal-strong"
        elif score >= 45:
            badge_class = "score-medium"
            signal_class = "signal-mid"
        else:
            badge_class = "score-low"
            signal_class = "signal-weak"

        buy_amount = row["shares_changed"] * row["current_price"]

        market_val = row.get("market", "")
        if market_val == "KOSPI":
            market_badge = "<span class='badge-kospi'>KOSPI</span>"
        elif market_val == "KOSDAQ":
            market_badge = "<span class='badge-kosdaq'>KOSDAQ</span>"
        else:
            market_badge = ""

        st.markdown(f"""
        <div style='
            background: linear-gradient(135deg, #1A1F2E, #1E2436);
            border: 1px solid #2D3748;
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 10px;
        '>
            <div style='display:flex; justify-content:space-between; align-items:center;'>
                <div>
                    <span class='{signal_class}' style='font-size:1.2rem;'>
                        {row["corp_name"]}
                    </span>
                    <span style='color:#5A6577; margin-left:8px;'>({row["stock_code"]})</span>
                    {market_badge}
                    <span style='color:#8892A4; margin-left:12px;'>| {row.get("sector", "기타")}</span>
                </div>
                <div>
                    <span class='score-badge {badge_class}'>Score {score}</span>
                </div>
            </div>
            <div style='display:flex; gap:32px; margin-top:10px; color:#8892A4; font-size:0.88rem;'>
                <span>{row["reporter_name"]} ({row["position"]})</span>
                <span>{row["change_reason"]}</span>
                <span>비중 {row["buy_ratio"]:.3f}%</span>
                <span>추정 매수액 W{buy_amount:,.0f}</span>
                <span>{row["report_date"]}</span>
            </div>
            <div style='margin-top:6px;'>
                <a href='{row["dart_url"]}' target='_blank'
                   style='font-size:0.8rem; color:#00D4AA;'>
                   DART 원문 보기 &rarr;
                </a>
            </div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("TOP 시그널이 없습니다.")


# ── 직위 가중치 설명 ─────────────────────────────────────────
with st.expander("직위 가중치 기준표"):
    st.markdown("""
    직위 가중치는 **내부자의 정보 접근 권한**에 따라 매수 신호의 의미를 차등 평가하는 수치입니다.
    회사 내부 사정을 가장 잘 아는 인물의 매수일수록 높은 점수를 부여합니다.

    | 직위 | 가중치 | 설명 |
    |------|--------|------|
    | 대표이사 / 최대주주 | 10 | 경영 전반의 정보를 보유, 가장 강력한 신호 |
    | 부회장 | 9 | 대표이사에 준하는 의사결정권 |
    | 사내이사 / CFO / 재무이사 | 8 | 재무 상태와 실적을 직접 파악 |
    | 전략이사 / 주요주주 | 7 | 사업 방향성과 성장 전략에 관여 |
    | 임원 / 등기임원 | 6 | 이사회 참석 등으로 주요 정보 접근 가능 |
    | 사외이사 / 감사 | 5 | 제한적이나 이사회 안건 확인 가능 |
    | 미등기임원 | 4 | 실무 레벨 정보 보유 |
    | 특수관계인 | 3 | 간접적 정보, 가장 낮은 신호 강도 |

    이 가중치는 **신호 점수**(0~100)의 40%를 차지하며,
    나머지는 매수 비중(40%)과 변동사유 유형(20%)으로 구성됩니다.
    """)


# ── 푸터 ─────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#5A6577; font-size:0.8rem; padding:16px;'>"
    "K-Insider Quant Monitor v1.1 | "
    "데이터 출처: DART 전자공시시스템 | "
    "주가 데이터: pykrx (KRX) | "
    "본 프로그램은 투자 조언이 아니며, 투자 판단의 책임은 본인에게 있습니다."
    "</div>",
    unsafe_allow_html=True,
)
