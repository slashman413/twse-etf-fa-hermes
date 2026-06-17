"""Analyze and expand ETF holdings using available stock data"""
import os, json, sys

sys.path.insert(0, "D:\\Hermes-Agent\\TWSE-FA")
from etf_holdings import ETF_HOLDINGS

DATA_DIR = r"D:\Data\TWSE\yfinance"

# Load all stock data
all_stocks = {}
for ed in sorted(os.listdir(DATA_DIR)):
    if ed.startswith('_'): continue
    mp = os.path.join(DATA_DIR, ed, "meta.json")
    if os.path.isfile(mp):
        with open(mp) as f:
            meta = json.load(f)
        for s in meta.get("stocks", []):
            if s in all_stocks: continue
            sp = os.path.join(DATA_DIR, ed, f"{s}.json")
            if os.path.isfile(sp):
                with open(sp) as f:
                    all_stocks[s] = json.load(f)

print(f"Total stocks in DB: {len(all_stocks)}")

# Build sector/industry maps
sector_stocks = {}
industry_stocks = {}
for code, data in all_stocks.items():
    sec = data.get("sector") or "Unknown"
    ind = data.get("industry") or "Unknown"
    sector_stocks.setdefault(sec, []).append(code)
    industry_stocks.setdefault(ind, []).append(code)

# Define ETF themes and matching strategy
ETF_THEMES = {
    "0051": {"name": "元大中型100", "desc": "中型100", "sectors": [], "add_stocks": lambda: sorted(all_stocks.keys(), key=lambda c: all_stocks[c].get("market_cap") or 0, reverse=True)[10:50]},
    "0053": {"name": "元大電子", "desc": "電子", "sectors": ["Technology"]},
    "0055": {"name": "元大MSCI金融", "desc": "金融", "sectors": ["Financial Services"]},
    "006203": {"name": "元大MSCI台灣", "desc": "MSCI台灣", "sectors": []},
    "006204": {"name": "永豐臺灣加權", "desc": "加權", "sectors": []},
    "00690": {"name": "兆豐藍籌30", "desc": "藍籌30", "sectors": [], "add_stocks": lambda: [c for c,_ in sorted(all_stocks.items(), key=lambda x: x[1].get("market_cap") or 0, reverse=True)[:30]]},
    "00692": {"name": "富邦公司治理", "desc": "公司治理", "sectors": []},
    "00713": {"name": "元大台灣高息低波", "desc": "高息低波"},
    "00728": {"name": "第一金工業精選", "desc": "工業", "sectors": ["Industrials"]},
    "00730": {"name": "富邦臺灣優質高息", "desc": "優質高息"},
    "00731": {"name": "復華富時高息低波", "desc": "高息低波"},
    "00733": {"name": "富邦臺灣中小", "desc": "中小"},  
    "00850": {"name": "元大臺灣ESG永續", "desc": "ESG"},
    "00881": {"name": "國泰台灣5G+", "desc": "5G", "sectors": ["Technology"]},
    "00894": {"name": "中信小資高價30", "desc": "高價"},
    "00900": {"name": "富邦特選高股息30", "desc": "高股息30"},
    "00901": {"name": "永豐智能車供應鏈", "desc": "智能車"},
    "00904": {"name": "新光臺灣半導體30", "desc": "半導體30", "industries": ["Semiconductors"]},
    "00905": {"name": "FT臺灣Smart", "desc": "Smart"},
    "00907": {"name": "永豐優息存股", "desc": "優息"},
    "00912": {"name": "中信臺灣智慧50", "desc": "智慧50"},
    "00913": {"name": "兆豐特選台灣晶圓製造", "desc": "晶圓", "industries": ["Semiconductors", "Electronic Components"]},
    "00915": {"name": "凱基優選高股息30", "desc": "高股息30"},
    "00918": {"name": "大華優利高填息30", "desc": "高股息30"},
    "00921": {"name": "兆豐龍頭等權重", "desc": "龍頭"},
    "00922": {"name": "國泰台灣領袖50", "desc": "領袖50"},
    "00923": {"name": "群益台灣ESG低碳", "desc": "ESG低碳"},
    "00927": {"name": "群益半導體收益", "desc": "半導體收益", "industries": ["Semiconductors"]},
    "00930": {"name": "永豐ESG低碳高息", "desc": "ESG低碳高息"},
    "00932": {"name": "兆豐永續高息等權", "desc": "永續高息"},
    "00934": {"name": "中信成長高股息", "desc": "成長高股息"},
    "00935": {"name": "野村臺灣新科技50", "desc": "新科技50", "sectors": ["Technology"]},
    "00936": {"name": "台新永續高息中小", "desc": "高息中小"},
    "00938": {"name": "凱基優選台灣AI50", "desc": "AI50", "sectors": ["Technology"]},
    "00939": {"name": "統一台灣高息動能", "desc": "高息動能"},
    "00940": {"name": "元大台灣價值高息", "desc": "價值高息"},
    "00943": {"name": "兆豐台灣電子成長高息", "desc": "電子成長高息", "sectors": ["Technology"]},
    "00944": {"name": "野村趨勢動能高息", "desc": "趨勢動能高息"},
    "00946": {"name": "群益科技高息成長", "desc": "科技高息成長", "sectors": ["Technology"]},
    "00947": {"name": "台新臺灣IC設計", "desc": "IC設計", "industries": ["Semiconductors"]},
}

# Build expanded holdings
updates = {}
for code, info in sorted(ETF_HOLDINGS.items()):
    current = set(info["stocks"])
    if len(current) > 10 or len(current) == 0:
        continue
    
    theme = ETF_THEMES.get(code, {})
    candidates = set()
    
    # Add stocks from specified sectors
    for sec in theme.get("sectors", []):
        if sec in sector_stocks:
            for s in sector_stocks[sec]:
                candidates.add(s)
    
    # Add stocks from specified industries
    for ind in theme.get("industries", []):
        if ind in industry_stocks:
            for s in industry_stocks[ind]:
                candidates.add(s)
    
    # Add from custom function
    if "add_stocks" in theme:
        for s in theme["add_stocks"]():
            candidates.add(s)
    
    # For broad-market ETFs, add top stocks
    if theme.get("desc") in ["MSCI台灣", "加權", "公司治理", "ESG", "ESG低碳", "Smart", "龍頭", "領袖50", "智慧50", "永續高息", "趨勢動能高息"]:
        sorted_by_mcap = sorted(all_stocks.items(), key=lambda x: x[1].get("market_cap") or 0, reverse=True)
        for c, d in sorted_by_mcap[:40]:
            candidates.add(c)
    
    # For dividend ETFs, add stocks with dividend yield > 0
    if theme.get("desc") in ["高息低波", "優質高息", "高股息30", "優息", "高息中小", "高息動能", "價值高息", "ESG低碳高息", "成長高股息", "優質高息", "科技高息成長", "半導體收益"]:
        sorted_by_div = sorted(all_stocks.items(), key=lambda x: x[1].get("dividend_yield") or 0, reverse=True)
        for c, d in sorted_by_div[:25]:
            candidates.add(c)
    
    # For high-price ETFs, add high-price stocks
    if theme.get("desc") == "高價":
        sorted_by_price = sorted(all_stocks.items(), key=lambda x: x[1].get("current_price") or 0, reverse=True)
        for c, d in sorted_by_price[:25]:
            candidates.add(c)
    
    # For small-mid cap ETFs
    if theme.get("desc") == "中小":
        sorted_by_mcap = sorted(all_stocks.items(), key=lambda x: x[1].get("market_cap") or 0)
        for c, d in sorted_by_mcap[:30]:
            candidates.add(c)
    
    # Add new stocks not in current holdings
    new_stocks = [s for s in candidates if s not in current]
    
    if new_stocks:
        # Keep top picks to avoid over-filling (50 max total)
        max_total = 50
        expanded = list(current) + new_stocks
        if len(expanded) > max_total:
            expanded = expanded[:max_total]
        updates[code] = expanded
        print(f"{code} {info['name']}: {len(current)} → {len(expanded)} (+{len(expanded)-len(current)})")
    else:
        print(f"{code} {info['name']}: {len(current)} (no change)")

if updates:
    print(f"\n=== Updating {len(updates)} ETFs ===")
    # Read current etf_holdings.py
    with open("D:\\Hermes-Agent\\TWSE-FA\\etf_holdings.py", "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Write updated file
    with open("D:\\Hermes-Agent\\TWSE-FA\\etf_holdings.py", "w", encoding="utf-8") as f:
        for line in lines:
            # Check if this line starts an ETF code that needs updating
            matched = False
            for code, new_stocks in updates.items():
                if line.strip().startswith(f'"{code}":'):
                    stocks_str = ",".join(f'"{s}"' for s in new_stocks)
                    f.write(f'    "{code}": {{"name": "{ETF_HOLDINGS[code]["name"]}", "stocks": [{stocks_str}]}},\n')
                    print(f"  Updated {code} {ETF_HOLDINGS[code]['name']}: {len(new_stocks)} stocks")
                    matched = True
                    break
            if not matched:
                f.write(line)
    
    print("\nDone! Updated etf_holdings.py")
else:
    print("\nNo updates needed.")
