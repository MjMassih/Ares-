function formatDate(raw) {
  if (!raw) return '';
  try {
    const d = new Date(raw);
    if (isNaN(d)) return raw;
    return d.toLocaleString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', hour12: false,
    });
  } catch {
    return raw;
  }
}

export default function NewsColumn({ title, articles }) {
  return (
    <div className="news-col">
      <div className="card">
        <h2 className="section-title">{title}</h2>
        <div className="news-scroll">
          {articles.length === 0 && (
            <div style={{ padding: '20px', color: '#8b7355', textAlign: 'center' }}>
              Loading headlines...
            </div>
          )}
          {articles.map((a, i) => (
            <div className="article" key={a.storyId || i}>
              <div className="article-header">
                <div className="article-meta">
                  <span className="article-source">{a.source}</span>
                  <span className="article-dot"> • </span>
                  <span className="article-date">{formatDate(a.date)}</span>
                </div>
                <div className="article-tags">
                  <span className="tag-ticker">{a.related_to}</span>
                  <span className="tag-impact">{a.impact}</span>
                </div>
              </div>
              <h3>{a.title}</h3>
              {a.summary && a.summary !== a.title && (
                <p>{a.summary}</p>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
