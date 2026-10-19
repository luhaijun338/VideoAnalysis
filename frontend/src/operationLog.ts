export function formatClock(tStartMs: number): string {
  const totalSec = Math.floor(tStartMs / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function compactText(text: string, maxChars = 80): string {
  const compact = text.trim().split(/\s+/).join(" ");
  if (!compact) return "";
  if (compact.length <= maxChars) return compact;
  return compact.slice(0, maxChars - 1) + "…";
}

export function hitCaptionBody(caption: string, ocrText: string): string {
  return caption.trim() || compactText(ocrText) || "（无描述）";
}

export function formatOperationLogLine(
  tStartMs: number,
  caption: string,
  ocrText: string,
): string {
  return `[${formatClock(tStartMs)}] ${hitCaptionBody(caption, ocrText)}`;
}
