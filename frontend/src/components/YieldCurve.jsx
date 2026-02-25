import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

const posCls = (v) => (typeof v === 'string' && v.startsWith('+') ? 'positive' : '');
const negCls = (v) => (typeof v === 'string' && v.startsWith('-') ? 'negative' : '');
const changeCls = (v) => posCls(v) || negCls(v);

export default function YieldCurve({ curve }) {
  if (!curve) return null;

  const chartData = curve.maturities.map((m, i) => ({
    maturity: m,
    yield: curve.yields[i],
  }));

  return (
    <div className="yield-section">
      <div className="card">
        <h2 className="section-title">US Treasury Yield Curve</h2>

        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={chartData} margin={{ left: 0, right: 10, top: 5, bottom: 5 }}>
            <CartesianGrid stroke="#e8dfd5" />
            <XAxis dataKey="maturity" tick={{ fill: '#2c1810', fontSize: 11 }} />
            <YAxis tick={{ fill: '#2c1810', fontSize: 11 }} domain={['auto', 'auto']}
                   label={{ value: 'Yield (%)', angle: -90, position: 'insideLeft', fill: '#2c1810', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: '#fefcfa', border: '1px solid #d4c4b0', borderRadius: 6 }}
              formatter={(v) => [`${v.toFixed(2)}%`, 'Yield']}
            />
            <Area type="monotone" dataKey="yield" stroke="#8b4513" strokeWidth={3}
                  fill="rgba(139,69,19,.1)" dot={{ r: 5, fill: '#8b4513' }} />
          </AreaChart>
        </ResponsiveContainer>

        <table className="rates-table">
          <thead>
            <tr>
              <th>Maturity</th><th>Rate</th><th>1D</th><th>1W</th><th>1M</th><th>3M</th>
            </tr>
          </thead>
          <tbody>
            {curve.key_rates.map((r) => (
              <tr key={r.Maturity}>
                <td className="col-maturity">{r.Maturity}</td>
                <td className="col-rate">{r.Rate}</td>
                <td className={changeCls(r.D1)}>{r.D1}</td>
                <td className={changeCls(r.W1)}>{r.W1}</td>
                <td className={changeCls(r.M1)}>{r.M1}</td>
                <td className={changeCls(r.M3)}>{r.M3}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
