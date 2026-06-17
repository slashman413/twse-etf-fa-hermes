"""Discover and build holdings data for all TWSE stock ETFs"""
import yfinance as yf
import json, os, sys, time

DATA_DIR = r"D:\Data\TWSE\yfinance"
os.makedirs(DATA_DIR, exist_ok=True)

# Comprehensive list of TWSE stock ETFs (equity only - no bond/global/REIT)
STOCK_ETFS = {
    "0050": "元大台灣50",
    "0051": "元大中型100",
    "0052": "富邦科技",
    "0053": "元大電子",
    "0055": "元大MSCI金融",
    "0056": "元大高股息",
    "006201": "元大富櫃50",
    "006203": "元大MSCI台灣",
    "006204": "永豐臺灣加權",
    "006208": "富邦台50",
    "00690": "兆豐藍籌30",
    "00692": "富邦公司治理",
    "00713": "元大台灣高息低波",
    "00728": "第一金工業精選",
    "00730": "富邦臺灣優質高息",
    "00731": "復華富時高息低波",
    "00733": "富邦臺灣中小",
    "00850": "元大臺灣ESG永續",
    "00878": "國泰永續高股息",
    "00881": "國泰台灣5G+",
    "00888": "永豐台灣ESG",
    "00894": "中信小資高價30",
    "00900": "富邦特選高股息30",
    "00901": "永豐智能車供應鏈",
    "00904": "新光臺灣半導體30",
    "00905": "FT臺灣Smart",
    "00907": "永豐優息存股",
    "00912": "中信臺灣智慧50",
    "00913": "兆豐特選台灣晶圓製造",
    "00915": "凱基優選高股息30",
    "00918": "大華優利高填息30",
    "00919": "群益台灣精選高息",
    "00921": "兆豐龍頭等權重",
    "00922": "國泰台灣領袖50",
    "00923": "群益台灣ESG低碳",
    "00927": "群益半導體收益",
    "00928": "中信上櫃ESG30",
    "00929": "復華台灣科技優息",
    "00930": "永豐ESG低碳高息",
    "00932": "兆豐永續高息等權",
    "00934": "中信成長高股息",
    "00935": "野村臺灣新科技50",
    "00936": "台新永續高息中小",
    "00938": "凱基優選台灣AI50",
    "00939": "統一台灣高息動能",
    "00940": "元大台灣價值高息",
    "00943": "兆豐台灣電子成長高息",
    "00944": "野村趨勢動能高息",
    "00946": "群益科技高息成長",
    "00947": "台新臺灣IC設計",
}

def get_top_holdings(code):
    """Get top holdings from yfinance, returns list of stock codes (without .TW)"""
    try:
        t = yf.Ticker(f"{code}.TW")
        fd = t.funds_data
        th = fd.top_holdings
        if th is not None and not th.empty:
            return [s.replace(".TW", "") for s in list(th.index)]
    except:
        pass
    return []

def get_sector_weightings(code):
    """Get sector weightings from yfinance"""
    try:
        t = yf.Ticker(f"{code}.TW")
        sw = t.funds_data.sector_weightings
        if sw:
            return {k: round(float(v)*100, 1) for k, v in sw.items() if v and float(v) > 0}
    except:
        pass
    return {}

# Load existing known holdings
EXISTING_FILE = os.path.join(os.path.dirname(__file__), "etf_holdings.py")
known_holdings = {}
if os.path.isfile(EXISTING_FILE):
    import importlib.util
    spec = importlib.util.spec_from_file_location("etf_holdings", EXISTING_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    known_holdings = {k: v["stocks"] for k, v in mod.ETF_HOLDINGS.items()}

# Build the combined holdings
combined = {}
for code, name in STOCK_ETFS.items():
    # Use known holdings if available (more complete)
    if code in known_holdings:
        holdings = known_holdings[code]
        print(f"  {code} {name}: {len(holdings)} known holdings")
    else:
        # Get top holdings from yfinance
        holdings = get_top_holdings(code)
        if holdings:
            print(f"  {code} {name}: {len(holdings)} yfinance holdings")
        else:
            print(f"  {code} {name}: NO holdings found")
    combined[code] = {"name": name, "stocks": holdings}

# Save the result
output_path = r"D:\Hermes-Agent\TWSE-FA\etf_holdings_expanded.py"
with open(output_path, "w", encoding="utf-8") as f:
    f.write('"""TWSE ETF 成分股清單（自動擴充版）"""\n')
    f.write("ETF_HOLDINGS = {\n")
    for code, info in sorted(combined.items()):
        stocks_str = ",".join(f'"{s}"' for s in info["stocks"])
        f.write(f'    "{code}": {{"name": "{info["name"]}", "stocks": [{stocks_str}]}},\n')
    f.write("}\n\n")
    f.write("def unique_stocks():\n")
    f.write('    """回傳所有 ETF 去重後的成分股代碼清單"""\n')
    f.write("    seen = set()\n")
    f.write("    for v in ETF_HOLDINGS.values():\n")
    f.write("        for s in v['stocks']:\n")
    f.write("            seen.add(s)\n")
    f.write("    return sorted(seen)\n")
    f.write("\ndef stocks_by_etf():\n")
    f.write('    """回傳 {etf_code: [stock_codes]}"""\n')
    f.write("    return {k: v['stocks'] for k, v in ETF_HOLDINGS.items()}\n")
    f.write("\ndef etf_names():\n")
    f.write('    """回傳 {etf_code: name}"""\n')
    f.write("    return {k: v['name'] for k, v in ETF_HOLDINGS.items()}\n")

print(f"\nSaved to {output_path}")
total_stocks = sum(len(v["stocks"]) for v in combined.values())
etf_with_data = sum(1 for v in combined.values() if v["stocks"])
print(f"ETFs: {len(combined)} total, {etf_with_data} with holdings, {total_stocks} total stock entries")
