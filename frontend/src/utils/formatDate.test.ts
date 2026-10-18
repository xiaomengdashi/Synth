import test from 'node:test';
import assert from 'node:assert/strict';
import { formatAbsolute, getServerTimeZone, setServerTimeZone } from './formatDate.ts';

test('display follows the server zone regardless of the browser zone', () => {
  const previous = process.env.TZ;
  try {
    for (const browserZone of ['UTC', 'Asia/Tokyo', 'America/Los_Angeles']) {
      process.env.TZ = browserZone;
      for (const [serverZone, expected] of [
        ['UTC', '2026-10-18 16:19'],
        ['Asia/Tokyo', '2026-10-19 01:19'],
        ['America/New_York', '2026-10-18 12:19'],
      ]) {
        setServerTimeZone(serverZone);
        assert.equal(formatAbsolute(new Date('2026-10-18T16:19:07.588523Z')), expected);
        assert.equal(formatAbsolute(new Date('2026-10-19T01:19:07+09:00')), expected);
      }
    }
    setServerTimeZone('America/New_York');
    assert.equal(formatAbsolute(new Date('2026-01-15T12:00:00Z')), '2026-01-15 07:00');
    assert.equal(formatAbsolute(new Date('2026-07-15T12:00:00Z')), '2026-07-15 08:00');
    assert.throws(() => setServerTimeZone('not-a-zone'));
    assert.equal(getServerTimeZone(), 'America/New_York');
  } finally {
    setServerTimeZone('UTC');
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
});

test('trend chart calendar days follow server date across DST boundaries', async () => {
  const { serverDayKey, recentServerDays } = await import('./formatDate.ts');
  try {
    setServerTimeZone('Asia/Tokyo');
    assert.equal(serverDayKey(new Date('2026-10-18T16:19:00Z')), '2026-10-19');
    setServerTimeZone('America/New_York');
    assert.deepEqual(recentServerDays(new Date('2026-11-02T03:30:00Z'), 3), ['2026-10-30', '2026-10-31', '2026-11-01']);
  } finally {
    setServerTimeZone('UTC');
  }
});
