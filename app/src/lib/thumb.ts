// Thumbnail priority — matches the web (generate_pages.py _thumb / _hero, macros.html):
// AI-generated image → original article OG image → null (caller shows a color placeholder).
import type { Article } from "@/types/article";

export function thumbUrl(a: Article): string | null {
  return a.image_generated_url || a.image_url || null;
}
