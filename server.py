"""TWSE-FA Dashboard Server
- Static files (dashboard.html, etc.)
- API: /api/history?code=2330&period=6mo => OHLCV data
"""
import os, json, sys, socket, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, date

HISTORY_DIR = r"D:\Data\TWSE\history"
os.makedirs(HISTORY_DIR, exist_ok=True)

class TWSEHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/history":
            params = parse_qs(parsed.query)
            code = (params.get("code") or [""])[0].strip()
            period = (params.get("period") or ["1y"])[0]
            if not code:
                self.send_json({"error": "missing code"}, 400)
                return
            data = self._get_history(code, period)
            self.send_json(data)
            return
        # Force UTF-8 for .html files
        if self.path.endswith(".html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            with open(self.translate_path(self.path), "rb") as f:
                content = f.read()
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        super().do_GET()

    def _get_history(self, code, period="1y"):
        """Fetch OHLCV from yfinance cache or live API"""
        cache_path = os.path.join(HISTORY_DIR, f"{code}.json")
        # Check daily cache
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cached = json.load(f)
                # Use cache if it has data for requested period
                if cached.get("period") == period and cached.get("ohlcv"):
                    return cached
            except: pass
        # Fetch from yfinance
        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{code}.TW")
            df = ticker.history(period=period)
            if df.empty:
                ticker = yf.Ticker(f"{code}.TWO")
                df = ticker.history(period=period)
            if df.empty:
                return {"code": code, "error": "no data", "ohlcv": []}
            records = []
            for idx, row in df.iterrows():
                records.append({
                    "t": idx.strftime("%Y-%m-%d"),
                    "o": round(float(row["Open"]), 2),
                    "h": round(float(row["High"]), 2),
                    "l": round(float(row["Low"]), 2),
                    "c": round(float(row["Close"]), 2),
                    "v": int(row["Volume"]),
                })
            result = {"code": code, "period": period, "ohlcv": records}
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
            return result
        except Exception as e:
            return {"code": code, "error": str(e)[:200], "ohlcv": []}

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if args and "api/" in str(args[0]):
            super().log_message(fmt, *args)

def find_free_port(start=8080, max_try=10):
    for port in range(start, start + max_try):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("0.0.0.0", port))
            s.close()
            return port
        except: s.close()
    return start

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else find_free_port()
    server = HTTPServer(("0.0.0.0", port), TWSEHandler)
    print(f"TWSE Server on 0.0.0.0:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
