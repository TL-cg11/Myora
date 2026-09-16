export const DASHBOARDS = [
  { key: 'events', label: '보안 이벤트', uid: 'luck-security-events' },
  { key: 'consumers', label: 'Consumer · 마스킹 로그', uid: 'luck-security-consumers' },
  { key: 'suricata', label: 'Suricata IDS', uid: 'luck-suricata-ids' },
];

export const RANGES = [
  { label: '최근 1시간', value: 'now-1h' },
  { label: '최근 6시간', value: 'now-6h' },
  { label: '최근 24시간', value: 'now-24h' },
];

export function grafanaDashboardSource(dashboard, range) {
  const refresh = dashboard.key === 'consumers' ? '5s' : '1m';
  return `/grafana/d/${dashboard.uid}/?kiosk&theme=light&from=${encodeURIComponent(range)}&to=now&refresh=${refresh}`;
}
