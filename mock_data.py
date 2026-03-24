"""
K-Insider Quant Monitor - 데모 데이터 생성기
OpenDART API 키가 없을 때 현실적인 목업 데이터를 생성합니다.
"""

import random
from datetime import datetime, timedelta
import pandas as pd
from config import POSITION_WEIGHTS

# ── 한국 상장사 샘플 ──
# (종목코드, 기업명, 발행주식수, 현재가, 시가총액, 시장구분, 섹터)
SAMPLE_COMPANIES = [
    ("005930", "삼성전자",        5969782550, 71400,  426_200_000_000_000, "KOSPI",  "반도체"),
    ("000660", "SK하이닉스",       728002365, 178000, 129_584_000_000_000, "KOSPI",  "반도체"),
    ("035420", "NAVER",            163745195, 214000,  35_041_000_000_000, "KOSPI",  "서비스업"),
    ("035720", "카카오",           429801561,  41350,  17_772_000_000_000, "KOSPI",  "서비스업"),
    ("005380", "현대차",           211531506, 207500,  43_892_000_000_000, "KOSPI",  "운수장비"),
    ("000270", "기아",             407186936, 101200,  41_207_000_000_000, "KOSPI",  "운수장비"),
    ("051910", "LG화학",            70592343, 302000,  21_318_900_000_000, "KOSPI",  "화학"),
    ("006400", "삼성SDI",           68764530, 358000,  24_617_700_000_000, "KOSPI",  "전기전자"),
    ("028260", "삼성물산",         175572795,  98300,  17_258_700_000_000, "KOSPI",  "유통업"),
    ("068270", "셀트리온",         224909338, 168400,  37_874_700_000_000, "KOSPI",  "의약품"),
    ("207940", "삼성바이오로직스",  71174000, 780000,  55_515_700_000_000, "KOSPI",  "의약품"),
    ("055550", "신한지주",         501826487,  46700,  23_435_300_000_000, "KOSPI",  "금융업"),
    ("105560", "KB금융",           389075270,  72600,  28_246_900_000_000, "KOSPI",  "금융업"),
    ("003670", "포스코홀딩스",      84571230, 282000,  23_849_100_000_000, "KOSPI",  "철강금속"),
    ("373220", "LG에너지솔루션",   234000000, 358000,  83_772_000_000_000, "KOSPI",  "전기전자"),
    ("086790", "하나금융지주",     295242837,  56400,  16_651_700_000_000, "KOSPI",  "금융업"),
    ("010950", "S-Oil",            112582792,  63000,   7_092_700_000_000, "KOSPI",  "화학"),
    ("009150", "삼성전기",          74693696, 115500,   8_627_100_000_000, "KOSPI",  "전기전자"),
    ("034730", "SK",                47477986, 149000,   7_074_200_000_000, "KOSPI",  "기타금융"),
    ("015760", "한국전력",         641964077,  21550,  13_834_300_000_000, "KOSPI",  "전기가스업"),
    ("096770", "SK이노베이션",      94399296,  99300,   9_373_400_000_000, "KOSPI",  "화학"),
    ("032830", "삼성생명",         200000000,  71200,  14_240_000_000_000, "KOSPI",  "보험"),
    ("036570", "엔씨소프트",        21954022, 184500,   4_050_500_000_000, "KOSPI",  "서비스업"),
    ("352820", "하이브",            40763589, 194500,   7_928_500_000_000, "KOSPI",  "서비스업"),
    ("251270", "넷마블",            85487942,  50200,   4_291_500_000_000, "KOSPI",  "서비스업"),
    # KOSDAQ 종목
    ("247540", "에코프로비엠",      55148702, 166400,   9_176_700_000_000, "KOSDAQ", "일반전기전자"),
    ("263750", "펄어비스",          48280694,  36050,   1_740_500_000_000, "KOSDAQ", "디지털컨텐츠"),
    ("042700", "한미반도체",        98614015,  73200,   7_218_500_000_000, "KOSDAQ", "반도체"),
    ("122870", "와이지엔터",        81376930,  41200,   3_352_700_000_000, "KOSDAQ", "오락문화"),
    ("091990", "셀트리온헬스케어",  143780385, 59300,   8_526_200_000_000, "KOSDAQ", "유통"),
    ("328130", "루닛",              24350000, 72300,    1_760_505_000_000, "KOSDAQ", "소프트웨어"),
    ("403870", "HPSP",              23920000, 33500,      801_320_000_000, "KOSDAQ", "반도체"),
    ("058470", "리노공업",          16909338, 198000,   3_348_049_000_000, "KOSDAQ", "반도체"),
    ("257720", "실리콘투",          50000000,  8700,      435_000_000_000, "KOSDAQ", "유통"),
]

REPORTER_NAMES = [
    "김영호", "이재현", "박준성", "정민수", "최승우",
    "한지영", "오동환", "윤서진", "장태석", "송민아",
    "임현우", "강도윤", "조영래", "배수진", "류현석",
    "신동혁", "황보경", "서지훈", "전민규", "권나영",
]

POSITIONS = [
    "대표이사", "최대주주", "사내이사", "CFO", "전략이사",
    "사외이사", "감사", "등기임원", "미등기임원", "주요주주",
    "특수관계인",
]

BUY_REASONS = [
    "장내매수", "장내 매수", "장외매수", "장외 매수",
    "시간외매수", "시간외 매수", "장내취득", "시간외취득",
]
NOISE_REASONS = [
    "증여", "상속", "스톡옵션 행사", "주식매수선택권 행사",
    "담보 제공", "신탁 해지", "무상 취득", "CB전환",
]
NORMAL_REASONS = [
    "장내매도", "장외매도", "시간외매도",
]


def _random_date_range(days_back: int = 45) -> list:
    today = datetime.now().date()
    dates = []
    for i in range(days_back):
        d = today - timedelta(days=i)
        if d.weekday() < 5:
            dates.append(d.strftime("%Y-%m-%d"))
    return dates


def generate_demo_data(days_back: int = 45, records_per_day: int = 8) -> pd.DataFrame:
    dates = _random_date_range(days_back)
    rows = []
    rcept_counter = 20240001

    for date_str in dates:
        n = random.randint(max(2, records_per_day - 3), records_per_day + 4)

        for _ in range(n):
            company = random.choice(SAMPLE_COMPANIES)
            stock_code, corp_name, total_shares, price, mcap, market, sector = company

            roll = random.random()
            if roll < 0.30:
                reason = random.choice(BUY_REASONS)
                signal = "BUY"
                ratio = round(random.uniform(0.01, 0.35), 4)
            elif roll < 0.55:
                reason = random.choice(NOISE_REASONS)
                signal = "NOISE"
                ratio = round(random.uniform(0.001, 0.1), 4)
            else:
                reason = random.choice(NORMAL_REASONS)
                signal = "NORMAL"
                ratio = round(random.uniform(0.005, 0.15), 4)

            shares_changed = int(total_shares * ratio / 100)
            position = random.choice(POSITIONS)
            weight = POSITION_WEIGHTS.get(position, 3)

            if signal == "BUY" and random.random() < 0.35:
                position = random.choice(["대표이사", "최대주주", "CFO"])
                weight = POSITION_WEIGHTS.get(position, 8)

            daily_price = int(price * random.uniform(0.95, 1.05))
            daily_mcap = daily_price * total_shares

            rows.append({
                "report_date":    date_str,
                "rcept_no":       str(rcept_counter),
                "corp_code":      f"00{stock_code}",
                "corp_name":      corp_name,
                "stock_code":     stock_code,
                "reporter_name":  random.choice(REPORTER_NAMES),
                "position":       position,
                "change_reason":  reason,
                "shares_changed": shares_changed,
                "shares_after":   int(shares_changed * random.uniform(1.0, 5.0)),
                "total_shares":   total_shares,
                "buy_ratio":      round(ratio, 4),
                "signal_type":    signal,
                "position_weight": weight,
                "current_price":  daily_price,
                "market_cap":     daily_mcap,
                "market":         market,
                "sector":         sector,
                "dart_url":       f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_counter}",
            })
            rcept_counter += 1

    return pd.DataFrame(rows)
