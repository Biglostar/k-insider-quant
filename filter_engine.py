"""
K-Insider Quant Monitor - 퀀트 필터 엔진

핵심 필터링 로직:
1. BUY 신호만 추출 (장내/장외/시간외 매수)
2. 매수 비중 ≥ 기준치 (기본 0.05%)
3. NOISE 제거 (증여/상속/스톡옵션 등)
4. 직위 가중치 정렬
"""

import pandas as pd
from config import DEFAULT_MIN_RATIO


def apply_quant_filter(
    df: pd.DataFrame,
    min_ratio: float = DEFAULT_MIN_RATIO,
    positions: list = None,
    signal_types: list = None,
) -> pd.DataFrame:
    """
    퀀트 필터를 적용하여 고순도 매수 신호만 추출합니다.

    Parameters:
        df:            원본 DataFrame
        min_ratio:     최소 매수 비중 (%, 기본 0.05)
        positions:     필터링할 직위 리스트 (None이면 전체)
        signal_types:  허용할 신호 유형 (기본 ['BUY'])

    Returns:
        필터링된 DataFrame (가중치 내림차순 정렬)
    """
    if df.empty:
        return df

    filtered = df.copy()

    # 1) BUY 신호만 (기본)
    if signal_types is None:
        signal_types = ["BUY"]
    filtered = filtered[filtered["signal_type"].isin(signal_types)]

    # 2) 최소 매수 비중 필터
    if min_ratio > 0:
        filtered = filtered[filtered["buy_ratio"] >= min_ratio]

    # 3) 직위 필터
    if positions:
        filtered = filtered[filtered["position"].isin(positions)]

    # 4) 정렬: 가중치 → 매수비중 → 날짜 (모두 내림차순)
    filtered = filtered.sort_values(
        by=["position_weight", "buy_ratio", "report_date"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    return filtered


def compute_signal_score(row: pd.Series) -> float:
    """
    개별 거래의 종합 신호 점수 산출 (0~100)

    가중 요소:
    - 직위 가중치 (40%)
    - 매수 비중   (40%)
    - 변동사유    (20%)
    """
    # 직위 점수 (0~10 → 0~40)
    pos_score = min(row.get("position_weight", 0), 10) * 4

    # 비중 점수: 0.05% → 10점, 0.5%+ → 40점 (로그 스케일)
    ratio = row.get("buy_ratio", 0)
    if ratio >= 0.5:
        ratio_score = 40
    elif ratio >= 0.1:
        ratio_score = 25 + (ratio - 0.1) / 0.4 * 15
    elif ratio >= 0.05:
        ratio_score = 10 + (ratio - 0.05) / 0.05 * 15
    else:
        ratio_score = ratio / 0.05 * 10

    # 변동사유 보너스
    reason = str(row.get("change_reason", ""))
    reason_score = 10  # 기본
    if "장내매수" in reason:
        reason_score = 20  # 가장 강력한 의지 표현
    elif "시간외매수" in reason:
        reason_score = 18
    elif "장외매수" in reason:
        reason_score = 15

    total = pos_score + ratio_score + reason_score
    return round(min(total, 100), 1)


def add_signal_scores(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame에 종합 신호 점수 컬럼 추가"""
    if df.empty:
        return df
    df = df.copy()
    df["signal_score"] = df.apply(compute_signal_score, axis=1)
    return df.sort_values("signal_score", ascending=False).reset_index(drop=True)


def get_top_signals(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """상위 N개 매수 신호 추출"""
    scored = add_signal_scores(df)
    return scored.head(top_n)
