// AI News Watch — client-side filtering (importance / source / keyword) + copy buttons.
// Cards are server-rendered with data-* attributes; JS only toggles visibility.
(function () {
  "use strict";

  // ---- Copy buttons (RSS URLs, share link) ----
  function bindCopyButtons() {
    document.querySelectorAll(".copy-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var text = btn.getAttribute("data-copy") || "";
        var done = function () {
          var original = btn.textContent;
          btn.textContent = "コピー済み";
          btn.classList.add("is-copied");
          setTimeout(function () {
            btn.textContent = original;
            btn.classList.remove("is-copied");
          }, 1400);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done).catch(function () { fallbackCopy(text, done); });
        } else {
          fallbackCopy(text, done);
        }
      });
    });
  }

  function fallbackCopy(text, done) {
    var ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
    done();
  }

  // ---- Filtering ----
  function initFilters() {
    var list = document.getElementById("news-list");
    if (!list) return;

    var cards = Array.prototype.slice.call(list.querySelectorAll(".card"));
    var groups = Array.prototype.slice.call(list.querySelectorAll(".news-group"));
    var noResults = document.getElementById("no-results");
    var countEl = document.getElementById("result-count");
    var sourceSel = document.getElementById("filter-source");
    var searchEl = document.getElementById("filter-search");
    var segBtns = Array.prototype.slice.call(document.querySelectorAll("[data-filter-importance]"));

    var state = { importance: "all", source: "all", q: "" };

    function apply() {
      var visible = 0;
      var q = state.q.trim().toLowerCase();
      cards.forEach(function (card) {
        var okImp = state.importance === "all" || card.getAttribute("data-importance") === state.importance;
        var okSrc = state.source === "all" || card.getAttribute("data-source") === state.source;
        var okQ = true;
        if (q) {
          var hay = (card.textContent + " " + (card.getAttribute("data-tags") || "")).toLowerCase();
          okQ = hay.indexOf(q) !== -1;
        }
        var show = okImp && okSrc && okQ;
        card.classList.toggle("is-hidden", !show);
        if (show) visible++;
      });
      // Hide a date group whose cards are all filtered out.
      groups.forEach(function (group) {
        var anyVisible = group.querySelectorAll(".card:not(.is-hidden)").length > 0;
        group.classList.toggle("is-hidden", !anyVisible);
      });
      if (noResults) noResults.classList.toggle("is-hidden", visible !== 0);
      if (countEl) countEl.textContent = visible + "件";
    }

    segBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        segBtns.forEach(function (b) { b.classList.remove("is-active"); });
        btn.classList.add("is-active");
        state.importance = btn.getAttribute("data-filter-importance");
        apply();
      });
    });
    if (sourceSel) sourceSel.addEventListener("change", function () { state.source = sourceSel.value; apply(); });
    if (searchEl) searchEl.addEventListener("input", function () { state.q = searchEl.value; apply(); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindCopyButtons();
    initFilters();
  });
})();
