import { useEffect, useMemo, useState } from 'react';
import './dashboard.css';
import { DASHBOARDS, RANGES, grafanaDashboardSource } from './dashboardConfig.js';

const SERVER_CLOCK_SYNC_MS = 60_000;

function formatServerTime(epochMs) {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(epochMs));
}

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState(DASHBOARDS[0]);
  const [range, setRange] = useState(RANGES[0].value);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [clock, setClock] = useState({ now: Date.now(), offset: 0, synced: false });
  const source = useMemo(() => grafanaDashboardSource(dashboard, range), [dashboard, range]);

  useEffect(() => {
    let active = true;

    const syncServerClock = async () => {
      const requestedAt = Date.now();
      try {
        const response = await fetch('/api/health', { cache: 'no-store' });
        const serverDate = Date.parse(response.headers.get('date') || '');
        if (!Number.isFinite(serverDate) || !active) return;
        const receivedAt = Date.now();
        const midpoint = requestedAt + ((receivedAt - requestedAt) / 2);
        setClock({ now: receivedAt, offset: serverDate - midpoint, synced: true });
      } catch {
        // Keep the visible clock running on local time until the next sync attempt.
      }
    };

    syncServerClock();
    const tick = window.setInterval(() => {
      setClock((current) => ({ ...current, now: Date.now() }));
    }, 1_000);
    const resync = window.setInterval(syncServerClock, SERVER_CLOCK_SYNC_MS);

    return () => {
      active = false;
      window.clearInterval(tick);
      window.clearInterval(resync);
    };
  }, []);

  const selectDashboard = (item) => {
    setDashboard(item);
    setLoading(true);
    setFailed(false);
  };

  const selectRange = (event) => {
    setRange(event.target.value);
    setLoading(true);
    setFailed(false);
  };

  return <main className="dashboard-page"><section className="dashboard-shell">
    <div className="dashboard-heading"><div><span>ADMIN ONLY</span><h1>보안 모니터링</h1><p>Grafana는 같은 사이트의 보호된 경로에서만 표시됩니다.</p></div><a href="/grafana/" target="_blank" rel="noreferrer">Grafana 새 창</a></div>
    <div className="dashboard-controls">
      <div className="dashboard-tabs">{DASHBOARDS.map((item) => <button key={item.key} className={item.key === dashboard.key ? 'active' : ''} onClick={() => selectDashboard(item)}>{item.label}</button>)}</div>
      <div className="dashboard-actions">
        <div className="dashboard-live" title={clock.synced ? '서버 HTTP Date 기준' : '서버 시간 동기화 중'}>
          <i aria-hidden="true" />
          <span>서버 시간 <b>{formatServerTime(clock.now + clock.offset)}</b></span>
          <span>자동 새로고침 <b>{dashboard.refresh}</b></span>
        </div>
        <label>조회 기간<select value={range} onChange={selectRange}>{RANGES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      </div>
    </div>
    <div className="dashboard-frame-wrap">{loading && <div className="dashboard-state">대시보드를 불러오는 중입니다.</div>}{failed && <div className="dashboard-state dashboard-error">Grafana에 연결하지 못했습니다. 잠시 후 다시 시도하세요.<button onClick={() => { setFailed(false); setLoading(true); }}>다시 시도</button></div>}<iframe title={`${dashboard.label} Grafana dashboard`} src={source} onLoad={() => setLoading(false)} onError={() => { setLoading(false); setFailed(true); }} className={loading || failed ? 'dashboard-frame is-hidden' : 'dashboard-frame'} /></div>
  </section></main>;
}
