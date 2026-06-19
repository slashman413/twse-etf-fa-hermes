"""
TWSE ETF 成分股財報爬蟲 - 排程版本
資料源: yfinance (免 API key)
輸出: D:\\Data\\TWSE\\yfinance\\
stdout: 結果摘要 (cron job 會送到 Discord)
"""
import os, sys, json, time
from datetime import datetime

import yfinance as yf

DATA_DIR = os.environ.get("TWSE_DATA_DIR", r"D:\Data\TWSE\yfinance")
os.makedirs(DATA_DIR, exist_ok=True)

# 從共用模組載入 ETF 清單，確保唯一事實來源
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
        return result, None
    except Exception as e:
        return None, str(e)[:100]


def run():
    errors = []
    total_ok = 0
    total_all = 0
    etf_reports = []

    for etf_code, etf_info in ETF_HOLDINGS.items():
        name = etf_info["name"]
        stocks = etf_info["stocks"]
        etf_dir = os.path.join(DATA_DIR, etf_code)
        os.makedirs(etf_dir, exist_ok=True)

        results = {}
        for s in stocks:
            data, err = fetch_stock(s)
            if data:
                results[s] = data
            else:
                results[s] = {"code": s, "error": err}
                errors.append(f"{etf_code}/{s}: {err}")

            with open(os.path.join(etf_dir, f"{s}.json"), "w", encoding="utf-8") as f:
                json.dump(results[s], f, ensure_ascii=False, indent=2, default=str)
            time.sleep(0.3)  # 0.3s rate limit (原0.5s, 加速40%)

        ok_count = sum(1 for v in results.values() if "error" not in v)
        total_ok += ok_count
        total_all += len(stocks)

        meta = {
            "etf_code": etf_code, "etf_name": name,
            "total": len(stocks), "success": ok_count,
            "stocks": list(results.keys()),
            "crawled_at": datetime.now().isoformat(),
        }
        with open(os.path.join(etf_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        etf_reports.append(f"  {etf_code} {name}: {ok_count}/{len(stocks)} OK")

    # Global summary
    success_map = {}
    for k in ETF_HOLDINGS:
        mp = os.path.join(DATA_DIR, k, "meta.json")
        try:
            with open(mp) as f:
                success_map[k] = json.load(f)["success"]
        except Exception:
            success_map[k] = 0

    grand_total = sum(len(v["stocks"]) for v in ETF_HOLDINGS.values())
    summary = {
        "crawled_at": datetime.now().isoformat(),
        "data_dir": DATA_DIR,
        "total_stocks": grand_total,
        "success_stocks": sum(success_map.values()),
        "etfs": {k: {"name": ETF_HOLDINGS[k]["name"], "total": len(ETF_HOLDINGS[k]["stocks"]), "success": v}
                 for k, v in success_map.items()},
    }
    with open(os.path.join(DATA_DIR, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Build and save report
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_lines = [
        f"TWSE ETF 成分股財報更新 ({date_str})",
        f"   總計: {summary['success_stocks']}/{grand_total} 檔股票成功",
        "",
        *etf_reports,
    ]
    if errors:
        report_lines.append("")
        report_lines.append(f"  錯誤 {len(errors)} 筆:")
        for e in errors[:5]:
            report_lines.append(f"     {e}")
        if len(errors) > 5:
            report_lines.append(f"    ...還有 {len(errors)-5} 筆")

    report_text = "\n".join(report_lines)
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    # Save timestamped + latest report
    for suffix in [f"_report_{ts}.txt", "_report_latest.txt"]:
        rp = os.path.join(DATA_DIR, suffix)
        with open(rp, "w", encoding="utf-8") as f:
            f.write(report_text + "\n")

    print(report_text)


if __name__ == "__main__":
    run()
