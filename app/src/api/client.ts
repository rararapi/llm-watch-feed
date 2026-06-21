// Fetches the public models.json and exposes it via TanStack Query.
// On network failure, falls back to the offline cache so the last data still shows.
import { useQuery } from "@tanstack/react-query";
import { DATA_URL } from "@/lib/config";
import type { Article } from "@/types/article";
import { loadArticles, saveArticles } from "@/api/storage";

// Drop duplicate ids — the source data can contain the same article (same URL hash)
// more than once, which would collide as React list keys and duplicate rows.
function dedupeById(articles: Article[]): Article[] {
  const seen = new Set<string>();
  return articles.filter((a) => {
    if (!a.id || seen.has(a.id)) return false;
    seen.add(a.id);
    return true;
  });
}

async function fetchArticles(): Promise<Article[]> {
  const res = await fetch(DATA_URL);
  if (!res.ok) throw new Error(`Failed to fetch articles: HTTP ${res.status}`);
  const data = (await res.json()) as Article[];
  // Only A/B are shown (matches the web; C is excluded from normal feeds).
  const visible = dedupeById(data.filter((a) => a.importance === "A" || a.importance === "B"));
  await saveArticles(visible);
  return visible;
}

export function useArticles() {
  return useQuery({
    queryKey: ["articles"],
    queryFn: async () => {
      try {
        return await fetchArticles();
      } catch (err) {
        const cached = await loadArticles();
        if (cached && cached.length > 0) return cached;
        throw err;
      }
    },
    staleTime: 5 * 60 * 1000,
    retry: 2,
  });
}

export function useArticle(id: string | undefined) {
  const q = useArticles();
  const article = q.data?.find((a) => a.id === id);
  return { ...q, article };
}
