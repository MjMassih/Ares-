# Ares - Market Intelligence Dashboard

A personal financial dashboard featuring blue-chip stock tracking with valuation, performance, and risk metrics. Supplemented by a US Treasury yield curve visualization and live market/stock news from Refinitiv Eikon.

## Features

- **Equity Watchlist** -- real-time prices, 24h/7d/30d performance, volatility, beta, Sharpe ratio, and market cap across Technology, Consumer, Financials, Defense, Energy, Healthcare, and Crypto sectors
- **US Treasury Yield Curve** -- live 1M through 30Y yields rendered with Recharts
- **Live News** -- English-filtered headlines pulled from Refinitiv Eikon for both individual stocks and the broader rates/macro market, refreshed every 5 minutes
- **Auto-refresh** -- watchlist updates every 15 s, yield curve every 60 s, news every 5 min

## Tech Stack

| Layer | Stack |
|-------|-------|
| Frontend | React 19 + Vite, Recharts |
| Backend API | Flask, Flask-CORS |
| Data | Refinitiv Eikon Data API (`eikon`) |
| Scheduling | Custom background thread (single-threaded to avoid Eikon async clashes) |
| Language detection | `langdetect` (filters non-English headlines) |

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** and npm
- **Refinitiv Eikon Workspace** running on the same machine (the `eikon` library connects to it locally)

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/MjMassih/Ares-.git
   cd Ares-
   ```

2. **Create a `.env` file** in the project root with your Eikon app key:
   ```
   EIKON_APP_KEY=your_app_key_here
   ```

3. **Install Python dependencies:**
   ```bash
   pip install flask flask-cors eikon pandas numpy pytz langdetect
   ```

4. **Install frontend dependencies:**
   ```bash
   cd frontend
   npm install
   ```

## Running

Start both servers (from the project root):

```bash
# Terminal 1 -- API backend (port 5001)
python ares/api.py

# Terminal 2 -- React frontend (port 3000)
cd frontend && npx vite --port 3000
```

Open **http://localhost:3000** in your browser.

## Project Structure

```
Ares-/
├── .env                          # Eikon API key (not committed)
├── .gitignore
├── ares/
│   ├── api.py                    # Flask API: watchlist, yield curve, news
│   ├── dashboard.py              # Legacy Dash-based dashboard
│   ├── README.md
│   └── ares/Notebooks/
│       └── test_notebook.ipynb   # Exploratory notebook
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx               # Main app component + polling hooks
        ├── App.css               # Global styles
        ├── main.jsx
        └── components/
            ├── Watchlist.jsx     # Equity table
            ├── YieldCurve.jsx    # Treasury curve chart
            └── NewsColumn.jsx    # Live headlines column
```

## Design

Professional hedge-fund aesthetic with a warm tan/beige palette, information-dense layout, and responsive scaling.

---

Built for market intelligence.
