// Display constants resolved from the backend-generated shared meta (build-time import).
// Single source of truth is scripts/generate_pages.py; do not hardcode equivalents here.
import metaJson from "@/generated/meta.json";
import type { SharedMeta } from "@/types/meta";

export const meta = metaJson as SharedMeta;

// Placeholder hue from a source name — same formula as the backend (md5-based),
// so app placeholders match the web. Implemented without a crypto dep using the
// hues precomputed in meta.json; falls back to a small local hash for unknown sources.
const hueBySource: Record<string, number> = Object.fromEntries(
  meta.sources.map((s) => [s.name, s.hue]),
);

function fallbackHue(source: string): number {
  let h = 0;
  for (let i = 0; i < source.length; i++) {
    h = (h * 31 + source.charCodeAt(i)) >>> 0;
  }
  return h % 360;
}

export function sourceHue(source: string | undefined | null): number {
  const s = source || "AI";
  return hueBySource[s] ?? fallbackHue(s);
}

// Two-stop gradient colors matching the web placeholder (styles.css --ph-hue).
export function sourceColors(source: string | undefined | null): [string, string] {
  const hue = sourceHue(source);
  const { saturation: sat, lightness: lit } = meta.placeholder;
  return [`hsl(${hue}, ${sat}%, ${lit}%)`, `hsl(${(hue + 36) % 360}, ${sat}%, ${lit - 12}%)`];
}

export function importanceLabel(importance: string | undefined): string {
  if (!importance) return "-";
  return meta.importance[importance]?.label ?? importance;
}

export function modelTypeLabel(modelType: string | undefined): string | undefined {
  if (!modelType) return undefined;
  return meta.model_types[modelType] ?? modelType;
}
