# Ares - Market Intelligence Dashboard

A personal financial dashboard which includes blue chip stocks, following their valuation, performance, and risk. Supplementing this dashboard is a yield curve visualization for the 2,10, and 30Y Treasury Yields with a market/stock news extrapolator for contextual insights.

## Features

- **Watchlist Table**: Track multiple stocks across different sectors (Technology, Consumer, Financials, Defense, Energy, Healthcare, Crypto)
- **US Treasury Yield Curve**: Visualize the current yield curve with key rates and historical changes
- **Live News Headlines**: English-filtered stock and market news pulled from Refinitiv Eikon, refreshed every 5 minutes
- **Responsive Design**: Fully scalable interface that adapts to your browser size
- **Performance Metrics**: Monitor 24h, 7d, and 30d performance across your portfolio
- **Risk Analysis**: View volatility, beta, correlation, and Sharpe ratios
- **Auto-Refresh**: Watchlist updates every 15s, yield curve every 60s, news every 5 min

## Tech Stack

- **Python 3.10+**
- **React 19** + **Vite** - Frontend framework and build tool
- **Recharts** - Charting library
- **Flask** - API backend
- **Refinitiv Eikon** - Financial data retrieval (real-time, via Eikon Workspace desktop)
- **Pandas** - Data manipulation

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

5. **Eikon Workspace must be running** on the same machine. The `eikon` library connects to it locally for authentication.

## Running the Dashboard

1. Start the API backend:
   ```bash
   python ares/api.py
   ```

2. Start the React frontend:
   ```bash
   cd frontend && npx vite --port 3000
   ```

3. Open your browser and navigate to:
   ```
   http://localhost:3000
   ```

## Project Structure

```
ares/
├── ares/
│   ├── api.py                    # Flask API: watchlist, yield curve, news
│   ├── dashboard.py              # Legacy Dash-based dashboard
│   ├── ares/
│   │   └── Notebooks/
│   │       └── test_notebook.ipynb
│   └── README.md
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx               # Main app component + polling hooks
│       ├── App.css               # Global styles
│       ├── main.jsx
│       └── components/
│           ├── Watchlist.jsx     # Equity table
│           ├── YieldCurve.jsx    # Treasury curve chart
│           └── NewsColumn.jsx    # Live headlines column
└── .gitignore
```

## Features in Development

- Additional charting components
- Click-through stock details
- Portfolio analytics
- Alert notifications

## Design Philosophy

The dashboard is designed with a professional, hedge fund-style aesthetic featuring:
- Warm tan and beige color palette
- Tight, information-dense layouts
- Clean typography and spacing
- Responsive scaling for different screen sizes

---


