"""
K-Insider Quant Monitor - 데이터 수집기 (Collector)

실제 모드: OpenDARTReader + pykrx 로 DART 공시 & 시장 데이터 수집
데모 모드: mock_data.py 에서 현실적인 샘플 데이터 생성
"""

import time
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from config import (
    DART_API_KEY, DEMO_MODE,
    STRONG_BUY_KEYWORDS, NOISE_KEYWORDS,
    POSITION_WEIGHTS, DEFAULT_MIN_RATIO,
)

# 공유 세션 (브라우저처럼 보이도록)
_SESSION = requests.Session()
_SESSION.headers.update({
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'ko-KR,ko;q=0.9',
    'Referer': 'http://dart.fss.or.kr/',
})


# ─────────────────────────────────────────────────────────────
# 공통 유틸
# ─────────────────────────────────────────────────────────────

def classify_signal(reason: str) -> str:
    if not reason:
        return "NORMAL"
    r = reason.replace(" ", "")
    for kw in STRONG_BUY_KEYWORDS:
        if kw.replace(" ", "") in r:
            return "BUY"
    for kw in NOISE_KEYWORDS:
        if kw.replace(" ", "") in r:
            return "NOISE"
    return "NORMAL"


def get_position_weight(position: str) -> int:
    if not position:
        return 1
    for key, weight in POSITION_WEIGHTS.items():
        if key in position:
            return weight
    return 3


def calculate_buy_ratio(shares_changed: int, total_shares: int) -> float:
    if total_shares <= 0:
        return 0.0
    return round((shares_changed / total_shares) * 100, 4)


# ─────────────────────────────────────────────────────────────
# HTML 파싱 헬퍼
# ─────────────────────────────────────────────────────────────

def _get(url: str, retries: int = 3) -> str:
    """딜레이·재시도 포함 HTTP GET. 실패 시 빈 문자열 반환."""
    for attempt in range(retries):
        try:
            time.sleep(0.5)
            r = _SESSION.get(url, timeout=15)
            if r.status_code == 200:
                return r.text
        except Exception:
            time.sleep(2.0 * (attempt + 1))
    return ""


def _parse_one_report(rcept_no: str, corp_code: str, corp_name: str,
                      reporter_url: str, holdings_url: str) -> list:
    """
    단일 보고서의 원문 HTML을 파싱하여 매수 거래 목록 반환.
    Returns: list of dicts
    """
    # ── 보고자 정보 파싱 ──────────────────────────────
    reporter_name = ""
    position = "임원"
    html = _get(reporter_url)
    if html:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            tbl = soup.find('table')
            if tbl:
                for row in tbl.find_all('tr'):
                    cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                    if len(cells) >= 3 and '성명' in cells[0]:
                        reporter_name = cells[2]
                    if '직위명' in ' '.join(cells):
                        try:
                            idx = cells.index('직위명')
                            position = cells[idx + 1] if idx + 1 < len(cells) else "임원"
                        except ValueError:
                            pass
        except Exception:
            pass

    # ── 거래 내역 파싱 ───────────────────────────────
    # 테이블 구조: [0]요약, [1]증권종류, [2]발행주식총수, [3]거래상세
    # 거래상세 헤더: 보고사유 | 변동일 | 종류 | 변동전 | 증감 | 변동후 | 단가 | ...
    transactions = []
    html = _get(holdings_url)
    if html:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            tables = soup.find_all('table')
            if len(tables) >= 4:
                tbl = tables[3]
                for row in tbl.find_all('tr')[2:]:  # 헤더 2행 스킵
                    cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                    if not cells or len(cells) < 6:
                        continue
                    reason = cells[0]
                    if not reason or '합' in reason:
                        continue

                    delta_str = cells[4].replace(',', '').replace('\xa0', '').strip()
                    after_str = cells[5].replace(',', '').replace('\xa0', '').strip()

                    try:
                        delta        = int(delta_str) if delta_str and delta_str != '-' else 0
                        shares_after = int(after_str) if after_str and after_str != '-' else 0
                    except ValueError:
                        continue

                    if delta <= 0:  # 매도 또는 변동 없음 제외
                        continue

                    transactions.append({
                        'rcept_no':       rcept_no,
                        'corp_code':      corp_code,
                        'corp_name':      corp_name,
                        'reporter_name':  reporter_name,
                        'position':       position,
                        'reason':         reason,
                        'shares_changed': delta,
                        'shares_after':   shares_after,
                    })
        except Exception:
            pass

    return transactions


# ─────────────────────────────────────────────────────────────
# 실제 모드: DART API + pykrx
# ─────────────────────────────────────────────────────────────

def fetch_real_data(target_date: str) -> pd.DataFrame:
    """
    당일 지분공시 목록을 가져와 원문 HTML 병렬 파싱으로 매수 거래만 추출.
    """
    try:
        import OpenDartReader
        from pykrx import stock as pykrx_stock
    except ImportError as e:
        print(f"[ERROR] 필요한 패키지가 없습니다: {e}")
        return pd.DataFrame()

    dart     = OpenDartReader(DART_API_KEY)
    date_str = target_date.replace("-", "")

    # 1) 당일 지분공시(D) 목록
    try:
        report_list = dart.list(start=target_date, end=target_date, kind='D', final=False)
    except Exception as e:
        print(f"[DART] 보고서 목록 조회 실패: {e}")
        return pd.DataFrame()

    if report_list is None or report_list.empty:
        print(f"[DART] {target_date} 지분공시 없음")
        return pd.DataFrame()

    # 임원·주요주주 소유보고만
    mask = report_list['report_nm'].str.contains('임원|주요주주 소유', na=False)
    insider_reports = report_list[mask].reset_index(drop=True)

    if insider_reports.empty:
        print(f"[DART] {target_date} 임원·주요주주 소유보고 없음")
        return pd.DataFrame()

    print(f"[DART] {target_date} 대상 보고서 {len(insider_reports)}건")

    # 2) sub_docs URL 수집 (메인 스레드 - dart 객체 비스레드세이프)
    parse_tasks = []
    for _, rpt in insider_reports.iterrows():
        rcept_no  = str(rpt.get("rcept_no", ""))
        corp_code = str(rpt.get("corp_code", ""))
        corp_name = str(rpt.get("corp_name", ""))
        try:
            sub = dart.sub_docs(rcept_no)
        except Exception:
            continue
        if sub is None or sub.empty:
            continue
        reporter_url = holdings_url = None
        for _, row in sub.iterrows():
            title = str(row.get('title', ''))
            url   = str(row.get('url', ''))
            if '보고자' in title:
                reporter_url = url
            elif '소유상황' in title or '특정증권' in title:
                holdings_url = url
        if reporter_url and holdings_url:
            parse_tasks.append((rcept_no, corp_code, corp_name, reporter_url, holdings_url))

    print(f"[DART] HTML 파싱 대상 {len(parse_tasks)}건 (순차 처리)")

    # 3) HTML 파싱 순차 처리 (DART 차단 방지)
    all_tx = []
    for task in parse_tasks:
        try:
            all_tx.extend(_parse_one_report(*task))
        except Exception:
            pass

    if not all_tx:
        print("[DART] 파싱된 매수 거래 없음")
        return pd.DataFrame()

    print(f"[DART] 매수 거래 {len(all_tx)}건 수집 완료")

    # 4) pykrx + corp_codes로 시장 데이터 보강
    try:
        kospi_list  = pykrx_stock.get_market_ticker_list(date_str, market="KOSPI")
        kosdaq_list = pykrx_stock.get_market_ticker_list(date_str, market="KOSDAQ")
    except Exception:
        kospi_list, kosdaq_list = [], []

    # corp_code → stock_code 매핑
    corp_code_map = {}
    try:
        cc = dart.corp_codes[['corp_code', 'stock_code']].dropna()
        cc = cc[cc['stock_code'] != '']
        corp_code_map = dict(zip(cc['corp_code'], cc['stock_code']))
    except Exception:
        pass

    rows = []
    for tx in all_tx:
        raw_code   = corp_code_map.get(tx['corp_code'], "")
        stock_code = raw_code.zfill(6) if raw_code else ""

        total_shares  = 0
        current_price = 0
        market_cap    = 0
        market        = ""
        sector        = "기타"

        if stock_code:
            try:
                if stock_code in kospi_list:
                    market = "KOSPI"
                elif stock_code in kosdaq_list:
                    market = "KOSDAQ"

                cap_info = pykrx_stock.get_market_cap(date_str, date_str, stock_code)
                if not cap_info.empty:
                    total_shares = int(cap_info.iloc[0].get("상장주식수", 0))
                    market_cap   = int(cap_info.iloc[0].get("시가총액", 0))

                ohlcv = pykrx_stock.get_market_ohlcv(date_str, date_str, stock_code)
                if not ohlcv.empty:
                    current_price = int(ohlcv.iloc[0].get("종가", 0))
            except Exception:
                pass

        shares_changed = tx['shares_changed']
        buy_ratio = calculate_buy_ratio(shares_changed, total_shares)
        signal    = classify_signal(tx['reason'])
        weight    = get_position_weight(tx['position'])

        rows.append({
            "report_date":     target_date,
            "rcept_no":        tx['rcept_no'],
            "corp_code":       tx['corp_code'],
            "corp_name":       tx['corp_name'],
            "stock_code":      stock_code,
            "reporter_name":   tx['reporter_name'],
            "position":        tx['position'],
            "change_reason":   tx['reason'],
            "shares_changed":  shares_changed,
            "shares_after":    tx['shares_after'],
            "total_shares":    total_shares,
            "buy_ratio":       buy_ratio,
            "signal_type":     signal,
            "position_weight": weight,
            "current_price":   current_price,
            "market_cap":      market_cap,
            "market":          market,
            "sector":          sector,
            "dart_url":        f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={tx['rcept_no']}",
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# 데모 모드
# ─────────────────────────────────────────────────────────────

def fetch_demo_data() -> pd.DataFrame:
    from mock_data import generate_demo_data
    return generate_demo_data(days_back=45, records_per_day=8)


# ─────────────────────────────────────────────────────────────
# 메인 수집 함수
# ─────────────────────────────────────────────────────────────

def collect_data(target_date: str = None) -> pd.DataFrame:
    """
    - DEMO_MODE=True  → 목업 데이터 생성
    - DEMO_MODE=False → DART API + pykrx 실제 데이터 수집
    """
    if DEMO_MODE:
        return fetch_demo_data()

    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    return fetch_real_data(target_date)
