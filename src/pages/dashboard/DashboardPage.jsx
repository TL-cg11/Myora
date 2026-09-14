import { useMemo, useState } from 'react';
import './dashboard.css';
import { DASHBOARDS, RANGES, grafanaDashboardSource } from './dashboardConfig.js';

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState(DASHBOARDS[0]);
  const [range, setRange] = useState(RANGES[0].value);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const source = useMemo(() => grafanaDashboardSource(dashboard, range), [dashboard, range]);
  return <main className="dashboard-page"><section className="dashboard-shell">
    <div className="dashboard-heading"><div><span>ADMIN ONLY</span><h1>보안 모니터링</h1><p>Grafana는 같은 사이트의 보호된 경로에서만 표시됩니다.</p></div><a href="/grafana/" target="_blank" rel="noreferrer">Grafana 새 창</a></div>
    <div className="dashboard-controls"><div className="dashboard-tabs">{DASHBOARDS.map((item) => <button key={item.key} className={item.key === dashboard.key ? 'active' : ''} onClick={() => { setDashboard(item); setLoading(true); setFailed(false); }}>{item.label}</button>)}</div><label>조회 기간<select value={range} onChange={(event) => { setRange(event.target.value); setLoading(true); setFailed(false); }}>{RANGES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label></div>
    <div className="dashboard-frame-wrap">{loading && <div className="dashboard-state">대시보드를 불러오는 중입니다.</div>}{failed && <div className="dashboard-state dashboard-error">Grafana에 연결하지 못했습니다. 잠시 후 다시 시도하세요.<button onClick={() => { setFailed(false); setLoading(true); }}>다시 시도</button></div>}<iframe title={`${dashboard.label} Grafana dashboard`} src={source} onLoad={() => setLoading(false)} onError={() => { setLoading(false); setFailed(true); }} className={loading || failed ? 'dashboard-frame is-hidden' : 'dashboard-frame'} /></div>
  </section></main>;
}
