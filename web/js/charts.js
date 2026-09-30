// Small, calm charts in plain SVG/HTML. One hue (the theme accent) for magnitude; identity is never
// carried by color alone (labels and counts are always visible or one hover away).
import { html, useMemo, useState } from "../vendor/preact-htm.module.js";
import { t, number, locale } from "./i18n.js";

const STEPS = [0, 22, 42, 66, 92];   // accent strength (%) per heatmap level; level 0 = empty day

function level(n, max) {
  if (!n) return 0;
  if (max <= 4) return Math.min(4, n);
  return Math.min(4, 1 + Math.floor((n / max) * 3.999));
}

/** GitHub-style calendar: the last 53 weeks up to the newest commit. */
export function Heatmap({ days, max, onPick }) {
  const [hover, setHover] = useState(null);
  const grid = useMemo(() => {
    const keys = Object.keys(days);
    if (!keys.length) return null;
    const end = new Date(keys[keys.length - 1] + "T12:00:00");
    const start = new Date(end);
    start.setDate(start.getDate() - 7 * 52 - end.getDay());
    const cells = [];
    const months = [];
    for (let d = new Date(start), i = 0; d <= end; d.setDate(d.getDate() + 1), i++) {
      // Local date, not toISOString() (UTC), which would shift commits onto the wrong day.
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      const week = Math.floor(i / 7);
      cells.push({ key, week, day: d.getDay(), n: days[key] || 0 });
      if (d.getDate() === 1) months.push({ week, label: new Intl.DateTimeFormat(locale, { month: "short" }).format(d) });
    }
    return { cells, months, weeks: Math.ceil(cells.length / 7) };
  }, [days]);
  if (!grid) return html`<p class="muted">${t("insights.noData")}</p>`;
  const size = 11, gap = 3, left = 22, top = 16;
  const width = left + grid.weeks * (size + gap);
  const total = grid.cells.reduce((a, c) => a + c.n, 0);
  const dayNames = [1, 3, 5].map((d) => new Intl.DateTimeFormat(locale, { weekday: "short" }).format(new Date(2024, 0, 7 + d)));
  return html`<div class="chart heatmap">
    <svg viewBox="0 0 ${width} ${top + 7 * (size + gap)}" role="img" width="100%"
      aria-label=${t("insights.heatmapSummary", { n: number(total) })}>
      ${grid.months.map((m) => html`<text x=${left + m.week * (size + gap)} y="10" class="axis-label">${m.label}</text>`)}
      ${[1, 3, 5].map((d, i) => html`<text x="0" y=${top + d * (size + gap) + 9} class="axis-label">${dayNames[i]}</text>`)}
      ${grid.cells.map((c) => html`<rect x=${left + c.week * (size + gap)} y=${top + c.day * (size + gap)} width=${size} height=${size}
          rx="2" class=${"cell l" + level(c.n, max)} onMouseEnter=${() => setHover(c)} onMouseLeave=${() => setHover(null)}
          onClick=${() => c.n && onPick?.(c.key)} style=${c.n && onPick ? "cursor:pointer" : ""}>
          <title>${t("insights.dayCommits", { n: c.n, date: c.key })}</title></rect>`)}
    </svg>
    <div class="chart-foot">
      <span class="muted">${hover ? t("insights.dayCommits", { n: hover.n, date: hover.key }) : t("insights.heatmapSummary", { n: number(total) })}</span>
      <span class="legend" aria-hidden="true">${t("insights.less")}
        ${STEPS.map((_, i) => html`<svg width="11" height="11"><rect width="11" height="11" rx="2" class=${"cell l" + i} /></svg>`)}
        ${t("insights.more")}</span>
    </div>
  </div>`;
}

/** Monthly bars (single series). */
export function MonthBars({ months }) {
  const [hover, setHover] = useState(null);
  if (!months.length) return html`<p class="muted">${t("insights.noData")}</p>`;
  const max = Math.max(...months.map((m) => m.total));
  const w = 18, gap = 6, h = 110;
  const width = months.length * (w + gap);
  const fmt = (m) => new Intl.DateTimeFormat(locale, { month: "short", year: "2-digit" }).format(new Date(m + "-15"));
  return html`<div class="chart bars">
    <svg viewBox="0 0 ${width} ${h + 18}" width="100%" role="img" aria-label=${t("insights.activitySummary")}>
      <line x1="0" x2=${width} y1=${h} y2=${h} class="baseline" />
      ${months.map((m, i) => {
        const bh = Math.max(2, (m.total / max) * (h - 8));
        return html`<g onMouseEnter=${() => setHover(m)} onMouseLeave=${() => setHover(null)}>
          <rect x=${i * (w + gap) - gap / 2} y="0" width=${w + gap} height=${h} fill="transparent" />
          <rect x=${i * (w + gap)} y=${h - bh} width=${w} height=${bh} rx="3" class=${"bar" + (hover === m ? " on" : "")}>
            <title>${fmt(m.month)}: ${m.total}</title></rect>
          ${(i % Math.ceil(months.length / 8) === 0) && html`<text x=${i * (w + gap)} y=${h + 13} class="axis-label">${fmt(m.month)}</text>`}
        </g>`;
      })}
    </svg>
    <div class="chart-foot"><span class="muted">${hover
      ? `${fmt(hover.month)}: ${t("insights.commitsN", { n: hover.total })} · ${Object.entries(hover.categories)
          .sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, v]) => `${t("category." + k)} ${v}`).join(", ")}`
      : t("insights.activitySummary")}</span></div>
  </div>`;
}

/** Horizontal bars with the label and value always visible (HTML, so it reads well at any width). */
export function BarList({ rows, onPick, format = (v) => number(v) }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return html`<ul class="barlist" role="list">
    ${rows.map((r) => html`<li key=${r.label}>
      ${onPick ? html`<button type="button" class="barlist-row" onClick=${() => onPick(r)}>
          <span class="barlist-label">${r.label}</span><span class="barlist-value">${format(r.value)}</span>
          <span class="barlist-track"><i style=${{ width: `${(r.value / max) * 100}%` }}></i></span></button>`
        : html`<div class="barlist-row">
          <span class="barlist-label">${r.label}</span><span class="barlist-value">${format(r.value)}</span>
          <span class="barlist-track"><i style=${{ width: `${(r.value / max) * 100}%` }}></i></span></div>`}
    </li>`)}
  </ul>`;
}
