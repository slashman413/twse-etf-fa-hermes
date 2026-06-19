"""
Generate a self-contained TWSE ETF Dashboard HTML (vanilla JS + Chart.js).
Fast mode: skips regeneration if source data unchanged.
"""
import os, json, datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("TWSE_DATA_DIR", "")
if not DATA_DIR or not os.path.isdir(DATA_DIR):
    # Fallback: check if the established data dir exists
    fallback = r"D:\Data\TWSE\yfinance"
    if os.path.isdir(fallback):
        DATA_DIR = fallback
    else:
        DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_FILE = os.environ.get("TWSE_OUTPUT_FILE", os.path.join(BASE_DIR, "dashboard.html"))
CACHE_FILE = os.path.join(DATA_DIR, "_dashboard_cache.json")

# Lazy-load Chinese names for backward compatibility with old data
_CN_NAMES = None
def _get_cn_name(code):
    global _CN_NAMES
    if _CN_NAMES is None:
        try:
            from chinese_names import get_names
            _CN_NAMES = get_names()
        except Exception:
            _CN_NAMES = {}
    return _CN_NAMES.get(code, "")


def get_data_mtime():
    """Latest modification time across all source JSON files (skip cache/output)."""
    latest = 0
    if not os.path.isdir(DATA_DIR):
        return 0
    skip_files = {"_dashboard_cache.json", "_summary.json", "_report_latest.txt"}
    for root, dirs, files in os.walk(DATA_DIR):
        for f in files:
            if f in skip_files or not f.endswith(".json"):
                continue
            mtime = os.path.getmtime(os.path.join(root, f))
            if mtime > latest:
                latest = mtime
    return latest


def load_cache():
    """Load cached dashboard data if valid."""
    if not os.path.isfile(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_cache(data, mtime):
    """Save aggregated data and source mtime to cache."""
    cache = {"mtime": mtime, "data": data}
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def build_data():
    """Load and aggregate all stock/ETF data from JSON files."""
    etfs = {}
    for ed in sorted(os.listdir(DATA_DIR)):
        mp = os.path.join(DATA_DIR, ed, "meta.json")
        if os.path.isfile(mp):
            with open(mp, encoding="utf-8") as f:
                etfs[ed] = json.load(f)

    stocks_data = {}
    for ec, meta in etfs.items():
        for code in meta["stocks"]:
            if code in stocks_data:
                continue  # dedup
            sp = os.path.join(DATA_DIR, ec, f"{code}.json")
            if os.path.isfile(sp):
                with open(sp, encoding="utf-8") as f:
                    raw = json.load(f)
                stocks_data[code] = {k: raw.get(k) for k in [
                    "code", "name", "name_cn", "sector", "industry", "market_cap",
                    "trailing_pe", "forward_pe", "price_to_book",
                    "revenue_growth", "profit_margins", "return_on_equity",
                    "debt_to_equity", "current_price", "dividend_yield",
                    "beta", "52w_high", "52w_low", "currency"
                ]}
                # Fill name_cn if missing (old data compat)
                if not stocks_data[code].get("name_cn"):
                    stocks_data[code]["name_cn"] = _get_cn_name(code)

    return etfs, stocks_data


def median(arr):
    """Calculate median - robust to outliers"""
    if not arr:
        return None
    s = sorted(arr)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2

def compute_stats(etfs, stocks_data):
    """Compute aggregated statistics using median (robust to outliers)."""
    # Sector distribution
    sector_counts = {}
    for s in stocks_data.values():
        sec = s.get("sector") or "\u672a\u77e5"
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
    sectors_sorted = sorted(sector_counts.items(), key=lambda x: -x[1])

    # PE ranking (lowest 30)
    pe_stocks = [(s["code"], s.get("trailing_pe") or 0, s.get("name") or "")
                 for s in stocks_data.values() if s.get("trailing_pe") and s["trailing_pe"] > 0]
    pe_stocks.sort(key=lambda x: x[1])
    pe_top30 = pe_stocks[:30]

    # Top 10 by market cap
    by_mcap = sorted(stocks_data.values(), key=lambda x: x.get("market_cap") or 0, reverse=True)

    # ETF comparison stats - use MEDIAN instead of MEAN
    etf_stats = {}
    for ec, meta in etfs.items():
        sin = [stocks_data[s] for s in meta["stocks"] if s in stocks_data]
        if not sin:
            continue
        vpe = [s["trailing_pe"] for s in sin if s.get("trailing_pe") and s["trailing_pe"] > 0]
        vpb = [s["price_to_book"] for s in sin if s.get("price_to_book") and s["price_to_book"] > 0]
        vdy = [s["dividend_yield"] for s in sin if s.get("dividend_yield") and s["dividend_yield"] > 0]
        vroe = [s["return_on_equity"] for s in sin if s.get("return_on_equity")]
        etf_stats[ec] = {
            "name": meta["etf_name"],
            "count": len(meta["stocks"]),
            "avg_pe": round(median(vpe), 2) if vpe else None,
            "avg_pb": round(median(vpb), 2) if vpb else None,
            "avg_dy": round(median(vdy), 2) if vdy else None,
            "avg_roe": round(median(vroe) * 100, 2) if vroe else None,
            "total_mcap": sum(s.get("market_cap") or 0 for s in sin),
        }

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    return {
        "etfs": {k: {"name": v["etf_name"], "stocks": v["stocks"], "total": v["total"]}
                 for k, v in etfs.items()},
        "stocks": stocks_data,
        "etfStats": etf_stats,
        "sectors": sectors_sorted,
        "peStocks": pe_top30,
        "top10": [{k: s[k] for k in s if k != "financials"} for s in by_mcap[:10]],
        "crawledAt": now_str,
        "etfCodes": list(etfs.keys()),
    }


def generate_html(data_obj):
    """Generate self-contained HTML from aggregated data."""
    data_json = json.dumps(data_obj, ensure_ascii=False)
    return _build_html(data_json)


def _build_html(data_json):
    """Template function: inject dataset into HTML skeleton."""
    jscode = r"""
const DATA = """ + data_json + r""";

const ETF_CODES = DATA.etfCodes;
const S = DATA.stocks, ES = DATA.etfStats, ETFS = DATA.etfs;
const SECTOR_COLORS = {Technology:'#2563eb','Financial Services':'#059669','Consumer Cyclical':'#d97706',Industrials:'#7c3aed','Basic Materials':'#0891b2','Real Estate':'#be185d','Consumer Defensive':'#65a30d','Communication Services':'#ca8a04','Energy':'#dc2626','Healthcare':'#0d9488','Utilities':'#9333ea'};

function fmt(n,d){if(n==null)return'—';if(typeof n!='number')return n;if(n>1e12)return(n/1e12).toFixed(2)+'T';if(n>1e8)return(n/1e8).toFixed(2)+'億';if(n>1e4)return(n/1e4).toFixed(2)+'萬';return Number(n).toFixed(d||2)}
function pct(n){return n!=null?(n*100).toFixed(2)+'%':'—'}
function dy(n){return n!=null?n.toFixed(2)+'%':'—'}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}

let currentTab = 'overview';
let activeTab = ETF_CODES[0];
let searchQuery = '';
let sortCol = null, sortDir = 'asc';
let chartInstances = {};

function sc(s){return SECTOR_COLORS[s]||'#94a3b8'}

function switchTab(tab){
  currentTab = tab;
  searchQuery = ''; sortCol = null; sortDir = 'asc';
  renderApp();
}

function renderApp(){
  const app = document.getElementById('app');
  let h = '<div class="header"><div><h1>TWSE ETF 財務儀表板</h1><div class="meta">'+Object.keys(S).length+' 檔成分股 · '+ETF_CODES.length+' 檔ETF · 更新 '+DATA.crawledAt+'</div></div><span style="font-size:12px;color:#94a3b8">yfinance</span></div>';
  h += '<div class="tab-bar"><button class="tab-btn'+(currentTab==='overview'?' active':'')+'" onclick="switchTab(\'overview\')">📊 總覽</button><button class="tab-btn'+(currentTab==='individual'?' active':'')+'" onclick="switchTab(\'individual\')">📋 個別ETF資訊</button></div>';
  h += '<div id="tabContent">';
  if(currentTab==='overview'){ h += renderOverview(); }
  else { h += renderIndividual(); }
  h += '</div>';
  h += '<div class="footer">資料來源: yfinance · <a href="./privacy.html" style="color:#94a3b8;text-decoration:none">隱私權政策</a></div>';
  app.innerHTML = h;
  app.querySelector('#stockBody')?.addEventListener('click', function(e){
    var tr = e.target.closest('tr[data-code]');
    if(tr) openModal(tr.getAttribute('data-code'));
  });
  app.querySelector('.top10-table tbody')?.addEventListener('click', function(e){
    var tr = e.target.closest('tr');
    if(tr){
      var code = tr.cells[1]?.textContent?.trim();
      if(code) openModal(code);
    }
  });
  renderCharts();
}

function renderOverview(){
  var h = '<div class="chart-box"><h2>前10大市值成分股</h2><table class="top10-table"><thead><tr><th>#</th><th>代碼</th><th>名稱</th><th>市值</th><th>本益比</th><th>股價淨值比</th><th>殖利率</th><th>ROE</th></tr></thead><tbody>';
  DATA.top10.forEach(function(s,i){
    h += '<tr data-code="'+esc(s.code)+'"><td>'+(i+1)+'</td><td style="font-weight:600">'+esc(s.code)+'</td><td>'+esc((s.name_cn||s.name||'').slice(0,20))+'</td><td>'+fmt(s.market_cap)+'</td><td>'+(s.trailing_pe?s.trailing_pe.toFixed(1):'—')+'</td><td>'+(s.price_to_book?s.price_to_book.toFixed(2):'—')+'</td><td style="color:#059669">'+dy(s.dividend_yield)+'</td><td>'+pct(s.return_on_equity)+'</td></tr>';
  });
  h += '</tbody></table></div>';
  h += '<div class="chart-box"><h2>本益比最低30檔</h2><canvas id="peRankChart"></canvas></div>';
  h += '<div class="charts-row"><div class="chart-box"><h2>ETF 平均本益比</h2><canvas id="peChart"></canvas></div><div class="chart-box"><h2>ETF 平均殖利率</h2><canvas id="dyChart"></canvas></div></div>';
  h += '<div class="charts-row"><div class="chart-box"><h2>ETF 平均ROE</h2><canvas id="roeChart"></canvas></div><div class="chart-box"><h2>產業分佈（全市場）</h2><canvas id="sectorChart"></canvas></div></div>';
  return h;
}

function renderIndividual(){
  var s = ES[activeTab] || {};
  // Dropdown first (separate from card)
  var h = '<div style="margin-bottom:16px">';
  h += '<label style="font-size:13px;color:#64748b;margin-right:8px">選擇ETF:</label>';
  h += '<select onchange="selectETF(this.value)" style="padding:8px 14px;border:1px solid #e2e8f0;border-radius:8px;font-size:14px;font-family:inherit;background:#fff;cursor:pointer;outline:none;max-width:100%">';
  ETF_CODES.forEach(function(c){
    h += '<option value="'+esc(c)+'"'+(c===activeTab?' selected':'')+'>'+esc(c)+' '+esc(ES[c]?ES[c].name:'')+'</option>';
  });
  h += '</select></div>';
  // ETF info card
  h += '<div class="etf-card" style="margin-bottom:20px;border-color:#0f172a;border-width:2px">';
  h += '<h3>'+esc(activeTab)+' '+esc(s.name_cn||s.name||'')+'</h3><div class="etf-code">'+(s.count||0)+' 檔成分股</div>';
  h += '<div class="etf-stats">';
  h += '<div class="stat"><div class="stat-label">平均本益比</div><div class="stat-value">'+(s.avg_pe!=null?s.avg_pe:'—')+'</div></div>';
  h += '<div class="stat"><div class="stat-label">平均殖利率</div><div class="stat-value" style="color:#059669">'+(s.avg_dy!=null?Number(s.avg_dy).toFixed(2)+'%':'—')+'</div></div>';
  h += '<div class="stat"><div class="stat-label">平均ROE</div><div class="stat-value">'+(s.avg_roe!=null?s.avg_roe+'%':'—')+'</div></div>';
  h += '<div class="stat"><div class="stat-label">總市值</div><div class="stat-value">'+(s.total_mcap!=null?fmt(s.total_mcap)+'億':'—')+'</div></div>';
  h += '</div></div>';
  h += '<div class="charts-row"><div class="chart-box"><h2>產業分佈 — '+esc(activeTab)+'</h2><canvas id="sectorChart"></canvas></div><div class="chart-box"><h2>ETF 健康分析 — '+esc(activeTab)+'</h2><div id="healthPanel" style="font-size:13px;line-height:1.8"></div></div></div>';
  h += '<div class="chart-box">';
  h += '<h2 id="detailTitle">'+esc(activeTab)+' '+esc(ETFS[activeTab]?ETFS[activeTab].name:'')+' — 成分股明細</h2>';
  h += '<input class="search-bar" id="searchInput" type="text" placeholder="搜尋股號或名稱..." value="'+esc(searchQuery)+'" oninput="onSearch(this.value)">';
  h += '<table class="stock-table"><thead><tr>';
  var cols = ['代碼','名稱','產業','股價','本益比','股價淨值比','ROE','殖利率','Beta'];
  var colKeys = ['code','name','sector','current_price','trailing_pe','price_to_book','return_on_equity','dividend_yield','beta'];
  cols.forEach(function(hdr,i){
    var ck = colKeys[i];
    if(!ck){h += '<th>'+esc(hdr)+'</th>'; return;}
    var arrow = (sortCol===ck?(sortDir==='asc'?' ▲':' ▼'):'');
    h += '<th onclick="sortBy(\''+ck+'\')">'+esc(hdr)+arrow+'</th>';
  });
  h += '</tr></thead><tbody id="stockBody">';
  h += renderStockRows();
  h += '</tbody></table></div>';
  return h;
}

function renderStockRows(){
  var stocks = (ETFS[activeTab]?ETFS[activeTab].stocks:[]).map(function(c){return S[c];}).filter(Boolean);
  if(searchQuery){
    var q = searchQuery.toLowerCase();
    stocks = stocks.filter(function(s){return (s.code&&s.code.indexOf(q)>-1)||((s.name_cn||s.name)&&(s.name_cn||s.name).toLowerCase().indexOf(q)>-1);});
  }
  if(sortCol){
    stocks.sort(function(a,b){
      var va = a[sortCol], vb = b[sortCol];
      if(va==null)va=-Infinity; if(vb==null)vb=-Infinity;
      return sortDir==='asc'?va-vb:vb-va;
    });
  }
  return stocks.map(function(s){
    return '<tr data-code="'+esc(s.code)+'"><td style="font-weight:600">'+esc(s.code)+'</td><td>'+esc((s.name_cn||s.name||'').slice(0,24))+'</td><td>'+esc(s.sector||'')+'</td><td>'+(s.current_price!=null?s.current_price.toFixed(0):'—')+'</td><td>'+(s.trailing_pe!=null?s.trailing_pe.toFixed(1):'—')+'</td><td>'+(s.price_to_book!=null?s.price_to_book.toFixed(2):'—')+'</td><td>'+pct(s.return_on_equity)+'</td><td style="color:#059669">'+dy(s.dividend_yield)+'</td><td>'+(s.beta!=null?s.beta.toFixed(2):'—')+'</td></tr>';
  }).join('');
}

function refreshTable(){
  var body = document.getElementById('stockBody');
  if(body) body.innerHTML = renderStockRows();
  var title = document.getElementById('detailTitle');
  if(title) title.textContent = activeTab+' '+(ETFS[activeTab]?ETFS[activeTab].name:'')+' — 成分股明細';
}

function selectETF(code){
  activeTab = code; searchQuery = ''; sortCol = null; sortDir = 'asc';
  if(currentTab==='overview'){ switchTab('individual'); return; }
  renderApp();
}

function onSearch(val){searchQuery = val; refreshTable();}

function sortBy(col){
  if(sortCol === col){sortDir = sortDir==='asc'?'desc':'asc';}
  else {sortCol = col; sortDir = 'asc';}
  refreshTable();
}

function openModal(code){
  var s = S[code];
  if(!s) return;
  var labels = {current_price:'股價',trailing_pe:'本益比(TTM)',forward_pe:'本益比(預估)',price_to_book:'股價淨值比',revenue_growth:'營收成長',profit_margins:'利潤率',return_on_equity:'ROE',debt_to_equity:'負債權益比',dividend_yield:'殖利率',beta:'Beta','52w_high':'52周高','52w_low':'52周低'};
  var overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.onclick = function(e){if(e.target===overlay){document.body.removeChild(overlay);}};
  var items = '';
  for(var k in labels){
    var lb=labels[k],v=s[k],dsp=v;
    if(k==='dividend_yield') dsp=dy(v);
    else if(k==='revenue_growth'||k==='profit_margins'||k==='return_on_equity') dsp=pct(v);
    else if(typeof v==='number') dsp=v.toFixed(2);
    else if(v==null) dsp='—';
    items += '<div class="modal-item"><div class="mlabel">'+lb+'</div><div class="mvalue">'+dsp+'</div></div>';
  }
  var chartId = 'kline_'+code;
  overlay.innerHTML = '<div class="modal" style="max-width:760px"><div class="modal-header"><div><h2>'+esc(s.code)+' '+esc(s.name_cn||s.name||'')+'</h2><div class="modal-badge">'+esc(s.sector||'')+' · '+esc(s.industry||'')+'</div></div><button class="modal-close" onclick="this.parentElement.parentElement.parentElement.remove()">✕</button></div><div class="modal-grid">'+items+'</div><div class="kline-box"><h3>日K線</h3><div class="kline-periods"><button class="active" data-period="6mo">6月</button><button data-period="1y">1年</button><button data-period="2y">2年</button></div><div class="chart-wrap"><canvas id="'+chartId+'"></canvas></div></div></div>';
  document.body.appendChild(overlay);
  loadKline(code,'6mo');
}

var KLINE_DATA = null;
fetch('/twse-etf-fa-hermes/data/kline_data.json').then(function(r){return r.json();}).then(function(d){KLINE_DATA=d;}).catch(function(){});

function loadKline(code,period,_btn){
  if(!code) return;
  var kbox = document.getElementById('kline_'+code);
  if(!kbox) return;
  var canvas = kbox;
  var existing = Chart.getChart(canvas);
  if(existing) existing.destroy();
  var ctx = canvas.getContext('2d');
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.font='14px sans-serif'; ctx.fillStyle='#94a3b8'; ctx.textAlign='center';
  ctx.fillText('載入中...',canvas.width/2,canvas.height/2);
  var pr = canvas.closest('.kline-box')?.querySelector('.kline-periods');
  if(pr) pr.querySelectorAll('button').forEach(function(b){b.className=''; if(b.dataset.period===period)b.className='active';});
  
  // Helper: load once, use from cache
  function renderKline(kd){
    if(!kd||!kd.t||kd.t.length===0){
      ctx.clearRect(0,0,canvas.width,canvas.height);
      ctx.font='14px sans-serif'; ctx.fillStyle='#94a3b8'; ctx.textAlign='center';
      ctx.fillText('暫無K線資料',canvas.width/2,canvas.height/2);
      return;
    }
    var ohlcv = kd.t.map(function(t,i){
      return {t:t, o:kd.o[i], h:kd.h[i], l:kd.l[i], c:kd.c[i], v:kd.v[i]};
    });
    var prices = ohlcv.map(function(d){return {x:d.t, y:d.c};});
    function sma(arr,n){
      var r=[]; for(var i=0;i<arr.length;i++){
        if(i<n-1){r.push({x:arr[i].x,y:null});continue;}
        var s=0; for(var j=i-n+1;j<=i;j++) s+=arr[j].y;
        r.push({x:arr[i].x,y:+(s/n).toFixed(2)});
      } return r;
    }
    new Chart(canvas, {
      type: 'line',
      data: {datasets:[{label:code+' 收盤價',data:prices,borderColor:'#0f172a',borderWidth:2,pointRadius:0,fill:false,tension:0.1,order:0},{label:'MA20',data:sma(prices,20),borderColor:'#8b5cf6',borderWidth:1.5,pointRadius:0,fill:false,borderDash:[4,3],order:1},{label:'MA60',data:sma(prices,60),borderColor:'#ec4899',borderWidth:1.5,pointRadius:0,fill:false,borderDash:[4,3],order:2}]},
      options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},plugins:{legend:{position:'top',labels:{boxWidth:14,font:{size:11},usePointStyle:true}},tooltip:{backgroundColor:'#fff',titleColor:'#0f172a',bodyColor:'#475569',borderColor:'#e2e8f0',borderWidth:1,cornerRadius:8,padding:12,boxPadding:4,callbacks:{title:function(items){return new Date(items[0].parsed.x*1000).toLocaleDateString('zh-TW');},label:function(ctx){if(ctx.dataset.label.indexOf('MA')===0) return ctx.dataset.label+': '+ctx.parsed.y.toFixed(2);return code+'收盤價: '+ctx.parsed.y.toFixed(2);}}}},scales:{x:{type:'linear',grid:{display:false},ticks:{font:{size:10},color:'#94a3b8',callback:function(v){return new Date(v*1000).toLocaleDateString('zh-TW',{month:'short',day:'numeric'})}}},y:{beginAtZero:false,grid:{color:'#f1f5f9',drawBorder:false},ticks:{font:{size:11},color:'#475569',callback:function(v){return v.toFixed(0);}}}}}
    });
  }
  
  if(KLINE_DATA && KLINE_DATA[code]){
    renderKline(KLINE_DATA[code]);
  } else {
    // Lazy load if not cached yet
    fetch('/twse-etf-fa-hermes/data/kline_data.json').then(function(r){return r.json();}).then(function(d){
      KLINE_DATA = d;
      renderKline(d[code]);
    }).catch(function(e){console.error('Kline error:',e);});
  }
}

document.addEventListener('click', function(e){
  var btn = e.target.closest('.kline-periods button');
  if(!btn) return;
  var kbox = btn.closest('.kline-box');
  if(!kbox) return;
  var canvas = kbox.querySelector('canvas');
  if(!canvas) return;
  var id = canvas.id;
  if(!id||!id.startsWith('kline_')) return;
  var code = id.replace('kline_','');
  var period = btn.dataset.period;
  if(!code||!period) return;
  loadKline(code,period);
});

function getSectorData(code){
  var stocks;
  if(code==='__all__'){
    stocks = ETF_CODES.reduce(function(a,c){return a.concat(ETFS[c]?ETFS[c].stocks:[]);},[]);
  } else {
    stocks = ETFS[code] ? ETFS[code].stocks : [];
  }
  var map = {};
  var seen = {};
  stocks.forEach(function(c){
    if(seen[c]) return;
    seen[c] = true;
    var s = S[c];
    if(s && s.sector){ map[s.sector] = (map[s.sector]||0) + 1; }
  });
  var keys = Object.keys(map).sort(function(a,b){return map[b]-map[a];});
  return keys.map(function(k){return [k, map[k]];});
}

function renderHealth(){
  var panel = document.getElementById('healthPanel');
  if(!panel) return;
  var stocks = (ETFS[activeTab]?ETFS[activeTab].stocks:[]).map(function(c){return S[c];}).filter(Boolean);
  if(!stocks.length){ panel.innerHTML='<div style="color:#94a3b8;text-align:center;padding:20px">無資料</div>'; return; }
  var pes = stocks.map(function(s){return s.trailing_pe;}).filter(function(v){return v&&v>0;}).sort(function(a,b){return a-b;});
  var dys = stocks.map(function(s){return s.dividend_yield;}).filter(function(v){return v!=null;}).sort(function(a,b){return a-b;});
  var betas = stocks.map(function(s){return s.beta;}).filter(function(v){return v!=null;});
  var roes = stocks.map(function(s){return s.return_on_equity;}).filter(function(v){return v!=null;});
  var mcaps = stocks.map(function(s){return s.market_cap||0;}).sort(function(a,b){return b-a;});
  var totalMcap = mcaps.reduce(function(a,b){return a+b;},0);
  var top3pct = totalMcap>0 ? (mcaps[0]+mcaps[1]+mcaps[2])/totalMcap*100 : 0;
  var topSector = getSectorData(activeTab);
  var topSectorPct = topSector.length>0 ? Math.round(topSector[0][1]/stocks.length*100) : 0;
  function median(arr){if(!arr.length)return null;var m=Math.floor(arr.length/2);return arr.length%2?arr[m]:(arr[m-1]+arr[m])/2;}
  var count = stocks.length;
  var divStars = count>=50?'★★★★★':count>=30?'★★★★☆':count>=20?'★★★☆☆':count>=10?'★★☆☆☆':'★☆☆☆☆';
  var peMed = median(pes);
  var dyMed = median(dys);
  var betaAvg = betas.length ? (betas.reduce(function(a,b){return a+b;},0)/betas.length).toFixed(2) : '—';
  var roeMed = median(roes);
  var h = '<table style="width:100%;border-collapse:collapse">';
  function row(label,value,color){
    h += '<tr><td style="padding:6px 8px;color:#64748b;border-bottom:1px solid #f1f5f9;white-space:nowrap">'+label+'</td><td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;text-align:right;font-weight:600;font-variant-numeric:tabular-nums'+(color?';color:'+color:'')+'">'+value+'</td></tr>';
  }
  row('📊 分散度評分','<span style="color:#f59e0b">'+divStars+'</span>');
  row('📋 成分股數量',count+' 檔');
  row('🔝 前3大持股佔比',top3pct.toFixed(1)+'%',top3pct>50?'#dc2626':'#0f172a');
  row('🏢 最大產業佔比',topSectorPct+'%',topSectorPct>50?'#dc2626':'#0f172a');
  row('📈 本益比中位數',peMed!=null?peMed.toFixed(1):'—');
  row('💰 殖利率中位數',dyMed!=null?(dyMed*100).toFixed(2)+'%':'—');
  row('📉 平均 Beta',betaAvg);
  row('📊 ROE 中位數',roeMed!=null?(roeMed*100).toFixed(2)+'%':'—');
  h += '</table>';
  panel.innerHTML = h;
}

function renderCharts(){
  renderHealth();
  for(var k in chartInstances){chartInstances[k].destroy();}
  chartInstances = {};
  var ctx1 = document.getElementById('sectorChart');
  if(ctx1){
    var sectorCode = currentTab==='overview' ? '__all__' : activeTab;
    var sd = getSectorData(sectorCode);
    chartInstances.sector = new Chart(ctx1, {type:'doughnut',data:{labels:sd.map(function(s){return s[0]+' ('+s[1]+')';}),datasets:[{data:sd.map(function(s){return s[1];}),backgroundColor:sd.map(function(s){return sc(s[0]);}),borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{position:'right',labels:{boxWidth:12,font:{size:11}}}}}});
  }
  var ctx2 = document.getElementById('peChart');
  if(ctx2){
    var pd = ETF_CODES.map(function(c){return {code:c,name:ES[c]?ES[c].name:'',pe:ES[c]?ES[c].avg_pe:null};}).filter(function(d){return d.pe!=null;});
    chartInstances.pe = new Chart(ctx2, {type:'bar',data:{labels:pd.map(function(d){return d.code+' '+d.name;}),datasets:[{label:'平均本益比',data:pd.map(function(d){return d.pe;}),backgroundColor:'#0f172a',borderRadius:4,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{display:false}},x:{grid:{display:false}}}}});
  }
  var ctx3 = document.getElementById('dyChart');
  if(ctx3){
    var dd = ETF_CODES.map(function(c){return {code:c,name:ES[c]?ES[c].name:'',dy:ES[c]?ES[c].avg_dy:null};}).filter(function(d){return d.dy!=null;});
    chartInstances.dy = new Chart(ctx3, {type:'bar',data:{labels:dd.map(function(d){return d.code+' '+d.name;}),datasets:[{label:'平均殖利率',data:dd.map(function(d){return d.dy;}),backgroundColor:'#059669',borderRadius:4,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{display:false},ticks:{callback:function(v){return v+'%';}}},x:{grid:{display:false}}}}});
  }
  var ctx4 = document.getElementById('roeChart');
  if(ctx4){
    var rd = ETF_CODES.map(function(c){return {code:c,name:ES[c]?ES[c].name:'',roe:ES[c]?ES[c].avg_roe:null};}).filter(function(d){return d.roe!=null;});
    chartInstances.roe = new Chart(ctx4, {type:'bar',data:{labels:rd.map(function(d){return d.code+' '+d.name;}),datasets:[{label:'平均ROE',data:rd.map(function(d){return d.roe;}),backgroundColor:'#2563eb',borderRadius:4,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{display:false},ticks:{callback:function(v){return v+'%';}}},x:{grid:{display:false}}}}});
  }
  var ctx5 = document.getElementById('peRankChart');
  if(ctx5){
    var pr = DATA.peStocks;
    chartInstances.peRank = new Chart(ctx5, {type:'bar',data:{labels:pr.map(function(d){return d[0];}),datasets:[{label:'本益比',data:pr.map(function(d){return d[1];}),backgroundColor:'#0f172a',borderRadius:4,borderSkipped:false}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,grid:{display:false}},y:{grid:{display:false},ticks:{font:{size:10}}}}}});
  }
}

document.addEventListener('DOMContentLoaded', renderApp);
"""
    return """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TWSE ETF 財務儀表板</title>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5115666613619890"
        crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC",sans-serif;background:#f8fafc;color:#0f172a;min-height:100vh;overflow-x:hidden;word-wrap:break-word}
.container{max-width:1400px;margin:0 auto;padding:24px;overflow-x:auto}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:32px;padding-bottom:20px;border-bottom:1px solid #e2e8f0}
.header h1{font-size:28px;font-weight:700;letter-spacing:-0.02em}
.header .meta{font-size:14px;color:#64748b}
.etf-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin-bottom:32px}
.etf-card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);transition:all 0.2s;cursor:pointer}
.etf-card:hover{box-shadow:0 4px 12px rgba(0,0,0,0.08);border-color:#0f172a}
.etf-card.active{border-color:#0f172a;border-width:2px}
.etf-card h3{font-size:18px;font-weight:600;margin-bottom:4px}
.etf-code{font-size:12px;color:#64748b;margin-bottom:12px}
.etf-stats{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.stat{font-size:13px}
.stat-label{color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:2px}
.stat-value{font-weight:600;font-variant-numeric:tabular-nums}
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
@media(max-width:900px){.charts-row{grid-template-columns:1fr}}
.chart-box{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}
.chart-box h2{font-size:18px;font-weight:600;margin-bottom:16px}
.chart-box canvas{max-height:300px;width:100%!important}
.etf-tabs{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
.etf-tab{padding:8px 16px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;cursor:pointer;font-size:14px;transition:all 0.15s;font-family:inherit}
.etf-tab:hover{border-color:#94a3b8}
.etf-tab.active{background:#0f172a;color:#fff;border-color:#0f172a}
.search-bar{width:100%;padding:10px 16px;border:1px solid #e2e8f0;border-radius:8px;font-size:14px;margin-bottom:16px;outline:none;font-family:inherit}
.search-bar:focus{border-color:#0f172a}
.stock-table{width:100%;border-collapse:collapse;font-size:13px}
.stock-table th{text-align:left;padding:10px 12px;border-bottom:2px solid #e2e8f0;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.05em;white-space:nowrap;cursor:pointer;user-select:none}
.stock-table th:hover{color:#0f172a}
.stock-table td{padding:10px 12px;border-bottom:1px solid #f1f5f9;font-variant-numeric:tabular-nums;white-space:nowrap}
.stock-table tr{cursor:pointer;transition:background 0.1s}
.stock-table tr:hover{background:#f1f5f9}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.3);z-index:100;display:flex;align-items:center;justify-content:center}
.modal{background:#fff;border-radius:16px;padding:32px;max-width:600px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.15)}
.modal-header{display:flex;justify-content:space-between;align-items:start;margin-bottom:20px}
.modal-header h2{font-size:22px;font-weight:700}
.modal-badge{font-size:12px;padding:2px 10px;border-radius:999px;background:#f1f5f9;color:#475569;display:inline-block;margin-top:4px}
.modal-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:16px}
.modal-item .mlabel{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:2px}
.modal-item .mvalue{font-size:18px;font-weight:600;font-variant-numeric:tabular-nums}
.kline-box{margin-top:20px;border-top:1px solid #e2e8f0;padding-top:16px}
.kline-box h3{font-size:14px;font-weight:600;margin-bottom:8px;color:#475569}
.kline-box .chart-wrap{position:relative;width:100%;height:420px}
.kline-box canvas{width:100%!important;height:100%!important}
.kline-periods{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}
.kline-periods button{padding:4px 12px;border:1px solid #e2e8f0;border-radius:6px;background:#fff;cursor:pointer;font-size:12px;font-family:inherit}
.kline-periods button:hover{border-color:#94a3b8}
.kline-periods button.active{background:#0f172a;color:#fff;border-color:#0f172a}
.modal-close{background:none;border:none;cursor:pointer;color:#94a3b8;font-size:24px;padding:4px}
.modal-close:hover{color:#0f172a}
.top10-table{width:100%;border-collapse:collapse;font-size:13px}
.top10-table th{text-align:left;padding:8px 12px;border-bottom:2px solid #e2e8f0;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.05em}
.top10-table td{padding:8px 12px;border-bottom:1px solid #f1f5f9;font-variant-numeric:tabular-nums}
.footer{text-align:center;padding:20px;font-size:12px;color:#94a3b8}
.tab-bar{display:flex;gap:0;margin-bottom:24px;border-bottom:2px solid #e2e8f0}
.tab-btn{padding:10px 24px;border:none;background:none;font-size:15px;font-weight:600;color:#94a3b8;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;font-family:inherit;transition:all 0.15s}
.tab-btn:hover{color:#475569}
.tab-btn.active{color:#0f172a;border-bottom-color:#0f172a}
</style>
</head>
<body>
<div id="app" class="container"></div>
<script>
""" + jscode + """</script>
</body>
</html>"""


def main():
    current_mtime = get_data_mtime()
    cache = load_cache()

    # Use cache if source data hasn't changed
    if cache and cache.get("mtime") == current_mtime:
        data_obj = cache["data"]
        print(f"[快取] 資料未變，使用快取 (mtime={current_mtime})")
    else:
        print(f"[讀取] 載入 {DATA_DIR} 中的 JSON 資料...")
        etfs, stocks_data = build_data()
        data_obj = compute_stats(etfs, stocks_data)
        save_cache(data_obj, current_mtime)
        print(f"[快取] 已儲存至 {CACHE_FILE}")

    html = generate_html(data_obj)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Dashboard: {OUTPUT_FILE}")
    print(f"   Stocks: {len(data_obj['stocks'])}, ETFs: {len(data_obj['etfs'])}, Size: {len(html)//1024}KB")


if __name__ == "__main__":
    main()
