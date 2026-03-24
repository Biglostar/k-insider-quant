"""
K-Insider Quant Monitor - SQLite 데이터베이스 관리
"""

import sqlite3
import pandas as pd
from config import DB_PATH


def get_connection():
    """SQLite 연결 생성 (WAL 모드)"""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """테이블 초기화 (없으면 생성)"""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS insider_trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date     TEXT NOT NULL,           -- 보고일자 (YYYY-MM-DD)
            rcept_no        TEXT UNIQUE NOT NULL,     -- DART 접수번호
            corp_code       TEXT,                     -- DART 기업코드
            corp_name       TEXT NOT NULL,            -- 기업명
            stock_code      TEXT,                     -- 종목코드 (6자리)
            reporter_name   TEXT,                     -- 보고자 이름
            position        TEXT,                     -- 직위
            change_reason   TEXT,                     -- 변동사유
            shares_changed  INTEGER DEFAULT 0,        -- 변동 주식수
            shares_after    INTEGER DEFAULT 0,        -- 변동 후 보유수
            total_shares    INTEGER DEFAULT 0,        -- 발행주식총수
            buy_ratio       REAL DEFAULT 0.0,         -- 매수비중 (%)
            signal_type     TEXT DEFAULT 'NORMAL',    -- BUY / NOISE / NORMAL
            position_weight INTEGER DEFAULT 0,        -- 직위 가중치
            current_price   INTEGER DEFAULT 0,        -- 현재 주가
            market_cap      INTEGER DEFAULT 0,        -- 시가총액
            market          TEXT DEFAULT '',             -- 시장구분 (KOSPI/KOSDAQ)
            sector          TEXT DEFAULT '기타',       -- 업종 (KRX 업종분류)
            dart_url        TEXT,                     -- DART 원문 링크
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_report_date ON insider_trades(report_date);
        CREATE INDEX IF NOT EXISTS idx_signal_type ON insider_trades(signal_type);
        CREATE INDEX IF NOT EXISTS idx_stock_code  ON insider_trades(stock_code);
        CREATE INDEX IF NOT EXISTS idx_sector      ON insider_trades(sector);
    """)
    conn.close()


def upsert_trades(df: pd.DataFrame):
    """DataFrame을 DB에 삽입 (중복 무시)"""
    if df.empty:
        return 0

    conn = get_connection()
    inserted = 0
    for _, row in df.iterrows():
        try:
            conn.execute("""
                INSERT OR IGNORE INTO insider_trades (
                    report_date, rcept_no, corp_code, corp_name, stock_code,
                    reporter_name, position, change_reason, shares_changed,
                    shares_after, total_shares, buy_ratio, signal_type,
                    position_weight, current_price, market_cap, market, sector, dart_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get("report_date"), row.get("rcept_no"), row.get("corp_code"),
                row.get("corp_name"), row.get("stock_code"), row.get("reporter_name"),
                row.get("position"), row.get("change_reason"),
                int(row.get("shares_changed", 0)), int(row.get("shares_after", 0)),
                int(row.get("total_shares", 0)), float(row.get("buy_ratio", 0)),
                row.get("signal_type", "NORMAL"), int(row.get("position_weight", 0)),
                int(row.get("current_price", 0)), int(row.get("market_cap", 0)),
                row.get("market", ""), row.get("sector", "기타"), row.get("dart_url"),
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            continue
    conn.commit()
    conn.close()
    return inserted


def query_trades(
    start_date: str = None,
    end_date: str = None,
    signal_only: bool = True,
    min_ratio: float = 0.05,
    positions: list = None,
) -> pd.DataFrame:
    """조건부 거래 조회"""
    conn = get_connection()
    query = "SELECT * FROM insider_trades WHERE 1=1"
    params = []

    if start_date:
        query += " AND report_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND report_date <= ?"
        params.append(end_date)
    if signal_only:
        query += " AND signal_type = 'BUY'"
    if min_ratio > 0:
        query += " AND buy_ratio >= ?"
        params.append(min_ratio)
    if positions:
        placeholders = ",".join(["?"] * len(positions))
        query += f" AND position IN ({placeholders})"
        params.extend(positions)

    query += " ORDER BY report_date DESC, buy_ratio DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def query_sector_summary(days: int = 30) -> pd.DataFrame:
    """최근 N일간 섹터별 매수 집계"""
    conn = get_connection()
    query = """
        SELECT
            sector,
            COUNT(*)            AS buy_count,
            SUM(shares_changed) AS total_shares,
            AVG(buy_ratio)      AS avg_ratio,
            COUNT(DISTINCT stock_code) AS unique_stocks
        FROM insider_trades
        WHERE signal_type = 'BUY'
          AND report_date >= date('now', ? || ' days')
        GROUP BY sector
        ORDER BY buy_count DESC
    """
    df = pd.read_sql_query(query, conn, params=[f"-{days}"])
    conn.close()
    return df


def query_daily_counts(days: int = 30) -> pd.DataFrame:
    """최근 N일간 일별 매수 신호 건수"""
    conn = get_connection()
    query = """
        SELECT
            report_date,
            COUNT(*) AS signal_count,
            SUM(CASE WHEN position_weight >= 8 THEN 1 ELSE 0 END) AS top_exec_count
        FROM insider_trades
        WHERE signal_type = 'BUY'
          AND report_date >= date('now', ? || ' days')
        GROUP BY report_date
        ORDER BY report_date
    """
    df = pd.read_sql_query(query, conn, params=[f"-{days}"])
    conn.close()
    return df


def get_all_dates() -> list:
    """DB에 저장된 모든 날짜 목록"""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT DISTINCT report_date FROM insider_trades ORDER BY report_date DESC"
    )
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates
