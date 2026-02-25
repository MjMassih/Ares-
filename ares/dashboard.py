import os
from pathlib import Path
import dash
from dash import html, dash_table, dcc
from dash.dependencies import Input, Output
import pandas as pd
import plotly.graph_objects as go
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
import eikon as ek
import numpy as np

_env_path = Path(__file__).resolve().parent.parent / '.env'
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

ek.set_app_key(os.environ.get('EIKON_APP_KEY', ''))

# Initialize the Dash app
app = dash.Dash(__name__)
app.title = "Ares - Market Intelligence"

# Format performance values
def format_performance(val):
    if val > 0:
        return f'+{val}%'
    return f'{val}%'

def _fmt_mkt_cap(val):
    """Format market cap as B/T"""
    if pd.isna(val) or val <= 0:
        return '—'
    if val >= 1e12:
        return f'{val/1e12:.1f}T'
    if val >= 1e9:
        return f'{val/1e9:.0f}B'
    if val >= 1e6:
        return f'{val/1e6:.0f}M'
    return str(round(val))

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


def _safe_float(val, default=0):
    try:
        if val is None or pd.isna(val):
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def fetch_watchlist_data():
    """Fetch live watchlist data from Refinitiv Eikon."""
    rics = [m['RIC'] for m in WATCHLIST_META]

    fields = [
        'CF_LAST', 'CF_CLOSE',
        'TR.PricePctChg1D',
        'TR.CompanyMarketCap',
        'TR.Beta',
        'TR.TotalReturn1Wk',
        'TR.TotalReturn1Mo',
    ]

    try:
        snapshot_df, _ = ek.get_data(rics, fields)
    except Exception as e:
        print(f'Eikon get_data failed: {e}')
        snapshot_df = pd.DataFrame()

    from datetime import timedelta
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d')
    try:
        hist_df = ek.get_timeseries(rics, fields='CLOSE',
                                     start_date=start, end_date=end,
                                     interval='daily')
    except Exception as e:
        print(f'Eikon get_timeseries failed: {e}')
        hist_df = pd.DataFrame()

    col_map = {}
    if not snapshot_df.empty:
        for col in snapshot_df.columns:
            cl = col.lower()
            if 'price' in cl and 'change' in cl:
                col_map['pctchg'] = col
            elif 'market cap' in cl:
                col_map['mktcap'] = col
            elif cl == 'beta' or 'beta' in cl:
                col_map['beta'] = col
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
                row['24h'] = round(_safe_float(s.get(col_map.get('pctchg', ''))), 1)
                row['7d'] = round(_safe_float(s.get(col_map.get('d7', ''))), 1)
                row['30d'] = round(_safe_float(s.get(col_map.get('d30', ''))), 1)
                mc = _safe_float(s.get(col_map.get('mktcap', '')))
                row['Mkt Cap'] = _fmt_mkt_cap(mc) if mc else '—'
                row['Beta'] = round(_safe_float(s.get(col_map.get('beta', ''))), 2)
            else:
                row.update({'Price': '—', '24h': 0, '7d': 0, '30d': 0, 'Mkt Cap': '—', 'Beta': 0})
        else:
            row.update({'Price': '—', '24h': 0, '7d': 0, '30d': 0, 'Mkt Cap': '—', 'Beta': 0})

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
        row['Sharpe'] = round(row.get('30d', 0) / (row['Vol'] or 1), 2) if row['Vol'] else 0
        rows.append(row)

    df_fresh = pd.DataFrame(rows)
    df_fresh['24h_display'] = df_fresh['24h'].apply(format_performance)
    df_fresh['7d_display'] = df_fresh['7d'].apply(format_performance)
    df_fresh['30d_display'] = df_fresh['30d'].apply(format_performance)
    return df_fresh


# Initial watchlist dataframe (from Eikon with fallback)
try:
    df = fetch_watchlist_data()
except Exception:
    all_stocks = [
        {'Ticker': m['Ticker'], 'Company': m['Company'], 'Sector': m['Sector'],
         'Price': '—', 'Mkt Cap': '—', '24h': 0, '7d': 0, '30d': 0, 'Vol': 0, 'Beta': 0, 'Corr': 0, 'Sharpe': 0}
        for m in WATCHLIST_META
    ]
    df = pd.DataFrame(all_stocks)
    df['24h_display'] = df['7d_display'] = df['30d_display'] = '—'
df['24h_display'] = df['24h'].apply(format_performance)
df['7d_display'] = df['7d'].apply(format_performance)
df['30d_display'] = df['30d'].apply(format_performance)

# Helper function to create article components
def create_article_component(article):
    return html.Div([
        # Article header
        html.Div([
            html.Div([
                html.Span(article['source'], style={
                    'font-weight': '700',
                    'color': '#8b4513',
                    'font-size': 'clamp(10px, 0.9vw, 12px)',
                    'text-transform': 'uppercase',
                    'letter-spacing': '0.5px',
                }),
                html.Span(' • ', style={'color': '#8b7355', 'margin': '0 4px'}),
                html.Span(article['date'], style={
                    'color': '#8b7355',
                    'font-size': 'clamp(9px, 0.8vw, 11px)',
                }),
            ], style={'display': 'flex', 'align-items': 'center'}),
            html.Div([
                html.Span(article['related_to'], style={
                    'background': '#d4c4b0',
                    'color': '#2c1810',
                    'padding': '2px 8px',
                    'border-radius': '4px',
                    'font-size': 'clamp(8px, 0.7vw, 10px)',
                    'font-weight': '600',
                    'margin-right': '6px',
                }),
                html.Span(article['impact'], style={
                    'background': '#e8dfd5',
                    'color': '#5c4a37',
                    'padding': '2px 8px',
                    'border-radius': '4px',
                    'font-size': 'clamp(8px, 0.7vw, 10px)',
                    'font-weight': '500',
                }),
            ], style={'display': 'flex', 'align-items': 'center'}),
        ], style={
            'display': 'flex',
            'justify-content': 'space-between',
            'align-items': 'center',
            'margin-bottom': '8px',
        }),
        
        # Article title
        html.H3(article['title'], style={
            'color': '#2c1810',
            'font-family': 'Arial, sans-serif',
            'font-size': 'clamp(13px, 1.2vw, 15px)',
            'font-weight': '600',
            'margin': '0 0 8px 0',
            'line-height': '1.4',
            'cursor': 'pointer',
        }),
        
        # Article summary
        html.P(article['summary'], style={
            'color': '#5c4a37',
            'font-family': 'Arial, sans-serif',
            'font-size': 'clamp(11px, 1vw, 13px)',
            'margin': '0',
            'line-height': '1.5',
        }),
    ], style={
        'padding': 'clamp(12px, 1.5vw, 16px)',
        'border-bottom': '1px solid #e8dfd5',
        'transition': 'background-color 0.2s',
    })

# Function to generate fresh articles with current date
def generate_fresh_articles():
    """Generate fresh market articles with today's date"""
    london_tz = pytz.timezone('Europe/London')
    today = datetime.now(london_tz)
    date_str = today.strftime('%b %d, %Y')
    
    # Stock News Articles (10 articles)
    stock_news = [
        {
            'title': 'NVIDIA Surges on Strong AI Chip Demand',
            'source': 'WSJ',
            'date': date_str,
            'related_to': 'NVDA',
            'impact': 'Stock Price',
            'summary': 'NVIDIA shares jumped 3.5% as demand for AI chips continues to outpace supply, with data center revenue hitting record highs.',
            'url': '#'
        },
        {
            'title': 'Tesla Stock Rallies on Strong Q4 Earnings Beat',
            'source': 'Bloomberg',
            'date': date_str,
            'related_to': 'TSLA',
            'impact': 'Stock Price',
            'summary': 'Tesla shares surged 4.3% after reporting better-than-expected quarterly earnings, driven by improved margins and strong delivery numbers.',
            'url': '#'
        },
        {
            'title': 'Apple Faces Regulatory Scrutiny in EU',
            'source': 'WSJ',
            'date': date_str,
            'related_to': 'AAPL',
            'impact': 'Stock Price',
            'summary': 'European regulators launch new investigation into Apple\'s App Store practices, causing concern among investors about potential fines.',
            'url': '#'
        },
        {
            'title': 'Energy Stocks Rise on Geopolitical Tensions',
            'source': 'Financial Times',
            'date': date_str,
            'related_to': 'XOM, CVX',
            'impact': 'Stock Price',
            'summary': 'Oil prices spike amid renewed Middle East tensions, lifting energy sector stocks as investors anticipate supply disruptions.',
            'url': '#'
        },
        {
            'title': 'Crypto Stocks Soar on Bitcoin ETF Inflows',
            'source': 'Bloomberg',
            'date': date_str,
            'related_to': 'COIN, MSTR',
            'impact': 'Stock Price',
            'summary': 'Record-breaking inflows into Bitcoin ETFs drive crypto-related stocks higher, with Coinbase and MicroStrategy leading gains.',
            'url': '#'
        },
        {
            'title': 'Microsoft Cloud Revenue Exceeds Expectations',
            'source': 'Reuters',
            'date': date_str,
            'related_to': 'MSFT',
            'impact': 'Stock Price',
            'summary': 'Microsoft shares gain 2.1% as Azure cloud services show stronger-than-expected growth, driven by enterprise adoption.',
            'url': '#'
        },
        {
            'title': 'Meta Announces New AI Initiatives',
            'source': 'WSJ',
            'date': date_str,
            'related_to': 'META',
            'impact': 'Stock Price',
            'summary': 'Meta shares decline 1.2% despite announcing new AI features, as investors remain cautious about ad revenue outlook.',
            'url': '#'
        },
        {
            'title': 'JPMorgan Reports Record Trading Revenue',
            'source': 'Bloomberg',
            'date': date_str,
            'related_to': 'JPM',
            'impact': 'Stock Price',
            'summary': 'JPMorgan shares rise 0.7% after reporting strong trading desk performance, offsetting concerns about loan defaults.',
            'url': '#'
        },
        {
            'title': 'Healthcare Stocks Rally on Drug Approval News',
            'source': 'Financial Times',
            'date': date_str,
            'related_to': 'UNH, JNJ',
            'impact': 'Stock Price',
            'summary': 'UnitedHealth and J&J shares climb as FDA approvals boost investor confidence in pharmaceutical pipelines.',
            'url': '#'
        },
        {
            'title': 'Defense Contractors Gain on Budget Increase',
            'source': 'Reuters',
            'date': date_str,
            'related_to': 'LMT, RTX',
            'impact': 'Stock Price',
            'summary': 'Lockheed and Raytheon shares advance as Congress approves increased defense spending for next fiscal year.',
            'url': '#'
        },
    ]
    
    # Market News Articles (10 articles)
    market_news = [
        {
            'title': 'Fed Signals Potential Rate Cuts Amid Economic Uncertainty',
            'source': 'WSJ',
            'date': date_str,
            'related_to': 'Yield Curve',
            'impact': 'Yield Curve',
            'summary': 'Federal Reserve officials hint at possible rate reductions later this year, causing the yield curve to flatten as short-term rates decline.',
            'url': '#'
        },
        {
            'title': 'Inflation Data Shows Cooling Trend, Bonds Rally',
            'source': 'Reuters',
            'date': date_str,
            'related_to': 'Yield Curve',
            'impact': 'Yield Curve',
            'summary': 'Latest CPI data indicates inflation is moderating faster than expected, leading to a rally in Treasury bonds across all maturities.',
            'url': '#'
        },
        {
            'title': '10-Year Treasury Yield Drops Below 4.5%',
            'source': 'WSJ',
            'date': date_str,
            'related_to': 'Yield Curve',
            'impact': 'Yield Curve',
            'summary': 'The benchmark 10-year Treasury yield fell to 4.45% as investors seek safe-haven assets amid global economic concerns.',
            'url': '#'
        },
        {
            'title': 'Dollar Strengthens on Fed Policy Outlook',
            'source': 'Bloomberg',
            'date': date_str,
            'related_to': 'Market',
            'impact': 'Yield Curve',
            'summary': 'US dollar gains against major currencies as markets price in more hawkish Fed stance, affecting global bond markets.',
            'url': '#'
        },
        {
            'title': 'Bond Market Volatility Reaches New Highs',
            'source': 'Financial Times',
            'date': date_str,
            'related_to': 'Yield Curve',
            'impact': 'Yield Curve',
            'summary': 'Treasury market volatility spikes as investors react to mixed economic signals and uncertainty about future rate path.',
            'url': '#'
        },
        {
            'title': 'Yield Curve Inversion Deepens',
            'source': 'WSJ',
            'date': date_str,
            'related_to': 'Yield Curve',
            'impact': 'Yield Curve',
            'summary': 'The 2-year/10-year yield spread widens further, signaling increased recession concerns among bond market participants.',
            'url': '#'
        },
        {
            'title': 'Central Banks Coordinate Policy Response',
            'source': 'Reuters',
            'date': date_str,
            'related_to': 'Market',
            'impact': 'Yield Curve',
            'summary': 'Major central banks signal coordinated approach to managing inflation, affecting global bond yields and currency markets.',
            'url': '#'
        },
        {
            'title': 'Treasury Auctions Show Strong Demand',
            'source': 'Bloomberg',
            'date': date_str,
            'related_to': 'Yield Curve',
            'impact': 'Yield Curve',
            'summary': 'Strong demand at recent Treasury auctions suggests continued investor appetite for safe-haven assets despite low yields.',
            'url': '#'
        },
        {
            'title': 'Mortgage Rates Decline on Bond Rally',
            'source': 'WSJ',
            'date': date_str,
            'related_to': 'Market',
            'impact': 'Yield Curve',
            'summary': '30-year mortgage rates fall to lowest level in months as Treasury yields decline, boosting housing market activity.',
            'url': '#'
        },
        {
            'title': 'Global Bond Markets React to US Data',
            'source': 'Financial Times',
            'date': date_str,
            'related_to': 'Yield Curve',
            'impact': 'Yield Curve',
            'summary': 'European and Asian bond markets follow US Treasuries higher as investors reassess global economic growth prospects.',
            'url': '#'
        },
    ]
    
    return {'stock_news': stock_news, 'market_news': market_news}

# Initialize market articles with current date
market_articles = generate_fresh_articles()

# Function to update articles (called by scheduler)
def update_articles_job():
    """Job function to update articles daily at 6 AM London time"""
    global market_articles
    market_articles = generate_fresh_articles()
    print(f"[{datetime.now()}] Articles updated at 6 AM London time")

# Set up scheduler to update articles at 6 AM London time daily
london_tz = pytz.timezone('Europe/London')
scheduler = BackgroundScheduler(timezone=london_tz)
scheduler.add_job(
    func=update_articles_job,
    trigger='cron',
    hour=6,
    minute=0,
    id='update_articles',
    name='Update market articles daily at 6 AM London time',
    replace_existing=True
)
scheduler.start()
print("Scheduler started: Articles will update daily at 6 AM London time")

# Helper function to create article components
def create_article_component(article):
    return html.Div([
        # Article header
        html.Div([
            html.Div([
                html.Span(article['source'], style={
                    'font-weight': '700',
                    'color': '#8b4513',
                    'font-size': 'clamp(10px, 0.9vw, 12px)',
                    'text-transform': 'uppercase',
                    'letter-spacing': '0.5px',
                }),
                html.Span(' • ', style={'color': '#8b7355', 'margin': '0 4px'}),
                html.Span(article['date'], style={
                    'color': '#8b7355',
                    'font-size': 'clamp(9px, 0.8vw, 11px)',
                }),
            ], style={'display': 'flex', 'align-items': 'center'}),
            html.Div([
                html.Span(article['related_to'], style={
                    'background': '#d4c4b0',
                    'color': '#2c1810',
                    'padding': '2px 8px',
                    'border-radius': '4px',
                    'font-size': 'clamp(8px, 0.7vw, 10px)',
                    'font-weight': '600',
                    'margin-right': '6px',
                }),
                html.Span(article['impact'], style={
                    'background': '#e8dfd5',
                    'color': '#5c4a37',
                    'padding': '2px 8px',
                    'border-radius': '4px',
                    'font-size': 'clamp(8px, 0.7vw, 10px)',
                    'font-weight': '500',
                }),
            ], style={'display': 'flex', 'align-items': 'center'}),
        ], style={
            'display': 'flex',
            'justify-content': 'space-between',
            'align-items': 'center',
            'margin-bottom': '8px',
        }),
        
        # Article title
        html.H3(article['title'], style={
            'color': '#2c1810',
            'font-family': 'Arial, sans-serif',
            'font-size': 'clamp(13px, 1.2vw, 15px)',
            'font-weight': '600',
            'margin': '0 0 8px 0',
            'line-height': '1.4',
            'cursor': 'pointer',
        }),
        
        # Article summary
        html.P(article['summary'], style={
            'color': '#5c4a37',
            'font-family': 'Arial, sans-serif',
            'font-size': 'clamp(11px, 1vw, 13px)',
            'margin': '0',
            'line-height': '1.5',
        }),
    ], style={
        'padding': 'clamp(12px, 1.5vw, 16px)',
        'border-bottom': '1px solid #e8dfd5',
        'transition': 'background-color 0.2s',
    })

# Create initial article components lists
stock_news_components = [create_article_component(article) for article in market_articles['stock_news']]
market_news_components = [create_article_component(article) for article in market_articles['market_news']]

# Custom CSS styling
app.layout = html.Div([
    # Hidden store to track articles update timestamp
    dcc.Store(id='articles-store', data={'timestamp': datetime.now().isoformat()}),
    # Interval to check for article updates every minute
    dcc.Interval(
        id='articles-interval',
        interval=60*1000,  # Check every minute
        n_intervals=0
    ),
    dcc.Interval(
        id='watchlist-interval',
        interval=10*1000,  # Refresh watchlist every 10 seconds
        n_intervals=0
    ),
    # Header
    html.Div([
        html.Div([
            html.H1('ARES', style={
                'color': '#2c1810',
                'font-family': 'Georgia, serif',
                'font-weight': '300',
                'letter-spacing': '8px',
                'margin': '0',
                'font-size': 'clamp(24px, 3vw, 36px)'
            }),
            html.P('Market Intelligence', style={
                'color': '#8b7355',
                'font-family': 'Arial, sans-serif',
                'margin': '5px 0 0 2px',
                'font-size': 'clamp(11px, 1vw, 13px)',
                'letter-spacing': '2px',
                'font-weight': '400'
            })
        ], style={'text-align': 'left'})
    ], style={
        'padding': 'clamp(20px, 2.5vw, 30px) clamp(25px, 3vw, 40px)',
        'background': 'linear-gradient(135deg, #f5f1ed 0%, #e8dfd5 100%)',
        'border-bottom': '2px solid #d4c4b0',
    }),
    
    # Main content
    html.Div([
        # Watchlist section
        html.Div([
            html.H2('Watch List', style={
                'color': '#2c1810',
                'font-family': 'Georgia, serif',
                'font-size': 'clamp(18px, 2vw, 22px)',
                'font-weight': '400',
                'margin': '0 0 20px 0',
                'letter-spacing': '1px'
            }),
            
            # Single unified table
            dash_table.DataTable(
                id='watchlist-table',
                columns=[
                    {'name': ['Info', 'Ticker'], 'id': 'Ticker'},
                    {'name': ['Info', 'Company'], 'id': 'Company'},
                    {'name': ['Info', 'Sector'], 'id': 'Sector'},
                    {'name': ['Valuation', 'Price'], 'id': 'Price'},
                    {'name': ['Valuation', 'Mkt Cap'], 'id': 'Mkt Cap'},
                    {'name': ['Performance', '24h'], 'id': '24h_display'},
                    {'name': ['Performance', '7d'], 'id': '7d_display'},
                    {'name': ['Performance', '30d'], 'id': '30d_display'},
                    {'name': ['Risk', 'Vol'], 'id': 'Vol'},
                    {'name': ['Risk', 'Beta'], 'id': 'Beta'},
                    {'name': ['Risk', 'Corr'], 'id': 'Corr'},
                    {'name': ['Risk', 'Sharpe'], 'id': 'Sharpe'},
                ],
                data=df.to_dict('records'),
                merge_duplicate_headers=True,
                sort_action='native',
                style_table={
                    'width': '100%',
                    'overflowX': 'hidden',
                },
                style_header={
                    'backgroundColor': '#d4c4b0',
                    'color': '#2c1810',
                    'fontWeight': '600',
                    'textAlign': 'center',
                    'border': 'none',
                    'borderBottom': '2px solid #b8a890',
                    'font-family': 'Arial, sans-serif',
                    'fontSize': 'clamp(9px, 0.8vw, 11px)',
                    'padding': '6px 3px',
                    'textTransform': 'uppercase',
                    'letterSpacing': '0.5px',
                },
                style_header_conditional=[],
                style_cell={
                    'backgroundColor': '#fefcfa',
                    'color': '#2c1810',
                    'border': 'none',
                    'borderBottom': '1px solid #e8dfd5',
                    'textAlign': 'center',
                    'font-family': 'Arial, sans-serif',
                    'fontSize': 'clamp(10px, 0.9vw, 12px)',
                    'padding': '6px 3px',
                    'minWidth': '55px',
                    'whiteSpace': 'normal',
                },
                style_cell_conditional=[
                    {
                        'if': {'column_id': 'Ticker'},
                        'fontWeight': '700',
                        'color': '#8b4513',
                        'textAlign': 'left',
                        'paddingLeft': '8px',
                        'paddingRight': '4px',
                        'fontSize': 'clamp(11px, 1vw, 13px)',
                        'width': '6%',
                        'borderLeft': '1px solid #e8dfd5'
                    },
                    {
                        'if': {'column_id': 'Company'},
                        'textAlign': 'left',
                        'paddingLeft': '4px',
                        'paddingRight': '4px',
                        'color': '#5c4a37',
                        'fontWeight': '500',
                        'width': '9%'
                    },
                    {
                        'if': {'column_id': 'Sector'},
                        'textAlign': 'center',
                        'paddingLeft': '4px',
                        'paddingRight': '8px',
                        'color': '#8b7355',
                        'fontWeight': '500',
                        'fontSize': 'clamp(9px, 0.8vw, 11px)',
                        'width': '7%'
                    },
                    {
                        'if': {'column_id': 'Price'},
                        'fontWeight': '600',
                        'color': '#2c1810',
                        'width': '9%',
                        'borderLeft': '1px solid #e8dfd5'
                    },
                    {
                        'if': {'column_id': 'Mkt Cap'},
                        'color': '#6b5744',
                        'width': '8%'
                    },
                    {
                        'if': {'column_id': ['24h_display', '7d_display', '30d_display']},
                        'width': '7%'
                    },
                    {
                        'if': {'column_id': '24h_display'},
                        'borderLeft': '1px solid #e8dfd5'
                    },
                    {
                        'if': {'column_id': ['Vol', 'Beta', 'Corr', 'Sharpe']},
                        'width': '6%',
                        'fontSize': 'clamp(9px, 0.8vw, 11px)'
                    },
                    {
                        'if': {'column_id': 'Vol'},
                        'borderLeft': '1px solid #e8dfd5'
                    },
                ],
                style_data_conditional=[
                    # Positive performance
                    {
                        'if': {
                            'filter_query': '{24h} > 0',
                            'column_id': '24h_display'
                        },
                        'color': '#2d7a3e',
                        'fontWeight': '600'
                    },
                    {
                        'if': {
                            'filter_query': '{7d} > 0',
                            'column_id': '7d_display'
                        },
                        'color': '#2d7a3e',
                        'fontWeight': '600'
                    },
                    {
                        'if': {
                            'filter_query': '{30d} > 0',
                            'column_id': '30d_display'
                        },
                        'color': '#2d7a3e',
                        'fontWeight': '600'
                    },
                    # Negative performance
                    {
                        'if': {
                            'filter_query': '{24h} < 0',
                            'column_id': '24h_display'
                        },
                        'color': '#b8473f',
                        'fontWeight': '600'
                    },
                    {
                        'if': {
                            'filter_query': '{7d} < 0',
                            'column_id': '7d_display'
                        },
                        'color': '#b8473f',
                        'fontWeight': '600'
                    },
                    {
                        'if': {
                            'filter_query': '{30d} < 0',
                            'column_id': '30d_display'
                        },
                        'color': '#b8473f',
                        'fontWeight': '600'
                    },
                    # Hover effect
                    {
                        'if': {'state': 'active'},
                        'backgroundColor': '#f5ede4',
                        'border': '1px solid #c9b59a'
                    },
                ],
            ),
        ], style={
            'background': 'linear-gradient(135deg, #ffffff 0%, #faf7f3 100%)',
            'padding': 'clamp(15px, 2vw, 25px)',
            'border-radius': '12px',
            'box-shadow': '0 2px 12px rgba(0,0,0,0.08)',
            'border': '1px solid #e8dfd5'
        }),
        
        # Treasury Yield Curve Section
        html.Div([
            html.H2('US Treasury Yield Curve', style={
                'color': '#2c1810',
                'font-family': 'Georgia, serif',
                'font-size': 'clamp(18px, 2vw, 22px)',
                'font-weight': '400',
                'margin': '0 0 12px 0',
                'letter-spacing': '1px'
            }),
            
            # Yield Curve Chart
            dcc.Graph(
                id='yield-curve-chart',
                figure={
                    'data': [
                        {
                            'x': ['1M', '3M', '6M', '1Y', '2Y', '3Y', '5Y', '7Y', '10Y', '20Y', '30Y'],
                            'y': [5.42, 5.38, 5.28, 4.95, 4.45, 4.28, 4.25, 4.32, 4.45, 4.72, 4.68],
                            'type': 'scatter',
                            'mode': 'lines+markers',
                            'line': {'color': '#8b4513', 'width': 3},
                            'marker': {'size': 8, 'color': '#8b4513'},
                            'fill': 'tozeroy',
                            'fillcolor': 'rgba(139, 69, 19, 0.1)',
                            'hovertemplate': '<b>%{x}</b><br>Yield: %{y:.2f}%<extra></extra>',
                        }
                    ],
                    'layout': {
                        'plot_bgcolor': '#fefcfa',
                        'paper_bgcolor': '#fefcfa',
                        'font': {'family': 'Arial, sans-serif', 'color': '#2c1810', 'size': 11},
                        'xaxis': {
                            'title': {'text': 'Maturity', 'font': {'size': 11}},
                            'gridcolor': '#e8dfd5',
                            'showgrid': True,
                            'zeroline': False,
                        },
                        'yaxis': {
                            'title': {'text': 'Yield (%)', 'font': {'size': 11}},
                            'gridcolor': '#e8dfd5',
                            'showgrid': True,
                            'zeroline': False,
                        },
                        'margin': {'l': 50, 'r': 20, 't': 10, 'b': 40},
                        'height': 250,
                        'hovermode': 'closest',
                    }
                },
                config={'displayModeBar': False}
            ),
            
            # Key Rates Table (no title)
            dash_table.DataTable(
                id='key-rates-table',
                columns=[
                    {'name': 'Maturity', 'id': 'Maturity'},
                    {'name': 'Rate', 'id': 'Rate'},
                    {'name': '1D', 'id': '1D'},
                    {'name': '1W', 'id': '1W'},
                    {'name': '1M', 'id': '1M'},
                    {'name': '3M', 'id': '3M'},
                ],
                data=[
                    {'Maturity': '2-Year', 'Rate': '4.45%', '1D': '+2', '1W': '-5', '1M': '+12', '3M': '+28'},
                    {'Maturity': '10-Year', 'Rate': '4.45%', '1D': '+3', '1W': '-3', '1M': '+15', '3M': '+32'},
                    {'Maturity': '30-Year', 'Rate': '4.68%', '1D': '+1', '1W': '-2', '1M': '+8', '3M': '+22'},
                ],
                style_table={
                    'width': '100%',
                    'overflowX': 'hidden',
                    'marginTop': '10px',
                },
                style_header={
                    'backgroundColor': '#d4c4b0',
                    'color': '#2c1810',
                    'fontWeight': '600',
                    'textAlign': 'center',
                    'border': 'none',
                    'borderBottom': '2px solid #b8a890',
                    'font-family': 'Arial, sans-serif',
                    'fontSize': 'clamp(8px, 0.7vw, 10px)',
                    'padding': '4px 3px',
                    'textTransform': 'uppercase',
                    'letterSpacing': '0.5px',
                },
                style_cell={
                    'backgroundColor': '#fefcfa',
                    'color': '#2c1810',
                    'border': 'none',
                    'borderBottom': '1px solid #e8dfd5',
                    'textAlign': 'center',
                    'font-family': 'Arial, sans-serif',
                    'fontSize': 'clamp(10px, 0.9vw, 12px)',
                    'padding': '5px 3px',
                },
                style_cell_conditional=[
                    {
                        'if': {'column_id': 'Maturity'},
                        'textAlign': 'left',
                        'fontWeight': '600',
                        'color': '#8b4513',
                        'paddingLeft': '10px',
                    },
                    {
                        'if': {'column_id': 'Rate'},
                        'fontWeight': '600',
                        'fontSize': 'clamp(11px, 1vw, 13px)',
                    },
                ],
                    style_data_conditional=[
                        # Positive changes (green)
                        {
                            'if': {
                                'filter_query': '{1D} contains "+"',
                                'column_id': '1D'
                            },
                            'color': '#2d7a3e',
                            'fontWeight': '600'
                        },
                        {
                            'if': {
                                'filter_query': '{1W} contains "+"',
                                'column_id': '1W'
                            },
                            'color': '#2d7a3e',
                            'fontWeight': '600'
                        },
                        {
                            'if': {
                                'filter_query': '{1M} contains "+"',
                                'column_id': '1M'
                            },
                            'color': '#2d7a3e',
                            'fontWeight': '600'
                        },
                        {
                            'if': {
                                'filter_query': '{3M} contains "+"',
                                'column_id': '3M'
                            },
                            'color': '#2d7a3e',
                            'fontWeight': '600'
                        },
                        # Negative changes (red)
                        {
                            'if': {
                                'filter_query': '{1D} contains "-"',
                                'column_id': '1D'
                            },
                            'color': '#b8473f',
                            'fontWeight': '600'
                        },
                        {
                            'if': {
                                'filter_query': '{1W} contains "-"',
                                'column_id': '1W'
                            },
                            'color': '#b8473f',
                            'fontWeight': '600'
                        },
                        {
                            'if': {
                                'filter_query': '{1M} contains "-"',
                                'column_id': '1M'
                            },
                            'color': '#b8473f',
                            'fontWeight': '600'
                        },
                        {
                            'if': {
                                'filter_query': '{3M} contains "-"',
                                'column_id': '3M'
                            },
                            'color': '#b8473f',
                            'fontWeight': '600'
                        },
                    ],
                ),
        ], style={
            'background': 'linear-gradient(135deg, #ffffff 0%, #faf7f3 100%)',
            'padding': 'clamp(12px, 1.5vw, 15px)',
            'border-radius': '12px',
            'box-shadow': '0 2px 12px rgba(0,0,0,0.08)',
            'border': '1px solid #e8dfd5',
            'width': '48%',
            'display': 'inline-block',
            'vertical-align': 'top',
            'margin-top': '20px',
        }),
        
        # News Articles Section - Two Columns
        html.Div([
            # Stock News Column
            html.Div([
                html.H2('Stock News', style={
                    'color': '#2c1810',
                    'font-family': 'Georgia, serif',
                    'font-size': 'clamp(18px, 2vw, 22px)',
                    'font-weight': '400',
                    'margin': '0 0 20px 0',
                    'letter-spacing': '1px'
                }),
                
                # Stock news articles container (will be updated by callback)
                html.Div(id='stock-news-container', children=stock_news_components, style={
                    'max-height': '600px',
                    'overflow-y': 'auto',
                }),
            ], style={
                'background': 'linear-gradient(135deg, #ffffff 0%, #faf7f3 100%)',
                'padding': 'clamp(15px, 2vw, 25px)',
                'border-radius': '12px',
                'box-shadow': '0 2px 12px rgba(0,0,0,0.08)',
                'border': '1px solid #e8dfd5',
                'margin-top': '20px',
                'flex': '1',
                'margin-right': 'clamp(10px, 1.5vw, 20px)',
            }),
            
            # Market News Column
            html.Div([
                html.H2('Market News', style={
                    'color': '#2c1810',
                    'font-family': 'Georgia, serif',
                    'font-size': 'clamp(18px, 2vw, 22px)',
                    'font-weight': '400',
                    'margin': '0 0 20px 0',
                    'letter-spacing': '1px'
                }),
                
                # Market news articles container (will be updated by callback)
                html.Div(id='market-news-container', children=market_news_components, style={
                    'max-height': '600px',
                    'overflow-y': 'auto',
                }),
            ], style={
                'background': 'linear-gradient(135deg, #ffffff 0%, #faf7f3 100%)',
                'padding': 'clamp(15px, 2vw, 25px)',
                'border-radius': '12px',
                'box-shadow': '0 2px 12px rgba(0,0,0,0.08)',
                'border': '1px solid #e8dfd5',
                'margin-top': '20px',
                'flex': '1',
            }),
        ], style={
            'width': '100%',
            'display': 'flex',
            'flex-direction': 'row',
            'gap': 'clamp(10px, 1.5vw, 20px)',
        }),
        
    ], style={
        'padding': 'clamp(20px, 2.5vw, 30px)',
        'max-width': '100%',
        'margin': '0 auto'
    }),
    
], style={
    'backgroundColor': '#f5f1ed',
    'min-height': '100vh',
    'font-family': 'Arial, sans-serif'
})

# Callback to update articles display periodically
@app.callback(
    [Output('stock-news-container', 'children'),
     Output('market-news-container', 'children')],
    Input('articles-interval', 'n_intervals')
)
def update_articles_display(n):
    """Update articles display when interval fires"""
    stock_components = [create_article_component(article) for article in market_articles['stock_news']]
    market_components = [create_article_component(article) for article in market_articles['market_news']]
    return stock_components, market_components


# Callback to refresh watchlist from Refinitiv
@app.callback(
    Output('watchlist-table', 'data'),
    Input('watchlist-interval', 'n_intervals')
)
def update_watchlist_data(n):
    """Refresh watchlist table data from Eikon."""
    try:
        df_fresh = fetch_watchlist_data()
        return df_fresh.to_dict('records')
    except Exception:
        return df.to_dict('records')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8051)
