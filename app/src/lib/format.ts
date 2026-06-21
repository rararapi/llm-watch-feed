// Date helpers. published_at is ISO 8601 (UTC offset included).
export function parseDate(iso: string | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function dateLabel(iso: string | undefined): string {
  return (iso ?? "").slice(0, 10);
}
