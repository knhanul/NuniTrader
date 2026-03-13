import json
import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from config import settings

app = FastAPI(title="KIS FastAPI Server")
BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
STOCK_CACHE_FILE = Path(settings.stock_cache_file)
TOKEN_CACHE_FILE = BASE_DIR / "token_cache.json"
TOKEN_CACHE: dict[str, Any] = {}
STOCK_INDEX: list[dict[str, str]] = []
STOCK_NAME_LOOKUP: dict[str, list[dict[str, str]]] = {}


def validate_settings() -> None:
    if not settings.kis_app_key or not settings.kis_app_secret:
        raise HTTPException(status_code=500, detail="KIS_APP_KEY 또는 KIS_APP_SECRET 환경변수가 설정되지 않았습니다.")


def save_token_cache(token: str, timestamp: float) -> None:
    """토큰과 타임스탬프를 파일에 저장"""
    try:
        cache_data = {
            "access_token": token,
            "timestamp": timestamp
        }
        TOKEN_CACHE_FILE.write_text(
            json.dumps(cache_data, ensure_ascii=False, indent=2), 
            encoding="utf-8"
        )
    except (OSError, IOError) as e:
        # 파일 저장 실패 시 메모리 캐시에만 저장
        TOKEN_CACHE["access_token"] = token


def load_token_cache() -> tuple[str | None, float | None]:
    """파일에서 토큰과 타임스탬프를 로드"""
    try:
        if not TOKEN_CACHE_FILE.exists():
            return None, None
        
        data = json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
        token = data.get("access_token")
        timestamp = data.get("timestamp")
        
        if isinstance(token, str) and isinstance(timestamp, (int, float)):
            return token, float(timestamp)
        return None, None
    except (json.JSONDecodeError, OSError, IOError, KeyError, TypeError):
        return None, None


def is_token_valid(timestamp: float) -> bool:
    """토큰이 23시간 이내에 발급되었는지 확인"""
    current_time = datetime.datetime.now().timestamp()
    return (current_time - timestamp) < (23 * 60 * 60)  # 23시간


def parse_int(value: Any) -> int:
    text = str(value or "0").replace(",", "").strip()
    if text == "":
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def save_stock_cache(stocks: list[dict[str, str]]) -> None:
    STOCK_CACHE_FILE.write_text(json.dumps(stocks, ensure_ascii=False, indent=2), encoding="utf-8")


def load_stock_cache() -> list[dict[str, str]]:
    if not STOCK_CACHE_FILE.exists():
        return []
    try:
        data = json.loads(STOCK_CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def parse_kind_stock_rows(html: str, market_label: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []
    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    if not headers:
        return []

    rows: list[dict[str, str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) != len(headers):
            continue
        values = {headers[index]: cells[index].get_text(strip=True) for index in range(len(headers))}
        name = values.get("회사명", "").strip()
        symbol = values.get("종목코드", "").strip().zfill(6)
        if not name or not symbol:
            continue
        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "market": market_label,
            }
        )
    return rows


def fetch_kind_market_stocks(market_type: str, market_label: str) -> list[dict[str, str]]:
    url = "https://kind.krx.co.kr/corpgeneral/corpList.do"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://kind.krx.co.kr/",
    }
    payload = {
        "method": "download",
        "searchType": "13",
        "marketType": market_type,
    }
    response = requests.post(url, data=payload, headers=headers, timeout=20)
    response.raise_for_status()
    return parse_kind_stock_rows(response.text, market_label)


def build_stock_index() -> list[dict[str, str]]:
    try:
        stocks = fetch_kind_market_stocks("stockMkt", "KOSPI") + fetch_kind_market_stocks("kosdaqMkt", "KOSDAQ")
        if stocks:
            save_stock_cache(stocks)
            return stocks
    except requests.RequestException:
        pass

    cached = load_stock_cache()
    if cached:
        return cached

    return [
        {"symbol": "005930", "name": "삼성전자", "market": "KOSPI"},
        {"symbol": "000660", "name": "SK하이닉스", "market": "KOSPI"},
        {"symbol": "035420", "name": "NAVER", "market": "KOSPI"},
        {"symbol": "035720", "name": "카카오", "market": "KOSPI"},
    ]


def rebuild_stock_name_lookup(stocks: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    lookup: dict[str, list[dict[str, str]]] = {}
    for stock in stocks:
        normalized = stock["name"].strip().lower()
        lookup.setdefault(normalized, []).append(stock)
    return lookup


def initialize_stock_data() -> None:
    global STOCK_INDEX, STOCK_NAME_LOOKUP
    STOCK_INDEX = build_stock_index()
    STOCK_NAME_LOOKUP = rebuild_stock_name_lookup(STOCK_INDEX)


def issue_access_token() -> str:
    # 파일에서 캐시된 토큰 로드
    cached_token, cached_timestamp = load_token_cache()
    
    # 캐시된 토큰이 있고 유효기간 내라면 재사용
    if cached_token and cached_timestamp and is_token_valid(cached_timestamp):
        TOKEN_CACHE["access_token"] = cached_token
        return cached_token

    # 새로운 토큰 발급 필요
    validate_settings()
    url = f"{settings.kis_base_url}/oauth2/tokenP"
    payload = {
        "grant_type": "client_credentials",
        "appkey": settings.kis_app_key,
        "appsecret": settings.kis_app_secret,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"KIS 토큰 발급 요청에 실패했습니다: {exc}") from exc

    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail=f"KIS 토큰 발급 응답이 올바르지 않습니다: {data}")

    # 새로운 토큰을 파일과 메모리에 저장
    current_timestamp = datetime.datetime.now().timestamp()
    save_token_cache(access_token, current_timestamp)
    TOKEN_CACHE["access_token"] = access_token
    return access_token


def get_current_price(symbol: str) -> dict[str, Any]:
    access_token = issue_access_token()
    url = f"{settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": settings.kis_app_key,
        "appsecret": settings.kis_app_secret,
        "tr_id": "FHKST01010100",
    }
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": symbol,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"KIS 현재가 조회 요청에 실패했습니다: {exc}") from exc

    data = response.json()
    output = data.get("output") or {}
    stock_name = output.get("hts_kor_isnm") or output.get("bstp_kor_isnm") or ""
    
    # 안전하게 시가와 종가 파싱
    try:
        open_price = parse_int(output.get("stck_oprc"))
    except (KeyError, ValueError, TypeError):
        open_price = 0
    
    try:
        current_price = parse_int(output.get("stck_prpr"))
    except (KeyError, ValueError, TypeError):
        current_price = 0

    if current_price == 0:
        raise HTTPException(status_code=502, detail=f"KIS 현재가 응답이 올바르지 않습니다: {data}")

    return {
        "symbol": symbol,
        "name": stock_name,
        "current_price": current_price,
        "open_price": open_price,
    }


def search_stocks_by_name(name: str) -> list[dict[str, str]]:
    keyword = name.strip().lower()
    if not keyword:
        return []

    exact_matches = STOCK_NAME_LOOKUP.get(keyword, [])
    if exact_matches:
        return exact_matches[:20]

    partial_matches = [stock for stock in STOCK_INDEX if keyword in stock["name"].lower()]
    return partial_matches[:20]


def parse_investor_rows(data: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    candidate_rows = data.get("output2") or data.get("output1") or data.get("output") or []
    if isinstance(candidate_rows, dict):
        candidate_rows = [candidate_rows]

    result: list[dict[str, Any]] = []
    for row in candidate_rows:
        if not isinstance(row, dict):
            continue
        date = (
            row.get("stck_bsop_date")
            or row.get("bsop_date")
            or row.get("date")
            or row.get("trad_dt")
            or row.get("trade_date")
            or ""
        )
        if not date:
            continue
        
        # 종가 파싱: stck_clpr 우선, 없으면 stck_prpr 사용
        try:
            close_price = parse_int(
                row.get("stck_clpr") or row.get("stck_prpr") or 0
            )
        except (KeyError, ValueError, TypeError):
            close_price = 0
        
        # 시가 파싱: stck_oprc, 없으면 0으로 처리
        try:
            open_price = parse_int(row.get("stck_oprc") or 0)
        except (KeyError, ValueError, TypeError):
            open_price = 0
        
        result.append(
            {
                "date": str(date),
                "symbol": symbol,
                "open_price": open_price,
                "close_price": close_price,
                "personal_net_buy": parse_int(
                    row.get("prsn_ntby_qty") or row.get("indi_ntby_qty") or row.get("personal_net_buy") or 0
                ),
                "foreign_net_buy": parse_int(
                    row.get("frgn_ntby_qty") or row.get("frgnr_ntby_qty") or row.get("foreign_net_buy") or 0
                ),
                "institution_net_buy": parse_int(
                    row.get("orgn_ntby_qty") or row.get("org_ntby_qty") or row.get("institution_net_buy") or 0
                ),
                "volume": parse_int(
                    row.get("acml_vol") or row.get("trade_volume") or row.get("volume") or row.get("sum_vol") or 0
                ),
            }
        )
    return result


def get_investor_trend(symbol: str) -> dict[str, Any]:
    access_token = issue_access_token()
    candidates = [
        {
            "url": f"{settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-investor",
            "tr_id": "FHKST01010900",
            "params": {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": symbol,
            },
        },
        {
            "url": f"{settings.kis_base_url}/uapi/domestic-stock/v1/quotations/foreign-institution-total",
            "tr_id": "FHPTJ04400000",
            "params": {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": symbol,
            },
        },
    ]
    last_error: Any = None

    for candidate in candidates:
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "tr_id": candidate["tr_id"],
        }
        try:
            response = requests.get(candidate["url"], headers=headers, params=candidate["params"], timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            last_error = str(exc)
            continue

        trends = parse_investor_rows(data, symbol)
        if trends:
            return {
                "symbol": symbol,
                "data": trends,
            }
        last_error = data

    raise HTTPException(status_code=502, detail=f"KIS 투자자 동향 응답을 해석하지 못했습니다: {last_error}")


def get_investor_intraday(symbol: str) -> dict[str, Any]:
    access_token = issue_access_token()
    url = f"{settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-investor-time-itemchartprice"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": settings.kis_app_key,
        "appsecret": settings.kis_app_secret,
        "tr_id": "FHKST01010600",
    }
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": symbol,
        "fid_input_hour_1": "090000",
        "fid_pw_data_incu_yn": "Y",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"KIS 시간대별 투자자 동향 요청에 실패했습니다: {exc}") from exc

    candidate_rows = data.get("output2") or data.get("output1") or data.get("output") or []
    if isinstance(candidate_rows, dict):
        candidate_rows = [candidate_rows]

    raw_rows: list[dict[str, Any]] = []
    for row in candidate_rows:
        if not isinstance(row, dict):
            continue
        time_val = (
            row.get("stck_cntg_hour")
            or row.get("bsop_hour")
            or row.get("hour")
            or ""
        )
        if not time_val:
            continue

        time_str = str(time_val).strip()
        if len(time_str) >= 4:
            formatted_time = f"{time_str[:2]}:{time_str[2:4]}"
        else:
            formatted_time = time_str

        try:
            personal = parse_int(
                row.get("prsn_ntby_qty") or row.get("indi_ntby_qty") or 0
            )
        except (KeyError, ValueError, TypeError):
            personal = 0

        try:
            foreign = parse_int(
                row.get("frgn_ntby_qty") or row.get("frgnr_ntby_qty") or 0
            )
        except (KeyError, ValueError, TypeError):
            foreign = 0

        try:
            institution = parse_int(
                row.get("orgn_ntby_qty") or row.get("org_ntby_qty") or 0
            )
        except (KeyError, ValueError, TypeError):
            institution = 0

        raw_rows.append({
            "time": formatted_time,
            "personal_net_buy": personal,
            "foreign_net_buy": foreign,
            "institution_net_buy": institution,
        })

    if not raw_rows:
        raise HTTPException(status_code=502, detail=f"KIS 시간대별 투자자 동향 응답을 해석하지 못했습니다: {data}")

    # 시간순 정렬 (과거 → 최신)
    raw_rows.reverse()

    # 누적합(Cumulative Sum) 계산
    cum_personal = 0
    cum_foreign = 0
    cum_institution = 0
    result: list[dict[str, Any]] = []
    for row in raw_rows:
        cum_personal += row["personal_net_buy"]
        cum_foreign += row["foreign_net_buy"]
        cum_institution += row["institution_net_buy"]
        result.append({
            "time": row["time"],
            "personal_net_buy": cum_personal,
            "foreign_net_buy": cum_foreign,
            "institution_net_buy": cum_institution,
        })

    return {
        "symbol": symbol,
        "data": result,
    }


@app.on_event("startup")
def on_startup() -> None:
    initialize_stock_data()


@app.get("/")
def read_index() -> FileResponse:
    return FileResponse(INDEX_FILE)


@app.get("/api/token")
def read_access_token() -> dict[str, str]:
    return {"access_token": issue_access_token()}


@app.get("/api/quote")
def read_quote(symbol: str = Query(..., min_length=1, max_length=12)) -> dict[str, Any]:
    try:
        return get_current_price(symbol)
    except HTTPException as e:
        # API 실패 시 기본 데이터 반환
        return {
            "symbol": symbol,
            "name": "데이터 없음",
            "current_price": 0,
            "open_price": 0,
        }


@app.get("/api/stocks/search")
def read_stock_search(name: str = Query(..., min_length=1, max_length=50)) -> dict[str, Any]:
    matches = search_stocks_by_name(name)
    if not matches:
        raise HTTPException(status_code=404, detail="일치하는 종목명을 찾지 못했습니다.")
    return {
        "query": name,
        "count": len(matches),
        "items": matches,
    }


@app.get("/api/investor-trend")
def read_investor_trend(symbol: str = Query(..., min_length=6, max_length=6)) -> dict[str, Any]:
    try:
        return get_investor_trend(symbol)
    except HTTPException as e:
        # API 실패 시 기본 데이터 반환
        import datetime
        sample_data = []
        for i in range(10):
            date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            sample_data.append({
                "date": date.replace("-", ""),
                "symbol": symbol,
                "open_price": 0,
                "close_price": 0,
                "personal_net_buy": 0,
                "foreign_net_buy": 0,
                "institution_net_buy": 0,
                "volume": 0
            })
        return {
            "symbol": symbol,
            "data": sample_data,
        }


@app.get("/api/investor-intraday")
def read_investor_intraday(symbol: str = Query(..., min_length=6, max_length=6)) -> dict[str, Any]:
    try:
        return get_investor_intraday(symbol)
    except HTTPException:
        # API 실패 시 테스트용 누적 더미 데이터 반환
        import random
        mock_data = []
        hours = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
                 "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30"]
        cum_personal = 0
        cum_foreign = 0
        cum_institution = 0
        for t in hours:
            cum_personal += random.randint(-500, 800)
            cum_foreign += random.randint(-600, 700)
            cum_institution += random.randint(-400, 600)
            mock_data.append({
                "time": t,
                "personal_net_buy": cum_personal,
                "foreign_net_buy": cum_foreign,
                "institution_net_buy": cum_institution,
            })
        return {
            "symbol": symbol,
            "data": mock_data,
        }
