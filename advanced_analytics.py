"""
K-Insider Quant Monitor - 고급 분석 엔진
헤지펀드 스타일 내부자 거래 분석 기법 4종

1. Cluster & Breadth (클러스터 매수 감지)
2. Routine vs Opportunistic (매수 패턴 분류)
3. Skin in the Game (지분 증가율)
4. Event Study (공시 전후 주가/거래량 분석)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

from config import POSITION_WEIGHTS, DEMO_MODE


# ═════════════════════════════════════════════════════════════
# 1. CLUSTER & BREADTH (클러스터 매수 감지)
# ═════════════════════════════════════════════════════════════

def detect_clusters(
    df: pd.DataFrame,
    window_days: int = 14,
    min_buyers: int = 2,
) -> pd.DataFrame:
    """
    동일 종목에 대해 일정 기간 내 다수 임원이 매수한 '클러스터'를 감지합니다.

    Parameters:
        df:           BUY 신호가 포함된 DataFrame
        window_days:  클러스터 판별 기간 (기본 14일)
        min_buyers:   최소 매수자 수 (기본 2명)

    Returns:
        클러스터 종목별 요약 DataFrame
    """
    if df.empty:
        return pd.DataFrame()

    buy_df = df[df["signal_type"] == "BUY"].copy()
    if buy_df.empty:
        return pd.DataFrame()

    buy_df["report_date"] = pd.to_datetime(buy_df["report_date"])
    clusters = []

    for stock_code, group in buy_df.groupby("stock_code"):
        group = group.sort_values("report_date")

        # 슬라이딩 윈도우로 클러스터 탐색
        for i, row in group.iterrows():
            window_start = row["report_date"]
            window_end = window_start + timedelta(days=window_days)
            window_data = group[
                (group["report_date"] >= window_start) &
                (group["report_date"] <= window_end)
            ]

            unique_buyers = window_data["reporter_name"].nunique()
            unique_positions = window_data["position"].nunique()

            if unique_buyers >= min_buyers:
                # Breadth 점수: 다양한 직급 참여도
                positions = window_data["position"].unique().tolist()
                max_weight = window_data["position_weight"].max()
                avg_weight = window_data["position_weight"].mean()
                total_shares = window_data["shares_changed"].sum()
                avg_ratio = window_data["buy_ratio"].mean()

                # 클러스터 강도 계산 (0~100)
                breadth_score = min(unique_positions * 15, 40)  # 다양성 (최대 40)
                weight_score = min(avg_weight * 4, 30)          # 직위 수준 (최대 30)
                size_score = min(avg_ratio * 100, 30)           # 매수 규모 (최대 30)
                cluster_strength = round(breadth_score + weight_score + size_score, 1)

                clusters.append({
                    "stock_code":       stock_code,
                    "corp_name":        row["corp_name"],
                    "market":           row.get("market", ""),
                    "sector":           row.get("sector", "기타"),
                    "window_start":     window_start.strftime("%Y-%m-%d"),
                    "window_end":       window_end.strftime("%Y-%m-%d"),
                    "buyer_count":      unique_buyers,
                    "position_count":   unique_positions,
                    "positions":        ", ".join(positions),
                    "total_shares":     total_shares,
                    "avg_ratio":        round(avg_ratio, 4),
                    "max_weight":       max_weight,
                    "cluster_strength": min(cluster_strength, 100),
                    "buyers":           ", ".join(window_data["reporter_name"].unique()),
                })

    if not clusters:
        return pd.DataFrame()

    result = pd.DataFrame(clusters)
    # 중복 클러스터 제거 (같은 종목 + 겹치는 기간)
    result = result.drop_duplicates(
        subset=["stock_code", "buyer_count", "positions"],
        keep="first"
    )
    return result.sort_values("cluster_strength", ascending=False).reset_index(drop=True)


# ═════════════════════════════════════════════════════════════
# 2. ROUTINE vs OPPORTUNISTIC (매수 패턴 분류)
# ═════════════════════════════════════════════════════════════

def classify_trader_pattern(df: pd.DataFrame) -> pd.DataFrame:
    """
    각 내부자의 과거 매수 패턴을 분석하여
    Routine(정기적) vs Opportunistic(기회주의적)으로 분류합니다.

    판별 기준:
    - 매수 간격의 표준편차가 낮으면 → Routine
    - 매수 빈도가 낮고 간격이 불규칙하면 → Opportunistic
    - 매수 1건이면 → 판별 불가 (Single)

    Returns:
        거래자별 패턴 분류 DataFrame
    """
    if df.empty:
        return pd.DataFrame()

    buy_df = df[df["signal_type"] == "BUY"].copy()
    if buy_df.empty:
        return pd.DataFrame()

    buy_df["report_date"] = pd.to_datetime(buy_df["report_date"])
    results = []

    # 보고자 + 종목 조합별 분석
    for (reporter, stock_code), group in buy_df.groupby(["reporter_name", "stock_code"]):
        group = group.sort_values("report_date")
        trade_count = len(group)
        corp_name = group.iloc[0]["corp_name"]
        position = group.iloc[0]["position"]
        total_bought = group["shares_changed"].sum()
        avg_ratio = group["buy_ratio"].mean()

        if trade_count == 1:
            pattern = "Single"
            regularity = 0
            avg_interval = 0
            std_interval = 0
            signal_boost = 1.0  # 판별 불가, 기본 배수
        else:
            # 매수 간격 계산
            dates = group["report_date"].sort_values().tolist()
            intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
            avg_interval = np.mean(intervals)
            std_interval = np.std(intervals)

            # 변동계수(CV)로 규칙성 판단
            if avg_interval > 0:
                cv = std_interval / avg_interval
            else:
                cv = 0

            # CV < 0.3 → 매우 규칙적 (Routine)
            # CV < 0.6 → 다소 규칙적 (Routine)
            # CV >= 0.6 → 불규칙 (Opportunistic)
            if cv < 0.3:
                pattern = "Routine"
                regularity = round((1 - cv) * 100, 1)
                signal_boost = 0.5  # 신호 가치 감소
            elif cv < 0.6:
                pattern = "Semi-Routine"
                regularity = round((1 - cv) * 100, 1)
                signal_boost = 0.8
            else:
                pattern = "Opportunistic"
                regularity = round((1 - min(cv, 1.0)) * 100, 1)
                signal_boost = 1.5  # 신호 가치 증가

        results.append({
            "reporter_name":  reporter,
            "stock_code":     stock_code,
            "corp_name":      corp_name,
            "position":       position,
            "market":         group.iloc[0].get("market", ""),
            "trade_count":    trade_count,
            "total_bought":   total_bought,
            "avg_ratio":      round(avg_ratio, 4),
            "avg_interval":   round(avg_interval, 1),
            "std_interval":   round(std_interval, 1),
            "pattern":        pattern,
            "regularity":     regularity,
            "signal_boost":   signal_boost,
            "first_trade":    group["report_date"].min().strftime("%Y-%m-%d"),
            "last_trade":     group["report_date"].max().strftime("%Y-%m-%d"),
        })

    result = pd.DataFrame(results)
    # Opportunistic을 우선 정렬
    pattern_order = {"Opportunistic": 0, "Single": 1, "Semi-Routine": 2, "Routine": 3}
    result["_sort"] = result["pattern"].map(pattern_order)
    result = result.sort_values(["_sort", "avg_ratio"], ascending=[True, False])
    return result.drop(columns="_sort").reset_index(drop=True)


# ═════════════════════════════════════════════════════════════
# 3. SKIN IN THE GAME (지분 증가율)
# ═════════════════════════════════════════════════════════════

def calculate_skin_in_game(df: pd.DataFrame) -> pd.DataFrame:
    """
    각 매수 건의 '지분 증가율'을 계산하여
    내부자가 얼마나 의미 있는 베팅을 했는지 평가합니다.

    핵심 지표:
    - 지분 증가율: (매수 수량 / 매수 전 보유량) * 100
    - 추정 투입액: 매수 수량 * 현재가
    - Net Buying: 같은 종목 내 매수-매도 합산

    Returns:
        Skin in the Game 분석 DataFrame
    """
    if df.empty:
        return pd.DataFrame()

    buy_df = df[df["signal_type"] == "BUY"].copy()
    if buy_df.empty:
        return pd.DataFrame()

    results = []

    for _, row in buy_df.iterrows():
        shares_changed = row["shares_changed"]
        shares_after = row["shares_after"]
        current_price = row["current_price"]

        # 매수 전 보유량 역산
        shares_before = max(shares_after - shares_changed, 0)

        # 지분 증가율
        if shares_before > 0:
            increase_rate = round((shares_changed / shares_before) * 100, 2)
        elif shares_after > 0:
            increase_rate = 100.0  # 신규 매수 (0 → N)
        else:
            increase_rate = 0

        # 추정 투입액
        est_investment = shares_changed * current_price

        # 총 발행주식 대비 보유 비중 (매수 후)
        total_shares = row["total_shares"]
        if total_shares > 0:
            ownership_after = round((shares_after / total_shares) * 100, 4)
        else:
            ownership_after = 0

        # Skin 점수 (0~100)
        # 지분 증가율이 높을수록, 투입액이 클수록 높은 점수
        rate_score = min(increase_rate * 2, 50)         # 증가율 (최대 50)
        invest_score = min(est_investment / 1e9 * 10, 30)  # 10억당 10점 (최대 30)
        weight_score = min(row["position_weight"] * 2, 20) # 직위 (최대 20)
        skin_score = round(min(rate_score + invest_score + weight_score, 100), 1)

        results.append({
            "report_date":     row["report_date"],
            "corp_name":       row["corp_name"],
            "stock_code":      row["stock_code"],
            "market":          row.get("market", ""),
            "sector":          row.get("sector", "기타"),
            "reporter_name":   row["reporter_name"],
            "position":        row["position"],
            "shares_before":   shares_before,
            "shares_changed":  shares_changed,
            "shares_after":    shares_after,
            "increase_rate":   increase_rate,
            "est_investment":  est_investment,
            "ownership_after": ownership_after,
            "current_price":   current_price,
            "skin_score":      skin_score,
        })

    result = pd.DataFrame(results)
    return result.sort_values("skin_score", ascending=False).reset_index(drop=True)


def calculate_net_buying(df: pd.DataFrame) -> pd.DataFrame:
    """
    종목별 Net Buying (매수 - 매도 합산)을 계산합니다.
    조직 전체가 매수 방향인지 매도 방향인지 판별합니다.
    """
    if df.empty:
        return pd.DataFrame()

    results = []
    for stock_code, group in df.groupby("stock_code"):
        buys = group[group["signal_type"] == "BUY"]
        sells = group[group["signal_type"].isin(["NORMAL"])]

        buy_total = buys["shares_changed"].sum() if not buys.empty else 0
        sell_total = sells["shares_changed"].sum() if not sells.empty else 0
        net = buy_total - sell_total

        buy_count = len(buys)
        sell_count = len(sells)

        corp_name = group.iloc[0]["corp_name"]
        market = group.iloc[0].get("market", "")

        if net > 0:
            direction = "Net BUY"
        elif net < 0:
            direction = "Net SELL"
        else:
            direction = "Neutral"

        results.append({
            "stock_code":  stock_code,
            "corp_name":   corp_name,
            "market":      market,
            "buy_shares":  buy_total,
            "sell_shares": sell_total,
            "net_shares":  net,
            "buy_count":   buy_count,
            "sell_count":  sell_count,
            "direction":   direction,
        })

    result = pd.DataFrame(results)
    return result.sort_values("net_shares", ascending=False).reset_index(drop=True)


# ═════════════════════════════════════════════════════════════
# 4. EVENT STUDY (공시 전후 주가/거래량 분석)
# ═════════════════════════════════════════════════════════════

def generate_demo_event_data(
    stock_code: str,
    filing_date: str,
    signal_type: str = "BUY",
    days_before: int = 10,
    days_after: int = 10,
) -> pd.DataFrame:
    """
    데모 모드용: 공시 전후 주가/거래량 시뮬레이션 데이터 생성

    BUY 신호의 경우:
    - 공시 전: 미세한 상승 + 거래량 증가 (정보 선반영 시뮬레이션)
    - 공시 후: 주가 상승 → 일부 되돌림 (Post-Filing Drift)
    """
    np.random.seed(hash(stock_code + filing_date) % 2**31)

    filing_dt = datetime.strptime(filing_date, "%Y-%m-%d")
    base_price = np.random.randint(30000, 300000)
    base_volume = np.random.randint(100000, 2000000)

    rows = []
    price = base_price

    for day_offset in range(-days_before, days_after + 1):
        dt = filing_dt + timedelta(days=day_offset)
        # 주말 건너뛰기
        if dt.weekday() >= 5:
            continue

        if signal_type == "BUY":
            if day_offset < -3:
                # 공시 전 안정기
                daily_return = np.random.normal(0.001, 0.015)
                vol_mult = np.random.uniform(0.8, 1.2)
            elif day_offset < 0:
                # 공시 직전: 정보 선반영 (미세 상승 + 거래량 증가)
                daily_return = np.random.normal(0.008, 0.012)
                vol_mult = np.random.uniform(1.3, 2.0)
            elif day_offset == 0:
                # 공시일: 주가 상승
                daily_return = np.random.normal(0.025, 0.015)
                vol_mult = np.random.uniform(2.0, 3.5)
            elif day_offset <= 3:
                # 공시 직후: 추가 상승 또는 되돌림
                daily_return = np.random.normal(0.005, 0.02)
                vol_mult = np.random.uniform(1.5, 2.5)
            else:
                # 공시 후 안정기: Post-Filing Drift
                daily_return = np.random.normal(0.002, 0.018)
                vol_mult = np.random.uniform(0.9, 1.3)
        else:
            daily_return = np.random.normal(0.0, 0.015)
            vol_mult = np.random.uniform(0.8, 1.2)

        price = price * (1 + daily_return)
        volume = int(base_volume * vol_mult)

        rows.append({
            "date":        dt.strftime("%Y-%m-%d"),
            "day_offset":  day_offset,
            "close":       round(price),
            "volume":      volume,
            "return_pct":  round(daily_return * 100, 2),
        })

    return pd.DataFrame(rows)


def run_event_study(
    df: pd.DataFrame,
    days_before: int = 10,
    days_after: int = 10,
    top_n: int = 10,
) -> dict:
    """
    주요 매수 신호에 대한 이벤트 스터디를 수행합니다.

    Returns:
        {
            "events": 이벤트별 상세 데이터 리스트,
            "avg_car": 평균 누적 초과수익률,
            "summary": 종합 통계
        }
    """
    if df.empty:
        return {"events": [], "avg_car": 0, "summary": {}}

    buy_df = df[df["signal_type"] == "BUY"].copy()
    if buy_df.empty:
        return {"events": [], "avg_car": 0, "summary": {}}

    # 상위 N개 신호만 분석
    buy_df = buy_df.sort_values("buy_ratio", ascending=False).head(top_n)

    events = []
    all_cars = []

    for _, row in buy_df.iterrows():
        if DEMO_MODE:
            price_data = generate_demo_event_data(
                row["stock_code"],
                row["report_date"],
                "BUY",
                days_before,
                days_after,
            )
        else:
            # 실제 모드: pykrx에서 주가 데이터 조회
            price_data = _fetch_real_event_data(
                row["stock_code"],
                row["report_date"],
                days_before,
                days_after,
            )

        if price_data.empty:
            continue

        # 누적 초과수익률(CAR) 계산
        # 기준: 공시 전 10일 평균 수익률
        pre_returns = price_data[price_data["day_offset"] < 0]["return_pct"]
        benchmark_return = pre_returns.mean() if len(pre_returns) > 0 else 0

        price_data["abnormal_return"] = price_data["return_pct"] - benchmark_return
        price_data["car"] = price_data["abnormal_return"].cumsum()

        # 공시 후 CAR
        post_data = price_data[price_data["day_offset"] >= 0]
        car_post = post_data["car"].iloc[-1] if not post_data.empty else 0
        all_cars.append(car_post)

        # 공시 전 거래량 이상 감지
        pre_volume = price_data[price_data["day_offset"] < -3]["volume"]
        near_volume = price_data[
            (price_data["day_offset"] >= -3) & (price_data["day_offset"] < 0)
        ]["volume"]

        if len(pre_volume) > 0 and pre_volume.mean() > 0:
            volume_surge = near_volume.mean() / pre_volume.mean() if len(near_volume) > 0 else 1.0
        else:
            volume_surge = 1.0

        # 정보 선반영 여부 판단
        if volume_surge > 1.5:
            leakage = "의심"
        elif volume_surge > 1.2:
            leakage = "경미"
        else:
            leakage = "없음"

        events.append({
            "corp_name":       row["corp_name"],
            "stock_code":      row["stock_code"],
            "market":          row.get("market", ""),
            "filing_date":     row["report_date"],
            "reporter_name":   row["reporter_name"],
            "position":        row["position"],
            "buy_ratio":       row["buy_ratio"],
            "car_post":        round(car_post, 2),
            "volume_surge":    round(volume_surge, 2),
            "info_leakage":    leakage,
            "price_data":      price_data,
        })

    avg_car = np.mean(all_cars) if all_cars else 0

    summary = {
        "total_events":    len(events),
        "avg_car":         round(avg_car, 2),
        "positive_car":    sum(1 for c in all_cars if c > 0),
        "negative_car":    sum(1 for c in all_cars if c <= 0),
        "hit_rate":        round(sum(1 for c in all_cars if c > 0) / len(all_cars) * 100, 1) if all_cars else 0,
        "leakage_count":   sum(1 for e in events if e["info_leakage"] == "의심"),
    }

    return {"events": events, "avg_car": avg_car, "summary": summary}


def _fetch_real_event_data(
    stock_code: str,
    filing_date: str,
    days_before: int = 10,
    days_after: int = 10,
) -> pd.DataFrame:
    """실제 모드: pykrx에서 주가 데이터 조회"""
    try:
        from pykrx import stock as pykrx_stock

        filing_dt = datetime.strptime(filing_date, "%Y-%m-%d")
        start_dt = (filing_dt - timedelta(days=days_before + 10)).strftime("%Y%m%d")
        end_dt = (filing_dt + timedelta(days=days_after + 5)).strftime("%Y%m%d")

        ohlcv = pykrx_stock.get_market_ohlcv(start_dt, end_dt, stock_code)
        if ohlcv.empty:
            return pd.DataFrame()

        ohlcv = ohlcv.reset_index()
        col_map = {
            ohlcv.columns[0]: "date",
            "시가": "open", "고가": "high", "저가": "low", "종가": "close",
            "거래량": "volume", "거래대금": "trading_value", "등락률": "price_change",
        }
        ohlcv = ohlcv.rename(columns=col_map)
        ohlcv["date"] = pd.to_datetime(ohlcv["date"])
        ohlcv["return_pct"] = ohlcv["close"].pct_change() * 100

        # day_offset 계산
        ohlcv["day_offset"] = (ohlcv["date"] - filing_dt).dt.days

        # 범위 필터링
        ohlcv = ohlcv[
            (ohlcv["day_offset"] >= -days_before) &
            (ohlcv["day_offset"] <= days_after)
        ]

        return ohlcv[["date", "day_offset", "close", "volume", "return_pct"]].copy()

    except Exception as e:
        print(f"[Event Study] pykrx 조회 실패: {e}")
        return pd.DataFrame()
