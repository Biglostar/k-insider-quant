"""
K-Insider Quant Monitor - 설정 파일
"""

import os
from pathlib import Path

# ── OpenDART API ──────────────────────────────────────────────
DART_API_KEY = os.environ.get("DART_API_KEY", "")
DEMO_MODE = not bool(DART_API_KEY)

# ── 데이터베이스 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "insider_trades.db"

# ── 퀀트 필터 기본값 ─────────────────────────────────────────
DEFAULT_MIN_RATIO = 0.05          # 발행주식 대비 최소 매수 비중 (%)
STRONG_BUY_KEYWORDS = [
    "장내매수", "장내 매수",
    "장외매수", "장외 매수",
    "시간외매수", "시간외 매수",
    "장내취득", "장외취득", "시간외취득",
]
NOISE_KEYWORDS = [
    "증여", "상속", "스톡옵션", "주식매수선택권",
    "담보", "질권", "신탁", "무상",
    "CB전환", "BW행사", "EB전환",
]

# ── 직위 가중치 (높을수록 강한 신호) ─────────────────────────
POSITION_WEIGHTS = {
    "대표이사":     10,
    "최대주주":     10,
    "부회장":       9,
    "사내이사":     8,
    "CFO":          8,
    "재무이사":     8,
    "전략이사":     7,
    "사외이사":     5,
    "감사":         5,
    "임원":         6,
    "등기임원":     6,
    "미등기임원":   4,
    "주요주주":     7,
    "특수관계인":   3,
}

# ── 시장 구분 ────────────────────────────────────────────────
# 실제 모드에서는 pykrx.stock.get_market_ticker_list()로 자동 판별
# 데모 모드에서는 아래 폴백 사용
MARKET_KOSPI = "KOSPI"
MARKET_KOSDAQ = "KOSDAQ"

# ── 섹터 분류 방식 ───────────────────────────────────────────
# 실제 모드: pykrx.stock.get_market_ticker_name() +
#            pykrx.stock.get_index_portfolio_deposit_file() 등으로
#            KRX 업종분류를 자동 조회합니다.
# 데모 모드: mock_data.py 내 샘플 기업에 섹터/시장 정보를 포함합니다.
#
# ※ 기존처럼 종목코드별 수동 매핑(SECTOR_MAP)은 제거했습니다.
#   30개 종목만 커버되는 한계가 있었기 때문에,
#   pykrx의 KRX 업종 분류를 활용하는 방식으로 전환합니다.
