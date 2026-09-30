// Story: AI-written, cited narratives — repository history, a timeline of key events,
// "what changed while I was away?" and a welcome brief. Facts show instantly; AI text is cached.
import { html, useEffect, useState } from "../../vendor/preact-htm.module.js";
import { api, q, waitForJob } from "../api.js";
import { Icon } from "../icons.js";
import { t, number, relativeTime, longDate } from "../i18n.js";
import { renderMarkdown } from "../markdown.js";
import { useApp, ProjectSwitch, Progress } from "../ui.js";
import { CommitLine, CategoryChip } from "./insights.js";

export const STORY_SECTIONS = ["history", "timeline", "away", "onboarding"];
const ICONS = { history: "book", timeline: "timeline", away: "clock", onboarding: "people" };

export function StorySidebar() {
  const app = useApp();
  const current = app.selection?.kind === "story" ? app.selection.section : null;
  return html`<aside class="sidebar" aria-label=${t("nav.story")}>
    <${ProjectSwitch} />
    <nav class="panel-body side-nav" aria-label=${t("nav.story")}>
      ${STORY_SECTIONS.map((s) => html`<button type="button" class="side-link" aria-current=${current === s ? "page" : undefined}
          onClick=${() => app.select({ kind: "story", section: s })}><${Icon} name=${ICONS[s]} /> ${t("story." + s)}</button>`)}
      <p class="hint" style="padding:12px">${t("story.note")}</p>
    </nav>
  </aside>`;
}

/** Loads cached AI text + instant facts for one kind of brief; runs generation as a background job. */
function useBrief(kind, since) {
  const app = useApp();
  const [data, setData] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const url = `/api/projects/${app.project.id}/briefs/${kind}${since ? q({ since }) : ""}`;
  const load = async () => {
    try {
      const d = await api.get(url);
      setData(d);
      if (d.job && !job) follow(d.job);
    } catch (e) { setError(e.message); }
  };
  const follow = async (id) => {
    try { await waitForJob(id, setJob, 700); } catch (e) { setError(e.message); }
    setJob(null);
    load();
  };
  const generate = async () => {
    setError(null);
    try { const { job: id } = await api.post(url); follow(id); } catch (e) { setError(e.message); }
  };
  useEffect(() => { setData(null); load(); }, [app.project.id, url, app.historyVersion]);
  return { data, job, error, generate };
}

function GenerateBar({ brief, label }) {
  const app = useApp();
  const { data, job, generate } = brief;
  const has = data?.brief && Object.values(data.brief).some((v) => v && (typeof v === "string" ? v : true));
  if (job) {
    const pct = job.total ? (job.done / job.total) * 100 : 5;
    return html`<div class="generate"><span class="spinner"></span>
      <span class="grow">${t("story.generating")} ${job.message && job.message !== "done" ? `· ${job.message}` : ""}</span>
      <div style="width:160px"><${Progress} value=${pct} /></div></div>`;
  }
  return html`<div class="generate">
    <span class="grow muted">${data?.created_at ? (data.stale ? t("story.stale") : t("story.generatedAt", { when: relativeTime(data.created_at) }))
      : app.model.downloaded ? t("story.notYet") : t("story.needsModel")}</span>
    <button class="btn primary" disabled=${!app.model.downloaded} onClick=${generate}>
      <${Icon} name="sparkle" /> ${has ? t("story.regenerate") : label}</button>
  </div>`;
}

function Prose({ text }) {
  const app = useApp();
  if (!text) return null;
  return html`<div class="answer prose" onClick=${(e) => { const c = e.target.closest("[data-hash]"); if (c) app.openCommit(c.dataset.hash); }}
    dangerouslySetInnerHTML=${{ __html: renderMarkdown(text) }}></div>`;
}

export function StoryPage() {
  const app = useApp();
  const { section } = app.selection;
  const pages = { history: History, timeline: Timeline, away: Away, onboarding: Onboarding };
  const Page = pages[section] || History;
  return html`<div class="page" key=${section}><${Page} /></div>`;
}

// ------------------------------------------------------------------ repository history
function History() {
  const brief = useBrief("history");
  const eras = brief.data?.brief?.eras || brief.data?.facts?.eras || [];
  return html`
    <header class="page-head"><div class="grow"><h1>${t("story.history")}</h1><p class="muted">${t("story.historyNote")}</p></div></header>
    <${GenerateBar} brief=${brief} label=${t("story.generateHistory")} />
    ${brief.error && html`<p class="error-box">${brief.error}</p>`}
    ${brief.data?.brief?.intro && html`<div class="card lead"><${Prose} text=${brief.data.brief.intro} /></div>`}
    ${!brief.data && html`<div class="placeholder" style="min-height:100px"><span class="spinner"></span></div>`}
    <ol class="eras" role="list">
      ${eras.map((e) => html`<li key=${e.key} class="era">
        <div class="era-marker" aria-hidden="true"></div>
        <div class="era-body">
          <div class="row wrap"><h2>${e.release ? html`<span class="tag-name mono">${e.title}</span>` : e.title}</h2>
            <span class="muted">${longDate(e.start).split(",")[0]} – ${longDate(e.end).split(",")[0]} · ${t("insights.commitsN", { n: e.count })}</span></div>
          <p class="muted small">${e.contributors.join(", ")}</p>
          ${e.summary ? html`<${Prose} text=${e.summary} />`
            : html`<ul class="commit-list">${e.notable.slice(0, 4).map((c) => html`<${CommitLine} key=${c.hash} c=${c} />`)}</ul>`}
        </div>
      </li>`)}
    </ol>`;
}

// ------------------------------------------------------------------ timeline
const KIND_ICON = { release: "tag", security: "shield", large: "layers", revert: "undo", performance: "bolt",
                    feature: "sparkle", joined: "people", left: "people" };

function Timeline() {
  const app = useApp();
  const brief = useBrief("timeline");
  const [kind, setKind] = useState("all");
  const events = brief.data?.brief?.events || brief.data?.facts?.events || [];
  const kinds = ["all", ...new Set(events.map((e) => e.kind))];
  const shown = kind === "all" ? events : events.filter((e) => e.kind === kind);
  return html`
    <header class="page-head"><div class="grow"><h1>${t("story.timeline")}</h1><p class="muted">${t("story.timelineNote")}</p></div></header>
    <${GenerateBar} brief=${brief} label=${t("story.explainEvents")} />
    <div class="filters" role="group" aria-label=${t("story.filter")}>
      ${kinds.map((k) => html`<button type="button" class="pill" aria-pressed=${kind === k} onClick=${() => setKind(k)}>
        ${k === "all" ? t("story.all") : t("event." + k)}</button>`)}
    </div>
    ${!brief.data && html`<div class="placeholder" style="min-height:100px"><span class="spinner"></span></div>`}
    <ol class="timeline" role="list">
      ${shown.map((e, i) => html`<li key=${i} class=${"event ev-" + e.kind}>
        <span class="event-icon" aria-hidden="true"><${Icon} name=${KIND_ICON[e.kind] || "dot"} size=${14} /></span>
        <button type="button" class="event-body" onClick=${() => app.openCommit(e.hashes[0])}>
          <span class="row wrap"><span class="event-kind">${t("event." + e.kind)}</span>
            <time class="muted" datetime=${e.date}>${longDate(e.date).split(",")[0]}</time>
            <span class="muted">${e.author}</span></span>
          <strong class="block">${e.title}</strong>
          ${e.why && html`<span class="block why">${e.why}</span>`}
          ${!e.why && e.detail && html`<span class="block muted small">${e.detail}</span>`}
        </button>
      </li>`)}
    </ol>`;
}

// ------------------------------------------------------------------ what changed while I was away?
function Away() {
  const app = useApp();
  const defaultSince = (app.previousVisit || new Date(Date.now() - 30 * 864e5).toISOString()).slice(0, 10);
  const [since, setSince] = useState(defaultSince);
  const brief = useBrief("away", since);
  const f = brief.data?.brief || brief.data?.facts;
  return html`
    <header class="page-head"><div class="grow"><h1>${t("story.away")}</h1><p class="muted">${t("story.awayNote")}</p></div>
      <label class="field inline"><span>${t("story.since")}</span>
        <input type="date" class="input" value=${since} max=${new Date().toISOString().slice(0, 10)}
          onChange=${(e) => e.target.value && setSince(e.target.value)} /></label></header>
    ${app.previousVisit && html`<p class="hint">${t("story.lastVisit", { when: longDate(app.previousVisit) })}</p>`}
    ${!f ? html`<div class="placeholder" style="min-height:100px"><span class="spinner"></span></div>` : f.count === 0
      ? html`<div class="card"><p>${t("story.nothingNew", { date: longDate(since + "T12:00:00").split(",")[0] })}</p></div>`
      : html`
      <div class="stats">
        <div class="stat"><strong>${number(f.count)}</strong><span>${t("insights.commits")}</span></div>
        <div class="stat"><strong>${number(f.contributors.length)}</strong><span>${t("insights.contributors")}</span></div>
        <div class="stat"><strong>${number(f.releases.length)}</strong><span>${t("insights.releases")}</span></div>
      </div>
      <${GenerateBar} brief=${brief} label=${t("story.catchUp")} />
      ${brief.data?.brief?.briefing && html`<div class="card lead"><${Prose} text=${brief.data.brief.briefing} /></div>`}
      ${f.releases.length > 0 && html`<section class="card"><h2>${t("insights.releases")}</h2>
        <ul class="plain">${f.releases.map((r) => html`<li key=${r.name}><span class="tag-name mono">${r.name}</span> ${r.message}</li>`)}</ul></section>`}
      <div class="two-col">
        <section class="card"><h2>${t("story.important")}</h2>
          <ul class="commit-list">${f.notable.map((c) => html`<${CommitLine} key=${c.hash} c=${c} />`)}</ul></section>
        <section class="card"><h2>${t("story.who")}</h2>
          <ul class="plain">${f.contributors.map((p) => html`<li key=${p.name}><button type="button" class="linklike"
            onClick=${() => app.select({ kind: "insight", section: "profile", arg: p.name })}>${p.name}</button>
            <span class="muted"> · ${t("insights.commitsN", { n: p.commits })}</span></li>`)}</ul>
          <p class="muted small">${Object.entries(f.categories).map(([k, v]) => `${t("category." + k)} ${v}`).join(" · ")}</p></section>
      </div>`}`;
}

// ------------------------------------------------------------------ welcome brief
function Onboarding() {
  const app = useApp();
  const brief = useBrief("onboarding");
  const f = brief.data?.brief || brief.data?.facts;
  return html`
    <header class="page-head"><div class="grow"><h1>${t("story.onboarding")}</h1><p class="muted">${t("story.onboardingNote")}</p></div></header>
    <${GenerateBar} brief=${brief} label=${t("story.writeBrief")} />
    ${brief.data?.brief?.brief && html`<div class="card lead"><${Prose} text=${brief.data.brief.brief} /></div>`}
    ${!f ? html`<div class="placeholder" style="min-height:100px"><span class="spinner"></span></div>` : html`
      <div class="two-col">
        <section class="card"><h2>${t("story.people")}</h2>
          <ul class="plain">${f.contributors.map((p) => html`<li key=${p.name}><button type="button" class="linklike"
            onClick=${() => app.select({ kind: "insight", section: "profile", arg: p.name })}>${p.name}</button>
            <span class="muted"> · ${p.areas.slice(0, 2).join(", ")}</span></li>`)}</ul></section>
        <section class="card"><h2>${t("story.startHere")}</h2>
          <ul class="plain mono">${f.start_here.map((p) => html`<li key=${p}>${p}</li>`)}</ul>
          <h3>${t("insights.releases")}</h3>
          <ul class="plain">${f.releases.map((r) => html`<li key=${r.name}><span class="tag-name mono">${r.name}</span>
            <span class="muted"> ${longDate(r.date).split(",")[0]}</span></li>`)}</ul></section>
      </div>`}`;
}

export { CategoryChip };
