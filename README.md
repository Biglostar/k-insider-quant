# 🔍 K-Insider Quant Monitor

한국 DART 공시 시스템의 내부자 거래 데이터를 자동 분석하여, 임원 및 대주주의 **'진짜 매수 신호'**를 포착하는 퀀트 대시보드입니다.

---

## 📸 주요 기능

| 기능 | 설명 |
|------|------|
| **매수 신호 포착** | 장내/장외/시간외 매수만 필터링 (증여·상속·스톡옵션 등 노이즈 제거) |
| **비중 기반 필터** | 발행주식 대비 0.05% 이상 매수만 추출 |
| **직위 가중치** | 대표이사/최대주주 > CFO > 일반임원 순 우선순위 |
| **신호 점수** | 직위·비중·사유를 종합한 0~100 시그널 스코어 |
| **섹터 분석** | 최근 30일간 내부자 매수가 집중된 업종 시각화 |
| **DART 원문 링크** | 클릭 한 번으로 공시 원문 확인 |

---

## 🚀 빠른 시작

### 1. 설치

```bash
# 저장소 클론
git clone https://github.com/YOUR_USERNAME/k-insider-quant.git
cd k-insider-quant

# 의존성 설치
pip install -r requirements.txt
```

### 2. 데모 모드 실행 (API 키 불필요)

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501`이 자동으로 열립니다.  
API 키 없이도 시뮬레이션 데이터로 전체 기능을 체험할 수 있습니다.

### 3. 실제 모드 전환 (OpenDART API 키 필요)

```bash
# 방법 1: 환경 변수
export DART_API_KEY="YOUR_API_KEY_HERE"
streamlit run app.py

# 방법 2: .env 파일 (추천)
echo 'DART_API_KEY=YOUR_API_KEY_HERE' > .env
streamlit run app.py
```

> **API 키 발급**: https://opendart.fss.or.kr 에서 무료 회원가입 후 발급

---

## 📁 프로젝트 구조

```
k-insider-quant/
├── .streamlit/
│   └── config.toml          # Streamlit 테마 설정 (다크 모드)
├── app.py                    # 메인 대시보드 (Streamlit)
├── config.py                 # 설정 상수 (필터 기준, 가중치 등)
├── database.py               # SQLite DB 관리
├── collector.py              # 데이터 수집기 (DART API + pykrx)
├── filter_engine.py          # 퀀트 필터링 엔진
├── mock_data.py              # 데모 데이터 생성기
├── requirements.txt          # Python 의존성
├── insider_trades.db         # SQLite DB (자동 생성)
└── README.md
```

---

## ⚙️ 핵심 퀀트 로직

### 매수 신호 분류

| 분류 | 키워드 | 설명 |
|------|--------|------|
| **BUY** (강력 매수) | 장내매수, 장외매수, 시간외매수 | 실제 자본 투입 유상 취득 |
| **NOISE** (노이즈) | 증여, 상속, 스톡옵션, 담보 | 정보 가치 없는 기계적 변동 |
| **NORMAL** (일반) | 장내매도, 기타 | 매도 및 기타 변동 |

### 신호 점수 산출 (0~100)

```
총점 = 직위 점수(40%) + 매수 비중 점수(40%) + 변동사유 보너스(20%)
```

- **직위 점수**: 대표이사(40) > CFO(32) > 일반임원(24) > 특수관계인(12)
- **비중 점수**: 0.5%↑ → 40점 / 0.1% → 25점 / 0.05% → 10점
- **사유 보너스**: 장내매수(20) > 시간외(18) > 장외(15) > 기본(10)

---

## 🛠 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| 언어 | Python 3.10+ |
| 대시보드 | Streamlit |
| 데이터 수집 | OpenDARTReader (DART 공시) |
| 시장 데이터 | pykrx (KRX 주가/시가총액) |
| 차트 | Plotly |
| 데이터베이스 | SQLite3 |

---

## 📋 Streamlit Cloud 배포

1. GitHub에 코드 업로드
2. [share.streamlit.io](https://share.streamlit.io) 접속
3. 레포 연결 후 `app.py` 지정
4. Secrets에 `DART_API_KEY` 추가:
   ```toml
   DART_API_KEY = "YOUR_KEY"
   ```
5. Deploy 클릭

---

## ⚠️ 면책 조항

본 프로그램은 교육 및 정보 제공 목적으로 제작되었으며, 투자 조언이 아닙니다.  
투자 판단의 최종 책임은 투자자 본인에게 있습니다.

---

## 📄 라이선스

MIT License
