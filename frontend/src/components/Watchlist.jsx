const fmt = (v) => (v > 0 ? `+${v}%` : `${v}%`);
const cls = (v) => (v > 0 ? 'positive' : v < 0 ? 'negative' : '');

const GROUPS = [
  { label: 'Info', cols: ['Ticker', 'Company', 'Sector'] },
  { label: 'Valuation', cols: ['Price', 'Mkt Cap'] },
  { label: 'Performance', cols: ['24h', '7d', '30d'] },
  { label: 'Risk', cols: ['Vol', 'Beta', 'Corr', 'Sharpe'] },
];

export default function Watchlist({ data }) {
  return (
    <div className="card" style={{ marginBottom: 0 }}>
      <h2 className="section-title">Watch List</h2>
      <table className="watchlist-table">
        <thead>
          <tr>
            {GROUPS.map((g) => (
              <th key={g.label} colSpan={g.cols.length} className="group-header">
                {g.label}
              </th>
            ))}
          </tr>
          <tr>
            {GROUPS.flatMap((g) =>
              g.cols.map((c) => <th key={c}>{c}</th>)
            )}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.Ticker}>
              <td className="col-ticker">{row.Ticker}</td>
              <td className="col-company">{row.Company}</td>
              <td className="col-sector">{row.Sector}</td>
              <td className="col-price">{row.Price}</td>
              <td className="col-mktcap">{row.MktCap}</td>
              <td className={`col-perf-start ${cls(row.h24)}`}>{fmt(row.h24)}</td>
              <td className={cls(row.d7)}>{fmt(row.d7)}</td>
              <td className={cls(row.d30)}>{fmt(row.d30)}</td>
              <td className="col-risk col-risk-start">{row.Vol}</td>
              <td className="col-risk">{row.Beta}</td>
              <td className="col-risk">{row.Corr}</td>
              <td className="col-risk">{row.Sharpe}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
