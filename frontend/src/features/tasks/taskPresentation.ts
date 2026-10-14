export function summarizeTaskStep(value: string) {
  const firstLine = value.split(/\r?\n/, 1)[0]?.trim() || '';
  return firstLine.length > 180 ? `${firstLine.slice(0, 177)}…` : firstLine;
}
