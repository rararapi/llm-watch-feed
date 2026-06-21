// Mirrors the models.json schema (see AGENTS.md「データスキーマ」). The backend is the
// source of truth; keep this in sync when the schema changes (same monorepo, same PR).
export type Importance = "A" | "B" | "C";

export interface Article {
  id: string;
  title: string;
  url: string;
  source: string;
  published_at: string;
  collected_at?: string;

  image_url?: string | null;
  image_generated_url?: string | null;
  image_generated_alt?: string | null;
  image_generated_prompt?: string | null;

  is_model_related?: boolean;
  model_relevance_reason?: string;

  model_name?: string;
  provider?: string;
  model_type?: string;
  summary?: string;
  impact?: string;
  action?: string;
  importance?: Importance;
  tags?: string[];
  language?: string;
}
