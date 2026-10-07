import test from 'node:test';
import assert from 'node:assert/strict';
import {
  READ_DONE_THRESHOLD,
  REPORT_INTERVAL_MS,
  clampProgress,
  isRead,
  shouldMarkRead,
  shouldReport,
  shouldRestore,
} from './readingState.ts';

test('isRead 只在进度越过阈值时为真', () => {
  assert.equal(READ_DONE_THRESHOLD, 0.95);
  assert.equal(isRead(0.949), false);
  assert.equal(isRead(0.95), true);
  assert.equal(isRead(1), true);
  assert.equal(isRead(undefined), false);
  assert.equal(isRead(0), false);
});

test('clampProgress 把任意数值压回 0~1', () => {
  assert.equal(clampProgress(-1), 0);
  assert.equal(clampProgress(1.5), 1);
  assert.equal(clampProgress(0.3), 0.3);
  assert.equal(clampProgress(0), 0);
  assert.equal(clampProgress(Number.NaN), 0);
});

test('shouldReport 按 2s 节流,跨 0.25 里程碑立即放行,回退不报', () => {
  assert.equal(REPORT_INTERVAL_MS, 2000);
  // 未到 2s 且未跨里程碑:不报
  assert.equal(shouldReport(0.1, 0.12, 1000), false);
  // 到 2s:报
  assert.equal(shouldReport(0.1, 0.12, 2000), true);
  assert.equal(shouldReport(0.1, 0.12, 3000), true);
  // 未到 2s 但跨过 0.25 边界:报
  assert.equal(shouldReport(0.24, 0.26, 100), true);
  assert.equal(shouldReport(0.49, 0.51, 500), true);
  // 恰好落在里程碑上(0.25/0.5 本身算已跨入):报
  assert.equal(shouldReport(0.24, 0.25, 100), true);
  // 进度不前进:即使到时也不报
  assert.equal(shouldReport(0.3, 0.3, 5000), false);
  assert.equal(shouldReport(0.4, 0.32, 5000), false);
});

test('shouldMarkRead 仅在跨越 0.95 边界那一次为真', () => {
  assert.equal(shouldMarkRead(0.9, 0.96), true);
  assert.equal(shouldMarkRead(0.96, 0.97), false);
  assert.equal(shouldMarkRead(0.9, 0.9), false);
  assert.equal(shouldMarkRead(0.95, 1), false);
  assert.equal(shouldMarkRead(0, 0.95), true);
});

test('shouldRestore 只对读到一半的进度恢复位置', () => {
  assert.equal(shouldRestore(undefined), false);
  assert.equal(shouldRestore(0), false);
  assert.equal(shouldRestore(0.03), false);
  assert.equal(shouldRestore(0.05), false);
  assert.equal(shouldRestore(0.5), true);
  assert.equal(shouldRestore(0.94), true);
  assert.equal(shouldRestore(0.95), false);
  assert.equal(shouldRestore(1), false);
});
