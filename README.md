# KIS 주식 정보 조회 시스템

한국투자증권(KIS) API를 활용한 주식 정보 조회 웹 애플리케이션입니다. 종목 검색, 현재가 조회, 투자자 동향 분석 기능을 제공합니다.

## 주요 기능

- 📊 **종목 검색**: 종목명으로 KOSPI/KOSDAQ 종목 검색
- 💰 **실시간 현재가**: KIS API를 통한 정확한 시가/종가 조회
- 📈 **투자자 동향**: 개인/외국인/기관별 일자별 매매동향 분석
- 📋 **데이터 그리드**: Toast UI Grid를 활용한 테이블 표시
- 📥 **CSV 다운로드**: 조회 데이터 내보내기 기능
- 🎨 **모던 UI**: 다크 테마의 반응형 웹 인터페이스

## 기술 스택

- **Backend**: FastAPI, Python 3.8+
- **Frontend**: HTML5, JavaScript, Toast UI Grid, Chart.js
- **API**: 한국투자증권 KIS API, KRX KIND API

## 설치 방법

1. 저장소 클론
```bash
git clone <repository-url>
cd Trader
```

2. 가상환경 설정 (권장)
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. 의존성 설치
```bash
pip install -r requirements.txt
```

## 환경변수 설정

`.env.example`을 참고해서 프로젝트 루트에 `.env` 파일을 생성하세요.

**필수 환경변수:**
```
KIS_APP_KEY=your_kis_app_key
KIS_APP_SECRET=your_kis_app_secret
KIS_BASE_URL=https://openapivts.koreainvestment.com:29443  # 모의투자
# KIS_BASE_URL=https://openapi.koreainvestment.com:9443     # 실전투자
```

**선택적 환경변수:**
```
STOCK_CACHE_FILE=stocks_cache.json  # 종목 캐시 파일 경로
```

## 실행 방법

```bash
uvicorn main:app --reload
```

서버가 시작되면 브라우저에서 `http://127.0.0.1:8000` 으로 접속하세요.

## API 엔드포인트

- `GET /` - 웹 인터페이스
- `GET /api/quote?symbol={종목코드}` - 현재가 조회
- `GET /api/stocks/search?name={종목명}` - 종목 검색
- `GET /api/investor-trend?symbol={종목코드}` - 투자자 동향
- `GET /api/token` - 접근 토큰 조회

## 사용 방법

1. **종목 검색**: 검색창에 종목명 입력 (예: 삼성전자)
2. **데이터 조회**: 검색 결과 클릭 또는 종목코드 직접 입력 후 "전체 조회"
3. **상세 보기**: 그리드 행 클릭하여 일자별 상세 정보 확인
4. **데이터 내보내기**: "CSV 다운로드" 버튼으로 데이터 저장

## 주의사항

- 서버 시작 시 KRX 상장 종목 목록을 자동으로 로드하고 캐시합니다
- KIS API는 실시간 데이터를 제공하므로 인터넷 연결이 필요합니다
- 모의투자 계정으로 테스트 후 실전투자로 전환하는 것을 권장합니다
- API 호출 제한에 주의하여 과도한 요청을 피하세요

## 라이선스

MIT License

## 기여

버그 리포트나 기능 요청은 Issues를 통해 제출해 주세요.
