// 4.4 検証補助: アプリが読み込むデータ(既定=公開バケット)に対して、
// Web(app.js)とアプリ(filter.ts)が同じ絞り込み・グルーピング結果になることを
// 件数レベルで突き合わせ、実機確認用の「期待件数表」を出力する。
//
//   node scripts/filter-parity.mjs                       # 公開バケットのデータで確認
//   node scripts/filter-parity.mjs ../docs/data/models.json   # ローカルデータで確認
//
// 注: filter.ts と同じロジックをここに写経している（TSをNodeで直接実行しないため）。
// アプリ本体の filter.ts は tsc/Metro で検証済み。本スクリプトは Web ルールとの一致と
// 実機で突き合わせる期待値を出すのが目的。

const DEFAULT_URL =
  "https://storage.googleapis.com/ai-watch-feed-llm-watch-public/data/models.json";

const arg = process.argv[2];

async function load() {
  if (arg && !arg.startsWith("http")) {
    const { readFileSync } = await import("node:fs");
    return JSON.parse(readFileSync(arg, "utf-8"));
  }
  const res = await fetch(arg || DEFAULT_URL);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// --- app(filter.ts) ルール ---
const visible = (a) => a.importance === "A" || a.importance === "B"; // client.ts と同じ
function haystack(a) {
  return [a.title, a.summary, a.impact, a.action, a.source, a.model_name, a.model_type, ...(a.tags || [])]
    .filter(Boolean).join(" ").toLowerCase();
}
function appMatch(a, f) {
  const okImp = f.importance === "all" || (a.importance || "C") === f.importance;
  const okSrc = f.source === "all" || a.source === f.source;
  const q = (f.query || "").trim().toLowerCase();
  return okImp && okSrc && (q === "" || haystack(a).includes(q));
}

// --- web(app.js) ルール（card.textContent + data-tags の部分一致 / data-importance / data-source）---
function webMatch(a, f) {
  const okImp = f.importance === "all" || (a.importance || "C") === f.importance;
  const okSrc = f.source === "all" || (a.source || "") === f.source;
  const q = (f.query || "").trim().toLowerCase();
  const hay = haystack(a); // カードに描画される本文＋タグ相当
  return okImp && okSrc && (q === "" || hay.includes(q));
}

function recency(iso, now) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "earlier";
  const days = Math.floor((now - d.getTime()) / 86400000);
  return days <= 0 ? "today" : days <= 7 ? "week" : "earlier";
}

const all = await load();
const ab = all.filter(visible);
const sources = [...new Set(ab.map((a) => a.source).filter(Boolean))].sort();
const now = Date.now();

console.log(`データ件数: 全${all.length} / 表示対象(A,B)=${ab.length}`);
console.log(`ソース数: ${sources.length}`);

const filters = [
  { importance: "all", source: "all", query: "" },
  { importance: "A", source: "all", query: "" },
  { importance: "B", source: "all", query: "" },
];
for (const s of sources) filters.push({ importance: "all", source: s, query: "" });

let mismatch = 0;
console.log("\n=== 期待件数（実機でこの数字と一致するか確認）===");
for (const f of filters) {
  const app = ab.filter((a) => appMatch(a, f)).length;
  const web = ab.filter((a) => webMatch(a, f)).length;
  const label = `importance=${f.importance} source=${f.source}`;
  const flag = app === web ? "" : "  <<< 不一致!";
  if (app !== web) mismatch++;
  console.log(`  ${label.padEnd(40)} app=${app} web=${web}${flag}`);
}

const groups = { today: 0, week: 0, earlier: 0 };
for (const a of ab) groups[recency(a.published_at, now)]++;
console.log("\n=== 日付グループ（今日/今週/それ以前）===");
console.log(`  今日=${groups.today}  今週=${groups.week}  それ以前=${groups.earlier}`);

console.log(`\n結果: ${mismatch === 0 ? "Web/アプリのロジック一致 ✓" : `不一致 ${mismatch} 件 ✗`}`);
process.exit(mismatch === 0 ? 0 : 1);
