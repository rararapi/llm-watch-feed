// Filtering + date grouping. Mirrors the web behaviour:
// - filtering: assets/site/js/app.js (importance / source / keyword, AND-combined)
// - grouping:  generate_pages.py _recency_group / _group_articles (today / week / earlier)
import type { Article, Importance } from "@/types/article";
import { parseDate } from "@/lib/format";

export interface FilterState {
  importance: Importance | "all";
  source: string | "all";
  query: string;
}

export const INITIAL_FILTER: FilterState = {
  importance: "all",
  source: "all",
  query: "",
};

function haystack(a: Article): string {
  return [
    a.title,
    a.summary,
    a.impact,
    a.action,
    a.source,
    a.model_name,
    a.model_type,
    ...(a.tags ?? []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function matches(a: Article, f: FilterState): boolean {
  const okImp = f.importance === "all" || (a.importance ?? "C") === f.importance;
  const okSrc = f.source === "all" || a.source === f.source;
  const q = f.query.trim().toLowerCase();
  const okQ = q === "" || haystack(a).includes(q);
  return okImp && okSrc && okQ;
}

export function filterArticles(articles: Article[], f: FilterState): Article[] {
  return articles.filter((a) => matches(a, f));
}

// Unique source list present in the data (for the source picker), sorted.
export function sourcesOf(articles: Article[]): string[] {
  return Array.from(new Set(articles.map((a) => a.source).filter(Boolean))).sort();
}

export type RecencyKey = "today" | "week" | "earlier";

export interface DateGroup {
  key: RecencyKey;
  label: string;
  articles: Article[];
}

function recencyKey(iso: string | undefined, now: Date): RecencyKey {
  const d = parseDate(iso);
  if (!d) return "earlier";
  const days = Math.floor((now.getTime() - d.getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days <= 7) return "week";
  return "earlier";
}

const GROUP_LABELS: Record<RecencyKey, string> = {
  today: "今日",
  week: "今週",
  earlier: "それ以前",
};

// Sort by published_at desc, then bucket into recency groups (empty groups dropped).
export function groupByRecency(articles: Article[], now: Date = new Date()): DateGroup[] {
  const sorted = [...articles].sort((a, b) =>
    (b.published_at ?? "").localeCompare(a.published_at ?? ""),
  );
  const order: RecencyKey[] = ["today", "week", "earlier"];
  return order
    .map((key) => ({
      key,
      label: GROUP_LABELS[key],
      articles: sorted.filter((a) => recencyKey(a.published_at, now) === key),
    }))
    .filter((g) => g.articles.length > 0);
}
