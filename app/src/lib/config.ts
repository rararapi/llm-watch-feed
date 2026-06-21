// Runtime infra config. The data URL points at the public GCS bucket that serves
// the same models.json the web app and RSS feeds use (read-only, no auth/keys).
// Overridable via EXPO_PUBLIC_DATA_URL for local/dev pointing.
const DEFAULT_DATA_URL =
  "https://storage.googleapis.com/ai-watch-feed-llm-watch-public/data/models.json";

export const DATA_URL = process.env.EXPO_PUBLIC_DATA_URL ?? DEFAULT_DATA_URL;

// Base of the public bucket — used to build feed URLs on the subscribe screen.
export const FEEDS_BASE =
  process.env.EXPO_PUBLIC_FEEDS_BASE ??
  "https://storage.googleapis.com/ai-watch-feed-llm-watch-public/feeds";
