"""Fast TWSE ETF crawler - fetches only unique stocks, parallel, reuses existing data"""
import os, json, sys, time, concurrent.futures
from datetime import datetime

import yfinance as yf

DATA_DIR = r"D:\Data\TWSE\yfinance"
os.makedirs(DATA_DIR, exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etf_holdings import ETF_HOLDINGS, unique_stocks

def fetch_stock(tw_code):
    """Fetch a single Taiwan stock via yfinance."""
    ticker = f"{tw_code}.TW"
    try:
        t = yf.Ticker(ticker)
        info = t.info
        result = {
            "code": tw_code,
            "name": info.get("longName", info.get("shortName", "")),
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
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "currency": info.get("currency", "TWD"),
            "timestamp": datetime.now().isoformat(),
        }
        return tw_code, result, None
    except Exception as e:
        return tw_code, None, str(e)[:100]

def run():
    # Get all unique stocks
    all_stocks = unique_stocks()
    print(f"Unique stocks to fetch: {len(all_stocks)}", flush=True)
    
    # Check existing data in any ETF dir
    existing = {}
    for ed in sorted(os.listdir(DATA_DIR)):
        if ed.startswith('_') or ed.startswith('.'): continue
        mp = os.path.join(DATA_DIR, ed, "meta.json")
        if os.path.isfile(mp):
            with open(mp, encoding="utf-8") as f:
                meta = json.load(f)
            for s in meta.get("stocks", []):
                sp = os.path.join(DATA_DIR, ed, f"{s}.json")
                if os.path.isfile(sp) and s not in existing:
                    existing[s] = True
    
    # Filter stocks we need to fetch
    to_fetch = [s for s in all_stocks if s not in existing]
    print(f"Already cached: {len(existing)}", flush=True)
    print(f"Need to fetch: {len(to_fetch)}", flush=True)
    
    if to_fetch:
        # Use ThreadPoolExecutor for parallel fetches
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            fut_map = {ex.submit(fetch_stock, s): s for s in to_fetch}
            for i, fut in enumerate(concurrent.futures.as_completed(fut_map), 1):
                code, data, err = fut.result()
                if data:
                    results[code] = data
                else:
                    results[code] = {"code": code, "error": err}
                if i % 10 == 0 or i == len(to_fetch):
                    print(f"  [{i}/{len(to_fetch)}] {code}", flush=True)
                time.sleep(0.15)  # mild throttle
        
        errors = [(c, results[c].get("error","")) for c in results if "error" in results[c]]
        if errors:
            print(f"Errors: {len(errors)}", flush=True)
            for c, e in errors[:5]:
                print(f"  {c}: {e}", flush=True)
    else:
        results = {}
        errors = []
    
    # Write data per ETF directory
    etf_reports = []
    for etf_code, etf_info in ETF_HOLDINGS.items():
        name = etf_info["name"]
        stocks = etf_info["stocks"]
        etf_dir = os.path.join(DATA_DIR, etf_code)
        os.makedirs(etf_dir, exist_ok=True)
        
        ok_count = 0
        for s in stocks:
            if s in results:
                data = results[s]
            else:
                # Use existing data
                found = False
                for ed in os.listdir(DATA_DIR):
                    if ed.startswith('_'): continue
                    sp = os.path.join(DATA_DIR, ed, f"{s}.json")
                    if os.path.isfile(sp):
                        with open(sp, encoding="utf-8") as f:
                            data = json.load(f)
                        found = True
                        break
                if not found:
                    data = {"code": s, "error": "no data"}
            
            # Write stock data
            with open(os.path.join(etf_dir, f"{s}.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            
            if "error" not in data:
                ok_count += 1
        
        meta = {
            "etf_code": etf_code, "etf_name": name,
            "total": len(stocks), "success": ok_count,
            "stocks": list(stocks),
            "crawled_at": datetime.now().isoformat(),
        }
        with open(os.path.join(etf_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        
        etf_reports.append(f"  {etf_code} {name}: {ok_count}/{len(stocks)} OK")
    
    # Save summary
    grand_total = sum(len(v["stocks"]) for v in ETF_HOLDINGS.values())
    summary = {
        "crawled_at": datetime.now().isoformat(),
        "total_stocks": grand_total,
        "etfs": {k: {"name": ETF_HOLDINGS[k]["name"], "total": len(ETF_HOLDINGS[k]["stocks"])}
                 for k in ETF_HOLDINGS},
    }
    with open(os.path.join(DATA_DIR, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    # Report
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    report = [f"TWSE ETF 成分股財報更新 ({date_str})", f"   總計: {grand_total} 檔股票", "", *etf_reports]
    if errors:
        report.append("")
        report.append(f"  錯誤 {len(errors)} 筆:")
        for e in errors[:5]:
            report.append(f"    {e[0]}: {e[1]}")
    print("\n".join(report))

if __name__ == "__main__":
    run()
