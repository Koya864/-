export function today(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

export function formatDate(date: Date | null | undefined): string {
  if (!date) return "-";
  return date.toLocaleDateString("ja-JP", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function formatMonthDay(date: Date): string {
  return date.toLocaleDateString("ja-JP", { month: "long", day: "numeric" });
}

/** from から見た日数差（未来なら正） */
export function daysBetween(from: Date, to: Date): number {
  const ms = to.getTime() - from.getTime();
  return Math.round(ms / (1000 * 60 * 60 * 24));
}

/** 記念日・誕生日の「次の到来日」を返す */
export function nextOccurrence(anniversary: Date, from: Date): Date {
  const next = new Date(anniversary);
  next.setHours(0, 0, 0, 0);
  next.setFullYear(from.getFullYear());
  if (next < from) next.setFullYear(from.getFullYear() + 1);
  return next;
}

/** 基準日時点の満年齢 */
export function ageAt(birthday: Date, at: Date): number {
  let age = at.getFullYear() - birthday.getFullYear();
  const m = at.getMonth() - birthday.getMonth();
  if (m < 0 || (m === 0 && at.getDate() < birthday.getDate())) age--;
  return age;
}

/** HTMLのdate inputの値 (YYYY-MM-DD) に変換 */
export function toInputValue(date: Date | null | undefined): string {
  if (!date) return "";
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
