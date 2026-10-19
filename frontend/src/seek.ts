export function seekSeconds(tStartMs: number, leadMs = 1000): number {
  return Math.max(0, tStartMs - leadMs) / 1000;
}
