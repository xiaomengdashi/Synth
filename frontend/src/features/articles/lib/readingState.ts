/** 阅读态纯函数:已读阈值只在此定义一处,后端只存原始 progress 不存派生布尔。 */

/** 已读判定阈值:进度 ≥ 0.95 视为读完(不拉到 100%,容许页脚余量)。 */
export const READ_DONE_THRESHOLD = 0.95;

/** 上报节流:距上次上报不足 2s 时,除非跨里程碑否则不报。 */
export const REPORT_INTERVAL_MS = 2000;

/** 里程碑步长:每推进 25% 强制上报一次,保证中途离开也能留下大致进度。 */
export const REPORT_MILESTONE_STEP = 0.25;

/** 已读 = 进度越过阈值(前端派生,避免后端双状态漂移)。 */
export function isRead(progress?: number): boolean {
  return (progress ?? 0) >= READ_DONE_THRESHOLD;
}

/** 进度值统一 clamp 到 0~1。 */
export function clampProgress(value: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

function crossedMilestone(prev: number, next: number): boolean {
  const epsilon = 1e-9; // 浮点累积误差下 0.25 边界可能算出 0.9999999
  return Math.floor(next / REPORT_MILESTONE_STEP + epsilon) > Math.floor(prev / REPORT_MILESTONE_STEP + epsilon);
}

/** 是否值得上报:只对单调前进的进度生效——距上次上报 ≥2s,或跨过 0.25 里程碑。 */
export function shouldReport(prev: number, next: number, elapsedMs: number): boolean {
  if (next <= prev) return false;
  if (elapsedMs >= REPORT_INTERVAL_MS) return true;
  return crossedMilestone(prev, next);
}

/** 是否首次读完:仅在跨越 0.95 边界那一次返回 true(0.9→0.96 真,0.96→0.97 假)。 */
export function shouldMarkRead(prev: number, next: number): boolean {
  return prev < READ_DONE_THRESHOLD && next >= READ_DONE_THRESHOLD;
}

/** 是否恢复上次阅读位置:读到一半(0.05<p<0.95)才恢复,未读/读完重进都回顶。 */
export function shouldRestore(progress?: number): boolean {
  const p = progress ?? 0;
  return p > 0.05 && p < READ_DONE_THRESHOLD;
}
