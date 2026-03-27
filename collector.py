"""
K-Insider Quant Monitor - 데이터 수집기 (Collector)

실제 모드: OpenDARTReader + pykrx 로 DART 공시 & 시장 데이터 수집
데모 모드: mock_data.py 에서 현실적인 샘플 데이터 생성
"""

import pandas as pd
from datetime import datetime, timedelta

from config import (
    DART_API_KEY, DEMO_MODE,
    STRONG_BUY_KEYWORDS, NOISE_KEYWORDS,
    POSITION_WEIGHTS, DEFAULT_MIN_RATIO,
)


# ─────────────────────────────────────────────────────────────
# 신호 분류 함수 (공통)
# ─────────────────────────────────────────────────────────────

def classify_signal(reason: str) -> str:
    """변동사유 텍스트를 분석하여 신호 유형 분류"""
    if not reason:
        return "NORMAL"
    reason_clean = reason.replace(" ", "")
    for kw in STRONG_BUY_KEYWORDS:
        if kw.replace(" ", "") in reason_clean:
            return "BUY"
    for kw in NOISE_KEYWORDS:
        if kw.replace(" ", "") in reason_clean:
            return "NOISE"
    return "NORMAL"


def get_position_weight(position: str) -> int:
    """직위에 따른 가중치 반환"""
    if not position:
        return 1
    for key, weight in POSITION_WEIGHTS.items():
        if key in position:
            return weight
    return 3  # 기본값


def calculate_buy_ratio(shares_changed: int, total_shares: int) -> float:
    """매수 비중 계산 (%)"""
    if total_shares <= 0:
        return 0.0
    return round((shares_changed / total_shares) * 100, 4)


# ─────────────────────────────────────────────────────────────
# 실제 모드: DART API + pykrx
# ─────────────────────────────────────────────────────────────

def fetch_real_data(target_date: str) -> pd.DataFrame:
    """
    OpenDARTReader로 지분변동 보고서를 수집하고
    pykrx로 시장 데이터를 보강합니다.

    Parameters:
        target_date: 'YYYY-MM-DD' 형식의 조회 날짜

    Returns:
        가공된 DataFrame
    """
    try:
        import OpenDartReader
        from OpenDartReader import dart_share
        from pykrx import stock as pykrx_stock
    except ImportError as e:
        print(f"[ERROR] 필요한 패키지가 없습니다: {e}")
        return pd.DataFrame()

    dart = OpenDartReader(DART_API_KEY)
    date_str = target_date.replace("-", "")

    # 1) 당일 지분공시(D) 목록 조회
    try:
        report_list = dart.list(start=target_date, end=target_date, kind='D', final=False)
    except Exception as e:
        print(f"[DART] 보고서 목록 조회 실패: {e}")
        return pd.DataFrame()

    if report_list is None or report_list.empty:
        print(f"[DART] {target_date} 지분공시 없음")
        return pd.DataFrame()

    # 임원·주요주주 소유보고만 필터링
    insider_mask = report_list['report_nm'].str.contains('임원|주요주주 소유', na=False)
    insider_reports = report_list[insider_mask].copy()

    if insider_reports.empty:
        print(f"[DART] {target_date} 임원·주요주주 소유보고 없음")
        return pd.DataFrame()

    # 오늘 접수번호 세트
    today_rcept_nos = set(insider_reports['rcept_no'].astype(str))

    # pykrx 시장 목록 (반복 호출 방지)
    try:
        kospi_list = pykrx_stock.get_market_ticker_list(date_str, market="KOSPI")
        kosdaq_list = pykrx_stock.get_market_ticker_list(date_str, market="KOSDAQ")
    except Exception:
        kospi_list, kosdaq_list = [], []

    rows = []
    processed_corps = set()

    for _, rpt in insider_reports.iterrows():
        rcept_no = str(rpt.get("rcept_no", ""))
        corp_code = str(rpt.get("corp_code", ""))
        corp_name = str(rpt.get("corp_name", ""))

        if corp_code in processed_corps:
            continue
        processed_corps.add(corp_code)

        # 2) 임원·주요주주 소유 상세 조회 (elestock API)
        try:
            detail = dart_share.major_shareholders_exec(DART_API_KEY, corp_code)
        except Exception as e:
            print(f"[DART] {corp_name} 상세 조회 실패: {e}")
            continue

        if detail is None or detail.empty:
            continue

        # 오늘 접수번호에 해당하는 건만 필터링
        if 'rcept_no' in detail.columns:
            detail = detail[detail['rcept_no'].astype(str).isin(today_rcept_nos)]

        for _, d in detail.iterrows():
            reason = str(d.get("stkqy_irds_rs", ""))
            signal = classify_signal(reason)

            try:
                shares_changed = abs(int(str(d.get("stkqy_irds", 0)).replace(",", "") or 0))
                shares_after = abs(int(str(d.get("stkqy", 0)).replace(",", "") or 0))
            except (ValueError, TypeError):
                shares_changed, shares_after = 0, 0

            reporter_name = str(d.get("hmpr_nm", ""))
            position = str(d.get("ofcps", "임원"))
            stock_code = str(d.get("stkcd", "")).zfill(6)
            row_rcept_no = str(d.get("rcept_no", rcept_no))

            # 3) pykrx로 시장 데이터 조회
            total_shares = 0
            current_price = 0
            market_cap = 0
            market = ""
            sector = "기타"

            try:
                if stock_code in kospi_list:
                    market = "KOSPI"
                elif stock_code in kosdaq_list:
                    market = "KOSDAQ"

                cap_info = pykrx_stock.get_market_cap(date_str, date_str, stock_code)
                if not cap_info.empty:
                    total_shares = int(cap_info.iloc[0].get("상장주식수", 0))
                    market_cap = int(cap_info.iloc[0].get("시가총액", 0))

                ohlcv = pykrx_stock.get_market_ohlcv(date_str, date_str, stock_code)
                if not ohlcv.empty:
                    current_price = int(ohlcv.iloc[0].get("종가", 0))
            except Exception:
                pass

            buy_ratio = calculate_buy_ratio(shares_changed, total_shares)
            weight = get_position_weight(position)

            rows.append({
                "report_date":     target_date,
                "rcept_no":        row_rcept_no,
                "corp_code":       corp_code,
                "corp_name":       corp_name,
                "stock_code":      stock_code,
                "reporter_name":   reporter_name,
                "position":        position,
                "change_reason":   reason,
                "shares_changed":  shares_changed,
                "shares_after":    shares_after,
                "total_shares":    total_shares,
                "buy_ratio":       buy_ratio,
                "signal_type":     signal,
                "position_weight": weight,
                "current_price":   current_price,
                "market_cap":      market_cap,
                "market":          market,
                "sector":          sector,
                "dart_url":        f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={row_rcept_no}",
            })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# 데모 모드
# ─────────────────────────────────────────────────────────────

def fetch_demo_data() -> pd.DataFrame:
    """mock_data에서 데모 데이터 생성"""
    from mock_data import generate_demo_data
    return generate_demo_data(days_back=45, records_per_day=8)


# ─────────────────────────────────────────────────────────────
# 메인 수집 함수
# ─────────────────────────────────────────────────────────────

def collect_data(target_date: str = None) -> pd.DataFrame:
    """
    모드에 따라 데이터를 수집합니다.

    - DEMO_MODE=True  → 목업 데이터 생성
    - DEMO_MODE=False → DART API + pykrx 실제 데이터 수집
    """
    if DEMO_MODE:
        return fetch_demo_data()

    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    return fetch_real_data(target_date)
