import assert from 'node:assert/strict';
import test from 'node:test';
import { DASHBOARDS, grafanaDashboardSource } from './dashboardConfig.js';

test('admin dashboard exposes tab-specific refresh intervals', () => {
  assert.deepEqual(DASHBOARDS.map(({ key, uid, refresh }) => ({ key, uid, refresh })), [
    { key: 'events', uid: 'luck-security-events', refresh: '1m' },
    { key: 'consumers', uid: 'luck-security-consumers', refresh: '5s' },
    { key: 'suricata', uid: 'luck-suricata-ids', refresh: '1m' },
  ]);
});

test('Grafana iframe source preserves the selected range', () => {
  assert.equal(
    grafanaDashboardSource(DASHBOARDS[2], 'now-24h'),
    '/grafana/d/luck-suricata-ids/?kiosk&theme=light&from=now-24h&to=now&refresh=1m',
  );
  assert.equal(
    grafanaDashboardSource(DASHBOARDS[1], 'now-1h'),
    '/grafana/d/luck-security-consumers/?kiosk&theme=light&from=now-1h&to=now&refresh=5s',
  );
});
