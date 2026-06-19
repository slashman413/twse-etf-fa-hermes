"""TWSE/TPEx 股票中文名查詢模組

從官方 API 取得股票中文名稱：
- TWSE API: 上市股票 (code 不含 O 後綴)
- TPEx API: 上櫃股票 (code 含 O 後綴，去 O 查詢)

使用方式:
    from chinese_names import get_names
    names = get_names()  # {"2330": "台積電", "5274O": "信驊", ...}
"""
import json, os, time
from urllib.request import urlopen, Request

CACHE_FILE = os.path.join(os.path.dirname(__file__), "stock_names_cn.json")


def _fetch_json(url, retries=3):
    """Fetch JSON from URL with retries."""
    for i in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)
    return {}


def fetch_twse_names():
    """Fetch listed stock Chinese names from TWSE API."""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        data = _fetch_json(url)
        return {d["Code"]: d["Name"] for d in data}
    except Exception as e:
        print(f"  [WARN] TWSE API failed: {e}", flush=True)
        return {}


def fetch_tpex_names():
    """Fetch 上櫃 stock Chinese names from TPEx API.
    
    TPEx returns base codes (without O suffix). We add O suffix back
    so the result dict uses the same format as our holding lists.
    """
    # Use the most recent trading day - try today, then go back up to 7 days
    from datetime import datetime, timedelta
    today = datetime.now()
    for delta in range(14):
        d = today - timedelta(days=delta)
        date_str = d.strftime("%Y/%m/%d")
        url = (
            f"https://www.tpex.org.tw/web/stock/aftertrading/"
            f"otc_quotes_no1430/stk_wn1430_result.php"
            f"?l=zh-tw&d={date_str}&se=EW&page=1"
        )
        try:
            resp = _fetch_json(url)
            tables = resp.get("tables", [{}])[0]
            rows = tables.get("data", [])
            if rows:
                result = {}
                for row in rows:
                    base_code = row[0].strip()
                    name = row[1].strip()
                    # Skip non-stock entries (ETF, warrants, etc.)
                    if not base_code.isdigit() or len(base_code) > 6:
                        continue
                    result[base_code] = name
                return result
        except Exception:
            continue
    print("  [WARN] TPEx API failed: no trading day data found in last 14 days", flush=True)
    return {}


def get_names(force_refresh=False):
    """Return {stock_code: chinese_name} for all TWSE + TPEx stocks.
    
    Caches result in stock_names_cn.json. Use force_refresh=True to refetch.
    Stock codes with O suffix are stored with O (e.g., "5274O": "信驊").
    """
    if not force_refresh and os.path.isfile(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    
    print("  Fetching Chinese names from TWSE/TPEx API...", flush=True)
    
    # TWSE listed stocks
    twse = fetch_twse_names()
    # TPEx 上櫃 stocks (add O suffix)
    tpex = fetch_tpex_names()
    
    # Merge: TWSE codes as-is, TPEx codes with O suffix
    result = {}
    result.update(twse)
    for base_code, name in tpex.items():
        result[f"{base_code}O"] = name
    
    # Save cache
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [WARN] Failed to cache Chinese names: {e}", flush=True)
    
    print(f"  Loaded {len(result)} Chinese names ({len(twse)} TWSE + {len(tpex)} TPEx)", flush=True)
    return result


if __name__ == "__main__":
    names = get_names(force_refresh=True)
    for code in ["2330", "2454", "2317", "5274O", "8299O", "2881"]:
        print(f"  {code}: {names.get(code, 'N/A')}")
