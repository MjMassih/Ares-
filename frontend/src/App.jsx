import { useState, useEffect, useCallback } from 'react';
import Watchlist from './components/Watchlist';
import YieldCurve from './components/YieldCurve';
import NewsColumn from './components/NewsColumn';
import './App.css';

const API = 'http://localhost:5001/api';

function usePolling(url, intervalMs) {
  const [data, setData] = useState(null);

  const fetchData = useCallback(() => {
    fetch(url)
      .then((r) => r.json())
      .then((fresh) => {
        setData((prev) => {
          if (!fresh || (Array.isArray(fresh) && fresh.length === 0)) return prev;
          return fresh;
        });
      })
      .catch(console.error);
  }, [url]);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, intervalMs);
    return () => clearInterval(id);
  }, [fetchData, intervalMs]);

  return data;
}

export default function App() {
  const watchlistRes = usePolling(`${API}/watchlist`, 10_000);
  const curve = usePolling(`${API}/yield-curve`, 30_000);
  const articles = usePolling(`${API}/articles`, 60_000);

  const watchlist = watchlistRes?.data || [];
  const loading = watchlist.length === 0;

  return (
    <div style={{ backgroundColor: '#f5f1ed', minHeight: '100vh' }}>
      <header className="header">
        <h1>ARES</h1>
        <p>Market Intelligence</p>
      </header>

      <main className="main">
        {loading ? (
          <div className="card" style={{ textAlign: 'center', padding: '40px', color: '#8b7355' }}>
            Loading watchlist data...
          </div>
        ) : (
          <Watchlist data={watchlist} />
        )}

        <YieldCurve curve={curve} />

        <div className="news-row">
          <NewsColumn title="Stock News" articles={articles?.stock_news || []} />
          <NewsColumn title="Market News" articles={articles?.market_news || []} />
        </div>
      </main>
    </div>
  );
}
