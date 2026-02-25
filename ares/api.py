import os
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS
from datetime import datetime
import pytz
import eikon as ek
import numpy as np
import pandas as pd
import threading
import time
from langdetect import detect

_env_path = Path(__file__).resolve().parent.parent / '.env'
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# Refinitiv Eikon API setup (requires Eikon Workspace running locally)
# ---------------------------------------------------------------------------

EIKON_APP_KEY = os.environ.get('EIKON_APP_KEY', '')
if not EIKON_APP_KEY:
    raise RuntimeError('Set EIKON_APP_KEY env var (or add it to .env in project root)')
ek.set_app_key(EIKON_APP_KEY)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_mkt_cap(val):
    if val is None or pd.isna(val) or val <= 0:
        return '—'
    if val >= 1e12:
        return f'{val/1e12:.1f}T'
    if val >= 1e9:
        return f'{val/1e9:.0f}B'
    if val >= 1e6:
        return f'{val/1e6:.0f}M'
    return str(round(val))


def _safe_float(val, default=0):
    try:
        if val is None or pd.isna(val):
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

WATCHLIST_META = [
    {'Ticker': 'AAPL', 'RIC': 'AAPL.O', 'Company': 'Apple', 'Sector': 'Technology'},
    {'Ticker': 'MSFT', 'RIC': 'MSFT.O', 'Company': 'Microsoft', 'Sector': 'Technology'},
    {'Ticker': 'GOOGL', 'RIC': 'GOOGL.O', 'Company': 'Alphabet', 'Sector': 'Technology'},
    {'Ticker': 'NVDA', 'RIC': 'NVDA.O', 'Company': 'NVIDIA', 'Sector': 'Technology'},
    {'Ticker': 'META', 'RIC': 'META.O', 'Company': 'Meta', 'Sector': 'Technology'},
    {'Ticker': 'AMZN', 'RIC': 'AMZN.O', 'Company': 'Amazon', 'Sector': 'Consumer'},
    {'Ticker': 'TSLA', 'RIC': 'TSLA.O', 'Company': 'Tesla', 'Sector': 'Consumer'},
    {'Ticker': 'NKE', 'RIC': 'NKE.N', 'Company': 'Nike', 'Sector': 'Consumer'},
    {'Ticker': 'JPM', 'RIC': 'JPM.N', 'Company': 'JPMorgan', 'Sector': 'Financials'},
    {'Ticker': 'BAC', 'RIC': 'BAC.N', 'Company': 'BofA', 'Sector': 'Financials'},
    {'Ticker': 'GS', 'RIC': 'GS.N', 'Company': 'Goldman', 'Sector': 'Financials'},
    {'Ticker': 'LMT', 'RIC': 'LMT.N', 'Company': 'Lockheed', 'Sector': 'Defense'},
    {'Ticker': 'RTX', 'RIC': 'RTX.N', 'Company': 'Raytheon', 'Sector': 'Defense'},
    {'Ticker': 'BA', 'RIC': 'BA.N', 'Company': 'Boeing', 'Sector': 'Defense'},
    {'Ticker': 'XOM', 'RIC': 'XOM.N', 'Company': 'Exxon', 'Sector': 'Energy'},
    {'Ticker': 'CVX', 'RIC': 'CVX.N', 'Company': 'Chevron', 'Sector': 'Energy'},
    {'Ticker': 'UNH', 'RIC': 'UNH.N', 'Company': 'UnitedHealth', 'Sector': 'Healthcare'},
    {'Ticker': 'JNJ', 'RIC': 'JNJ.N', 'Company': 'J&J', 'Sector': 'Healthcare'},
    {'Ticker': 'COIN', 'RIC': 'COIN.O', 'Company': 'Coinbase', 'Sector': 'Crypto'},
    {'Ticker': 'MSTR', 'RIC': 'MSTR.O', 'Company': 'MicroStrategy', 'Sector': 'Crypto'},
    {'Ticker': 'RIOT', 'RIC': 'RIOT.O', 'Company': 'Riot Platforms', 'Sector': 'Crypto'},
    {'Ticker': 'MARA', 'RIC': 'MARA.O', 'Company': 'Marathon Digital', 'Sector': 'Crypto'},
]


def fetch_watchlist():
    """Fetch watchlist data from Refinitiv Eikon in a single batch call."""
    rics = [m['RIC'] for m in WATCHLIST_META]
    meta_map = {m['RIC']: m for m in WATCHLIST_META}

    # Call 1: pricing + returns (streaming + TR fields that work together)
    pricing_fields = [
        'CF_LAST', 'CF_CLOSE',
        'TR.PricePctChg1D',
        'TR.CompanyMarketCap',
        'TR.TotalReturn1Wk',
        'TR.TotalReturn1Mo',
    ]
    try:
        snapshot_df, _ = ek.get_data(rics, pricing_fields)
    except Exception as e:
        print(f'[{datetime.now()}] Eikon get_data (pricing) failed: {e}')
        snapshot_df = pd.DataFrame()

    # Call 2: Beta via TR.WACCBeta (TR.Beta silently fails in batch requests)
    beta_map = {}
    try:
        beta_df, _ = ek.get_data(rics, ['TR.WACCBeta'])
        if beta_df is not None and not beta_df.empty:
            beta_col = [c for c in beta_df.columns if 'beta' in c.lower()]
            inst_col = [c for c in beta_df.columns if c and 'instrument' in c.lower()]
            if beta_col and inst_col:
                for _, brow in beta_df.iterrows():
                    beta_map[brow[inst_col[0]]] = _safe_float(brow[beta_col[0]])
    except Exception as e:
        print(f'[{datetime.now()}] Eikon get_data (beta) failed: {e}')

    # Call 3: historical closes for volatility
    from datetime import timedelta
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d')
    try:
        hist_df = ek.get_timeseries(rics, fields='CLOSE',
                                     start_date=start, end_date=end,
                                     interval='daily')
    except Exception as e:
        print(f'[{datetime.now()}] Eikon get_timeseries failed: {e}')
        hist_df = pd.DataFrame()

    # Build a column-name lookup (Eikon returns human-readable headers)
    col_map = {}
    if not snapshot_df.empty:
        for col in snapshot_df.columns:
            cl = col.lower()
            if 'price' in cl and 'change' in cl:
                col_map['pctchg'] = col
            elif 'market cap' in cl:
                col_map['mktcap'] = col
            elif 'return' in cl and 'week' in cl:
                col_map['d7'] = col
            elif 'return' in cl and 'month' in cl:
                col_map['d30'] = col

    rows = []
    for m in WATCHLIST_META:
        ric = m['RIC']
        row = {'Ticker': m['Ticker'], 'Company': m['Company'], 'Sector': m['Sector']}

        if not snapshot_df.empty and 'Instrument' in snapshot_df.columns:
            snap = snapshot_df[snapshot_df['Instrument'] == ric]
            if not snap.empty:
                s = snap.iloc[0]
                price = _safe_float(s.get('CF_LAST')) or _safe_float(s.get('CF_CLOSE'))
                row['Price'] = f'${price:,.2f}' if price else '—'
                row['h24'] = round(_safe_float(s.get(col_map.get('pctchg', ''))), 1)
                row['d7'] = round(_safe_float(s.get(col_map.get('d7', ''))), 1)
                row['d30'] = round(_safe_float(s.get(col_map.get('d30', ''))), 1)
                mc = _safe_float(s.get(col_map.get('mktcap', '')))
                row['MktCap'] = _fmt_mkt_cap(mc) if mc else '—'
            else:
                row.update({'Price': '—', 'h24': 0, 'd7': 0, 'd30': 0, 'MktCap': '—'})
        else:
            row.update({'Price': '—', 'h24': 0, 'd7': 0, 'd30': 0, 'MktCap': '—'})

        row['Beta'] = round(beta_map.get(ric, 0), 2)

        # Volatility from historical closes
        try:
            closes = pd.Series(dtype=float)
            if not hist_df.empty:
                if ric in hist_df.columns:
                    closes = hist_df[ric].dropna()
                elif 'CLOSE' in hist_df.columns and len(rics) == 1:
                    closes = hist_df['CLOSE'].dropna()

            if len(closes) > 5:
                rets = closes.pct_change().dropna()
                row['Vol'] = round(float(np.std(rets)) * 100 * np.sqrt(252), 1)
            else:
                row['Vol'] = 0
        except Exception:
            row['Vol'] = 0

        row['Corr'] = 0.75
        row['Sharpe'] = round(row.get('d30', 0) / (row['Vol'] or 1), 2) if row['Vol'] else 0
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Yield curve (live from Eikon)
# ---------------------------------------------------------------------------

YIELD_CURVE_RICS = {
    '1M': 'US1MT=RR', '3M': 'US3MT=RR', '6M': 'US6MT=RR',
    '1Y': 'US1YT=RR', '2Y': 'US2YT=RR', '3Y': 'US3YT=RR',
    '5Y': 'US5YT=RR', '7Y': 'US7YT=RR', '10Y': 'US10YT=RR',
    '20Y': 'US20YT=RR', '30Y': 'US30YT=RR',
}

YIELD_CURVE_FALLBACK = {
    'maturities': list(YIELD_CURVE_RICS.keys()),
    'yields': [5.42, 5.38, 5.28, 4.95, 4.45, 4.28, 4.25, 4.32, 4.45, 4.72, 4.68],
    'key_rates': [
        {'Maturity': '2-Year', 'Rate': '4.45%', 'D1': '+2', 'W1': '-5', 'M1': '+12', 'M3': '+28'},
        {'Maturity': '10-Year', 'Rate': '4.45%', 'D1': '+3', 'W1': '-3', 'M1': '+15', 'M3': '+32'},
        {'Maturity': '30-Year', 'Rate': '4.68%', 'D1': '+1', 'W1': '-2', 'M1': '+8', 'M3': '+22'},
    ],
}


def fetch_yield_curve():
    """Fetch live Treasury yields from Refinitiv Eikon using SEC_YLD_1."""
    try:
        rics = list(YIELD_CURVE_RICS.values())
        df, _ = ek.get_data(rics, ['SEC_YLD_1'])
        if df is None or df.empty:
            return YIELD_CURVE_FALLBACK

        # Find the yield column (Eikon may return it as 'SEC_YLD_1' or similar)
        yld_col = None
        for col in df.columns:
            if col != 'Instrument':
                yld_col = col
                break
        if not yld_col:
            return YIELD_CURVE_FALLBACK

        yields_map = {}
        for _, row in df.iterrows():
            yields_map[row['Instrument']] = _safe_float(row.get(yld_col))

        maturities = list(YIELD_CURVE_RICS.keys())
        yields = [round(yields_map.get(YIELD_CURVE_RICS[m], 0), 2) for m in maturities]

        y2 = yields_map.get('US2YT=RR', 0)
        y10 = yields_map.get('US10YT=RR', 0)
        y30 = yields_map.get('US30YT=RR', 0)

        key_rates = [
            {'Maturity': '2-Year', 'Rate': f'{y2:.2f}%', 'D1': '—', 'W1': '—', 'M1': '—', 'M3': '—'},
            {'Maturity': '10-Year', 'Rate': f'{y10:.2f}%', 'D1': '—', 'W1': '—', 'M1': '—', 'M3': '—'},
            {'Maturity': '30-Year', 'Rate': f'{y30:.2f}%', 'D1': '—', 'W1': '—', 'M1': '—', 'M3': '—'},
        ]

        return {'maturities': maturities, 'yields': yields, 'key_rates': key_rates}
    except Exception as e:
        print(f'[{datetime.now()}] Yield curve fetch failed: {e}')
        return YIELD_CURVE_FALLBACK


# ---------------------------------------------------------------------------
# Live news from Eikon
# ---------------------------------------------------------------------------

SOURCE_LABELS = {
    'NS:RTRS': 'Reuters', 'NS:BLOOM': 'Bloomberg', 'NS:BBG': 'Bloomberg',
    'NS:WSJO': 'WSJ', 'NS:WSJ': 'WSJ', 'NS:DJDN': 'Dow Jones',
    'NS:FT': 'Financial Times', 'NS:CNBC': 'CNBC', 'NS:ASSOPR': 'AP',
    'NS:INDEPE': 'The Independent', 'NS:PRN': 'PR Newswire',
    'NS:CMNW': 'Cision', 'NS:IFR': 'IFR',
}

STOCK_NEWS_RICS = [m['RIC'] for m in WATCHLIST_META]
MARKET_NEWS_QUERIES = ['R:US10YT=RR', 'R:US2YT=RR', 'R:US30YT=RR', 'R:US5YT=RR']


def _is_english(text):
    try:
        return detect(text) == 'en'
    except Exception:
        return False


def _format_source(code):
    return SOURCE_LABELS.get(code, code.replace('NS:', ''))


def _fetch_headlines(query, count=8):
    """Fetch headlines for a single query, return list of raw rows."""
    try:
        df = ek.get_news_headlines(query, count=count)
        if df is None or df.empty:
            return []
        return [row.to_dict() for _, row in df.iterrows()]
    except Exception:
        return []


def _get_story_summary(story_id):
    """Fetch first ~200 chars of the story body as a summary."""
    try:
        import re
        html = ek.get_news_story(story_id)
        if not html:
            return ''
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.S)
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.S)
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 200:
            text = text[:200].rsplit(' ', 1)[0] + '...'
        return text
    except Exception:
        return ''


def fetch_live_articles():
    """Fetch live news from Eikon for stock and market categories."""
    seen = set()

    # Stock news
    stock_news = []
    for ric in STOCK_NEWS_RICS:
        if len(stock_news) >= 10:
            break
        rows = _fetch_headlines(f'R:{ric}', count=6)
        for r in rows:
            sid = r.get('storyId', '')
            if sid in seen:
                continue
            title = r.get('text', '')
            if not title or not _is_english(title):
                continue
            seen.add(sid)
            ticker = ric.split('.')[0]
            dt = str(r.get('versionCreated', ''))[:16]
            summary = _get_story_summary(sid)
            stock_news.append({
                'title': title,
                'source': _format_source(r.get('sourceCode', '')),
                'date': dt,
                'related_to': ticker,
                'impact': 'Stock Price',
                'summary': summary or title,
                'storyId': sid,
            })
            if len(stock_news) >= 10:
                break

    # Market / rates news
    market_news = []
    for query in MARKET_NEWS_QUERIES:
        if len(market_news) >= 10:
            break
        rows = _fetch_headlines(query, count=8)
        for r in rows:
            sid = r.get('storyId', '')
            if sid in seen:
                continue
            title = r.get('text', '')
            if not title or not _is_english(title):
                continue
            seen.add(sid)
            dt = str(r.get('versionCreated', ''))[:16]
            summary = _get_story_summary(sid)
            market_news.append({
                'title': title,
                'source': _format_source(r.get('sourceCode', '')),
                'date': dt,
                'related_to': 'Yield Curve',
                'impact': 'Yield Curve',
                'summary': summary or title,
                'storyId': sid,
            })
            if len(market_news) >= 10:
                break

    return {'stock_news': stock_news, 'market_news': market_news}


market_articles = {'stock_news': [], 'market_news': []}


def refresh_articles():
    global market_articles
    try:
        fresh = fetch_live_articles()
        if fresh['stock_news'] or fresh['market_news']:
            market_articles = fresh
            print(f'[{datetime.now()}] Articles refreshed: '
                  f'{len(fresh["stock_news"])} stock, {len(fresh["market_news"])} market')
    except Exception as e:
        print(f'[{datetime.now()}] Articles refresh failed: {e}')


# ---------------------------------------------------------------------------
# Cached data – refreshed in background, served instantly
# ---------------------------------------------------------------------------

_watchlist_cache = []
_watchlist_last_updated = None
_yield_curve_cache = YIELD_CURVE_FALLBACK
_yield_curve_last_updated = None

WATCHLIST_INTERVAL = 15    # seconds between watchlist refreshes
YIELD_CURVE_INTERVAL = 60  # seconds between yield-curve refreshes
ARTICLES_INTERVAL = 300    # seconds between news refreshes (5 min)


def _data_refresh_loop():
    """Single background thread that calls Eikon sequentially — avoids async clashes."""
    global _watchlist_cache, _watchlist_last_updated
    global _yield_curve_cache, _yield_curve_last_updated

    last_yc_refresh = 0
    last_articles_refresh = 0

    while True:
        # Watchlist refresh (every cycle)
        try:
            fresh = fetch_watchlist()
            if fresh:
                _watchlist_cache = fresh
                _watchlist_last_updated = datetime.now().isoformat()
                print(f'[{datetime.now()}] Watchlist refreshed ({len(fresh)} rows)')
        except Exception as e:
            print(f'[{datetime.now()}] Watchlist refresh failed: {e}')

        now = time.time()

        # Yield curve refresh
        if now - last_yc_refresh >= YIELD_CURVE_INTERVAL:
            try:
                yc = fetch_yield_curve()
                if yc and yc.get('yields'):
                    _yield_curve_cache = yc
                    _yield_curve_last_updated = datetime.now().isoformat()
                    print(f'[{datetime.now()}] Yield curve refreshed')
            except Exception as e:
                print(f'[{datetime.now()}] Yield curve refresh failed: {e}')
            last_yc_refresh = now

        # Articles refresh (every 5 minutes)
        if now - last_articles_refresh >= ARTICLES_INTERVAL:
            refresh_articles()
            last_articles_refresh = now

        time.sleep(WATCHLIST_INTERVAL)


_refresh_thread = threading.Thread(target=_data_refresh_loop, daemon=True)
_refresh_thread.start()
print(f'Background refresh started: watchlist every {WATCHLIST_INTERVAL}s, yield curve every {YIELD_CURVE_INTERVAL}s, articles daily at 06:00 London')


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/api/watchlist')
def api_watchlist():
    return jsonify({
        'data': _watchlist_cache,
        'last_updated': _watchlist_last_updated,
    })


@app.route('/api/yield-curve')
def api_yield_curve():
    return jsonify(_yield_curve_cache)


@app.route('/api/articles')
def api_articles():
    return jsonify(market_articles)


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5001)
