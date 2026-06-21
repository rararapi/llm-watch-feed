// Copy the backend-generated shared/meta.json into the app bundle as a build-time
// import. The single source of truth for display constants is the repo-root
// shared/meta.json produced by scripts/generate_pages.py — this script only mirrors
// it into src/generated/meta.json so the app can import it without a Python step.
// Run before build/start (npm run sync-meta). If the shared file is absent (fresh
// checkout without a site generation), the existing committed copy is kept.
import { existsSync, copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../../shared/meta.json");
const dest = resolve(here, "../src/generated/meta.json");

if (!existsSync(src)) {
  console.warn(`[sync-meta] ${src} not found — keeping existing ${dest}`);
  process.exit(0);
}
mkdirSync(dirname(dest), { recursive: true });
copyFileSync(src, dest);
console.log(`[sync-meta] ${src} -> ${dest}`);
