"""Nightly ETF data updater - refreshes stock data, rebuilds dashboard."""
import os, json, sys, time, concurrent.futures
from datetime import datetime, timedelta

import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("TWSE_DATA_DIR", "")
if not DATA_DIR or not os.path.isdir(DATA_DIR):
    # Fallback: check if the established data dir exists
    fallback = r"D:\Data\TWSE\yfinance"
    if os.path.isdir(fallback):
        DATA_DIR = fallback
    else:
        DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)
from etf_holdings import ETF_HOLDINGS, unique_stocks
from chinese_names import get_names

STALE_HOURS = 20  # refresh data older than this

CN_NAMES = get_names()

def normalize_dy(raw_dy):
    """yfinance returns dividend_yield inconsistently (decimal vs percentage).
    Return consistent percentage value."""
    if raw_dy is None:
        return None
    if raw_dy > 1.0:
        return round(raw_dy / 100, 2)  # already percentage, divide
    return round(raw_dy * 100, 2)  # decimal → percentage

def fetch_stock(code):
    """Fetch stock data, handling both .TW and .TWO suffixes."""
    # Determine suffix
    if code.endswith('O'):
        base = code[:-1]
        suffix = '.TWO'
    else:
        base = code
        suffix = '.TW'
    
    ticker = f"{base}{suffix}"
    try:
        t = yf.Ticker(ticker)
        info = t.info
        raw_dy = info.get("dividendYield")
        result = {
            "code": code,
            "name": info.get("longName", info.get("shortName", "")),
            "name_cn": CN_NAMES.get(code, ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "market_cap": info.get("marketCap"),
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "price_to_book": info.get("priceToBook"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margins": info.get("profitMargins"),
            "return_on_equity": info.get("returnOnEquity"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_price": info.get("currentPrice", info.get("regularMarketPrice")),
            "dividend_yield": normalize_dy(raw_dy),
            "beta": info.get("beta"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "currency": info.get("currency", "TWD"),
            "timestamp": datetime.now().isoformat(),
        }
        # Clean up None values for numeric fields
        for k in ["market_cap","trailing_pe","forward_pe","price_to_book",
                   "revenue_growth","profit_margins","return_on_equity",
                   "debt_to_equity","current_price","dividend_yield","beta",
                   "52w_high","52w_low"]:
            if result.get(k) is None:
                result[k] = 0
        return code, result, None
    except Exception as e:
        return code, None, str(e)[:100]

def get_all_stock_codes():
    """Get all unique stock codes across all ETFs."""
    codes = set()
    for info in ETF_HOLDINGS.values():
        for s in info["stocks"]:
            codes.add(s)
    return sorted(codes)

def check_stale(codes):
    """Determine which stocks need refreshing.
    Returns (stale_codes, fresh_count)."""
    stale = []
    fresh = 0
    now = datetime.now()
    
    for code in codes:
        # Find the most recent file for this stock
        latest_ts = None
        for ed in sorted(os.listdir(DATA_DIR)):
            if ed.startswith('_'): continue
            fp = os.path.join(DATA_DIR, ed, f"{code}.json")
            if os.path.isfile(fp):
                try:
                    with open(fp, encoding='utf-8') as f:
                        data = json.load(f)
                    ts = data.get("timestamp")
                    if ts:
                        file_dt = datetime.fromisoformat(ts)
                        if latest_ts is None or file_dt > latest_ts:
                            latest_ts = file_dt
                except:
                    pass
        
        if latest_ts is None:
            stale.append(code)  # never fetched
        elif (now - latest_ts) > timedelta(hours=STALE_HOURS):
            stale.append(code)  # stale
        else:
            fresh += 1
    
    return stale, fresh

def main():
    print(f"=== TWSE ETF Nightly Update ===", flush=True)
    start = datetime.now()
    t0 = time.time()
    
    errors = []  # always defined
    
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M')}", flush=True)
    
    all_codes = get_all_stock_codes()
    print(f"Total unique stocks: {len(all_codes)}", flush=True)
    
    # Check which are stale
    stale, fresh = check_stale(all_codes)
    print(f"Fresh: {fresh}, Stale: {len(stale)}", flush=True)
    
    if not stale:
        print("All data is current, skipping fetch.", flush=True)
    else:
        # Fetch stale stocks in parallel (5 workers)
        results = {}
        errors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            fut_map = {ex.submit(fetch_stock, s): s for s in stale}
            done = 0
            for fut in concurrent.futures.as_completed(fut_map):
                code, data, err = fut.result()
                done += 1
                if data:
                    results[code] = data
                else:
                    results[code] = {"code": code, "error": err or "unknown"}
                    errors.append((code, err or "unknown"))
                if done % 10 == 0 or done == len(stale):
                    print(f"  [{done}/{len(stale)}]", flush=True)
                time.sleep(0.1)
        
        print(f"Fetched: {len(results)}, Errors: {len(errors)}", flush=True)
        
        # Write data to ALL ETF directories that contain each stock
        written = 0
        for etf_code, etf_info in ETF_HOLDINGS.items():
            etf_dir = os.path.join(DATA_DIR, etf_code)
            os.makedirs(etf_dir, exist_ok=True)
            
            ok_count = 0
            for s in etf_info["stocks"]:
                fp = os.path.join(etf_dir, f"{s}.json")
                if s in results:
                    data = results[s]
                    if "error" not in data:
                        ok_count += 1
                elif os.path.isfile(fp):
                    data = json.load(open(fp, encoding='utf-8'))
                    if "error" not in data:
                        ok_count += 1
                    continue  # already up to date
                else:
                    data = {"code": s, "error": "no data"}
                
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                written += 1
            
            # Update meta.json
            meta_path = os.path.join(etf_dir, "meta.json")
            meta = {
                "etf_code": etf_code, "etf_name": etf_info["name"],
                "total": len(etf_info["stocks"]), "success": ok_count,
                "stocks": list(etf_info["stocks"]),
                "crawled_at": datetime.now().isoformat(),
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        
        print(f"Updated {written} stock files", flush=True)
    
    # Rebuild dashboard
    print("\nRebuilding dashboard...", flush=True)
    cache_file = os.path.join(DATA_DIR, "_dashboard_cache.json")
    if os.path.isfile(cache_file):
        os.remove(cache_file)
    
    import subprocess
    result = subprocess.run(
        [sys.executable, "build_dashboard.py"],
        cwd=BASE_DIR,
        capture_output=True, text=True, timeout=60
    )
    print(result.stdout.strip(), flush=True)
    if result.stderr:
        print(f"Stderr: {result.stderr.strip()}", flush=True)
    
    # Build K-line data
    print("\nBuilding K-line data...", flush=True)
    result = subprocess.run(
        [sys.executable, "build_kline.py"],
        cwd=BASE_DIR,
        capture_output=True, text=True, timeout=120
    )
    print(result.stdout.strip(), flush=True)
    if result.stderr:
        print(f"Stderr: {result.stderr.strip()}", flush=True)
    
    # Summary
    total_all = sum(len(v["stocks"]) for v in ETF_HOLDINGS.values())
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_lines = [
        f"📊 ETF 夜間更新報告 ({date_str})",
        f"",
        f"  資料庫: {len(ETF_HOLDINGS)} 檔 ETF, {len(all_codes)} 檔成分股",
        f"  更新: {len(stale)} 檔重新抓取, {fresh} 檔資料仍新鮮",
        f"  儀表板: 已重建",
    ]
    if errors:
        report_lines.append(f"  錯誤: {len(errors)} 筆")
        for c, e in errors[:5]:
            report_lines.append(f"    {c}: {e}")
    
    print("\n".join(report_lines), flush=True)
    return report_lines

if __name__ == "__main__":
    main()
