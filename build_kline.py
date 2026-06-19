"""Fetch K-line (candlestick) data for ETF holdings via yfinance.
Saves as compact JSON for static serving on GitHub Pages.

Output: {data_dir}/kline_data.json
Format: {stock_code: {t: [timestamps], o: [open], h: [high], l: [low], c: [close], v: [volume]}}
"""
import os, sys, json, time, concurrent.futures
from datetime import datetime, timedelta

import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("TWSE_DATA_DIR", "")
if not DATA_DIR or not os.path.isdir(DATA_DIR):
    fallback = r"D:\Data\TWSE\yfinance"
    DATA_DIR = fallback if os.path.isdir(fallback) else os.path.join(BASE_DIR, "data")

sys.path.insert(0, BASE_DIR)
from etf_holdings import ETF_HOLDINGS, unique_stocks

PERIOD = "6mo"   # fetch ~180 trading days
OUTPUT_FILE = os.path.join(DATA_DIR, "kline_data.json")


def fetch_kline(code):
    """Fetch daily OHLCV for a single stock code. Returns (code, data_dict) or (code, None)."""
    if code.endswith('O'):
        base = code[:-1]
        suffix = '.TWO'
    else:
        base = code
        suffix = '.TW'
    ticker = f"{base}{suffix}"

    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=PERIOD)
        if hist.empty:
            return code, None
        result = {
            "t": [int(d.timestamp()) for d in hist.index],
            "o": [round(float(hist['Open'][d]), 2) for d in hist.index],
            "h": [round(float(hist['High'][d]), 2) for d in hist.index],
            "l": [round(float(hist['Low'][d]), 2) for d in hist.index],
            "c": [round(float(hist['Close'][d]), 2) for d in hist.index],
            "v": [int(float(hist['Volume'][d])) for d in hist.index],
        }
        # Clean any NaN
        clean = {}
        for key, arr in result.items():
            clean[key] = [0 if (v != v) else v for v in arr]  # NaN check
        return code, clean
    except Exception as e:
        return code, None


def main():
    codes = unique_stocks()
    print(f"Fetching K-line for {len(codes)} stocks (period={PERIOD})...", flush=True)

    all_data = {}
    ok = 0
    errors = 0
    batch_size = 8  # parallel workers

    with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as ex:
        fut_map = {ex.submit(fetch_kline, c): c for c in codes}
        done = 0
        for fut in concurrent.futures.as_completed(fut_map):
            code, data = fut.result()
            done += 1
            if data:
                all_data[code] = data
                ok += 1
            else:
                errors += 1
            if done % 50 == 0 or done == len(codes):
                print(f"  [{done}/{len(codes)}] OK={ok} Err={errors}", flush=True)
            time.sleep(0.05)

    # Save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False)
    size_mb = os.path.getsize(OUTPUT_FILE) / 1_000_000

    print(f"\nK-line saved: {ok}/{len(codes)} stocks, {size_mb:.1f}MB", flush=True)
    return all_data


if __name__ == "__main__":
    main()
