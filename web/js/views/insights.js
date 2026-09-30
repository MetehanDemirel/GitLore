// Insights: what Git alone can tell about a repository — instant, no AI.
import { html, useEffect, useState } from "../../vendor/preact-htm.module.js";
import { api, q } from "../api.js";
import { Icon } from "../icons.js";
import { t, number, relativeTime, longDate } from "../i18n.js";
import { Heatmap, MonthBars, BarList } from "../charts.js";
import { useApp, ProjectSwitch, authorColor } from "../ui.js";

export const INSIGHT_SECTIONS = ["overview", "contributors", "hot-files", "releases", "branches"];

/** Fetch JSON for the current project; refetches when the project or its history changes. */
export function useProjectData(path, deps = []) {
  const app = useApp();
  const [state, setState] = useState({ data: null, error: null });
  useEffect(() => {
    if (!app.project || !path) return;
    let live = true;
    setState({ data: null, error: null });
    api.get(`/api/projects/${app.project.id}${path}`)
      .then((data) => live && setState({ data, error: null }))
      .catch((e) => live && setState({ data: null, error: e.message }));
    return () => { live = false; };
  }, [app.project?.id, app.historyVersion, path, ...deps]);
  return state;
}

export function CategoryChip({ category, large }) {
  if (!category && !large) return null;
  return html`<span class="chips">
    ${category && !["chore", "merge", "style"].includes(category) && html`<span class=${"chip cat-" + category}>${t("category." + category)}</span>`}
    ${large && html`<span class="chip chip-large">${t("category.large")}</span>`}
  </span>`;
}

/** One commit in a list; opens the commit. */
export function CommitLine({ c, showAuthor = true }) {
  const app = useApp();
  return html`<li><button type="button" class="commit-line" onClick=${() => app.openCommit(c.hash)}>
    <span class="commit-line-title ellipsis">${c.subject}</span>
    <span class="commit-line-meta">
      <span class="mono">${c.short_hash}</span>
      ${showAuthor && html`<span class="nowrap">${c.author}</span>`}
      <time class="nowrap" datetime=${c.date} title=${longDate(c.date)}>${relativeTime(c.date)}</time>
      <${CategoryChip} category=${c.category} large=${c.large} />
    </span>
  </button></li>`;
}

export function InsightsSidebar() {
  const app = useApp();
  const current = app.selection?.kind === "insight" ? app.selection.section : null;
  const sections = [...INSIGHT_SECTIONS, ...(app.project?.online ? ["github"] : [])];
  return html`<aside class="sidebar" aria-label=${t("nav.insights")}>
    <${ProjectSwitch} />
    <nav class="panel-body side-nav" aria-label=${t("nav.insights")}>
      ${sections.map((s) => html`<button type="button" class="side-link" aria-current=${current === s ? "page" : undefined}
          onClick=${() => app.select({ kind: "insight", section: s })}>
        <${Icon} name=${SECTION_ICONS[s]} /> ${t("insights." + s)}</button>`)}
    </nav>
  </aside>`;
}

const SECTION_ICONS = { overview: "chart", contributors: "people", "hot-files": "flame", releases: "tag",
                        branches: "branch", github: "cloud", profile: "people" };

export function InsightPage() {
  const app = useApp();
  const { section, arg } = app.selection;
  const pages = { overview: Overview, contributors: Contributors, profile: Profile, "hot-files": HotFiles,
                  releases: Releases, branches: Branches, github: GitHubInfo };
  const Page = pages[section] || Overview;
  return html`<div class="page" key=${section + (arg || "")}><${Page} arg=${arg} /></div>`;
}

function PageHead({ title, sub, children }) {
  return html`<header class="page-head"><div class="grow"><h1>${title}</h1>${sub && html`<p class="muted">${sub}</p>`}</div>${children}</header>`;
}

function Loading({ state }) {
  if (state.error) return html`<p class="error-box">${state.error}</p>`;
  return html`<div class="placeholder" style="min-height:120px"><span class="spinner"></span></div>`;
}

// ------------------------------------------------------------------ overview
function Overview() {
  const app = useApp();
  const ov = useProjectData("/insights/overview");
  const heat = useProjectData("/insights/heatmap");
  const act = useProjectData("/insights/activity");
  if (!ov.data) return html`<${PageHead} title=${t("insights.overview")} /><${Loading} state=${ov} />`;
  const o = ov.data;
  const searchFor = (query) => app.searchHistory(query);
  return html`
    <${PageHead} title=${t("insights.overview")} sub=${o.commits ? t("insights.span", { from: longDate(o.first), to: longDate(o.last) }) : ""} />
    <div class="stats">
      <div class="stat"><strong>${number(o.commits)}</strong><span>${t("insights.commits")}</span></div>
      <div class="stat"><strong>${number(o.contributors)}</strong><span>${t("insights.contributors")}</span></div>
      <div class="stat"><strong>${number(o.files)}</strong><span>${t("insights.filesTouched")}</span></div>
    </div>
    <section class="card"><h2>${t("insights.heatmap")}</h2>
      ${heat.data ? html`<${Heatmap} days=${heat.data.days} max=${heat.data.max}
        onPick=${(day) => searchFor(`since:${day} until:${day}`)} />` : html`<${Loading} state=${heat} />`}</section>
    <section class="card"><h2>${t("insights.activity")}</h2>
      ${act.data ? html`<${MonthBars} months=${act.data} />` : html`<${Loading} state=${act} />`}</section>
    <div class="two-col">
      <section class="card"><h2>${t("insights.categories")}</h2>
        <p class="hint">${t("insights.categoriesNote")}</p>
        <${BarList} rows=${o.categories.map((c) => ({ label: t("category." + c.category), value: c.count, key: c.category }))}
          onPick=${(r) => searchFor(`type:${r.key}`)} /></section>
      <section class="card"><h2>${t("insights.largeChanges")}</h2>
        ${o.large.length ? html`<ul class="commit-list">${o.large.map((c) => html`<${CommitLine} key=${c.hash} c=${c} />`)}</ul>`
          : html`<p class="muted">${t("insights.noLarge")}</p>`}</section>
    </div>`;
}

// ------------------------------------------------------------------ people
function Contributors() {
  const app = useApp();
  const st = useProjectData("/insights/contributors");
  if (!st.data) return html`<${PageHead} title=${t("insights.contributors")} /><${Loading} state=${st} />`;
  return html`
    <${PageHead} title=${t("insights.contributors")} sub=${t("insights.contributorsNote")} />
    <ul class="people" role="list">
      ${st.data.map((p) => html`<li key=${p.name}><button type="button" class="person"
          onClick=${() => app.select({ kind: "insight", section: "profile", arg: p.name })}>
        <span class="avatar" style=${{ "--who": authorColor(p.name) }} aria-hidden="true">${p.name.slice(0, 1)}</span>
        <span class="grow">
          <strong>${p.name}</strong>
          <span class="muted block">${t("insights.activeRange", { from: longDate(p.first).split(",")[0], to: relativeTime(p.last) })}</span>
          <span class="muted block ellipsis">${p.areas.join(" · ")}</span>
        </span>
        <span class="nowrap"><strong>${number(p.commits)}</strong> <span class="muted">${t("insights.commits")}</span></span>
      </button></li>`)}
    </ul>`;
}

function Profile({ arg }) {
  const app = useApp();
  const st = useProjectData(`/profile${q({ author: arg })}`, [arg]);
  if (!st.data) return html`<${PageHead} title=${arg} /><${Loading} state=${st} />`;
  const p = st.data;
  return html`
    <${PageHead} title=${p.name} sub=${t("insights.activeRange", { from: longDate(p.first).split(",")[0], to: relativeTime(p.last) })}>
      <button class="btn" onClick=${() => app.searchHistory(`author:"${p.name}"`)}><${Icon} name="search" /> ${t("insights.allCommits")}</button>
    </${PageHead}>
    <div class="stats">
      <div class="stat"><strong>${number(p.commits)}</strong><span>${t("insights.commits")}</span></div>
      <div class="stat"><strong class="add">+${number(p.additions)}</strong><span>${t("insights.linesAdded")}</span></div>
      <div class="stat"><strong class="del">−${number(p.deletions)}</strong><span>${t("insights.linesRemoved")}</span></div>
    </div>
    <div class="two-col">
      <section class="card"><h2>${t("insights.workedOn")}</h2>
        <${BarList} rows=${Object.entries(p.categories).map(([k, v]) => ({ label: t("category." + k), value: v }))} /></section>
      <section class="card"><h2>${t("insights.areas")}</h2>
        <${BarList} rows=${p.top_files.map((f) => ({ label: f.path, value: f.commits }))} /></section>
    </div>
    <section class="card"><h2>${t("insights.recent")}</h2>
      <ul class="commit-list">${p.recent.map((c) => html`<${CommitLine} key=${c.hash} c=${c} showAuthor=${false} />`)}</ul></section>`;
}

// ------------------------------------------------------------------ files
function HotFiles() {
  const app = useApp();
  const st = useProjectData("/insights/hot-files");
  const [blame, setBlame] = useState(null);
  if (!st.data) return html`<${PageHead} title=${t("insights.hot-files")} /><${Loading} state=${st} />`;
  return html`
    <${PageHead} title=${t("insights.hot-files")} sub=${t("insights.hotNote")} />
    <table class="table">
      <thead><tr><th>${t("insights.file")}</th><th class="num">${t("insights.commits")}</th>
        <th class="num">${t("insights.lines")}</th><th>${t("insights.people")}</th><th>${t("insights.lastChange")}</th><th></th></tr></thead>
      <tbody>${st.data.map((f) => html`<tr key=${f.path}>
        <td class="mono ellipsis" title=${f.path}>${f.path}</td><td class="num">${number(f.commits)}</td>
        <td class="num">${number(f.lines)}</td><td class="ellipsis">${f.authors.join(", ")}</td>
        <td class="muted nowrap">${relativeTime(f.last)}</td>
        <td><button class="btn" onClick=${() => setBlame(f.path)}>${t("blame.who")}</button></td></tr>`)}</tbody>
    </table>
    ${blame && html`<${BlameDialog} path=${blame} onClose=${() => setBlame(null)} />`}`;
}

export function BlameDialog({ path, onClose }) {
  const app = useApp();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    api.get(`/api/projects/${app.project.id}/blame${q({ path })}`).then(setData).catch((e) => setError(e.message));
  }, [path]);
  return html`<div class="backdrop" onMouseDown=${(e) => e.target === e.currentTarget && onClose()}
      onKeyDown=${(e) => e.key === "Escape" && onClose()}>
    <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="blame-title" style="width:min(520px,100%)">
      <h2 id="blame-title">${t("blame.title")}</h2>
      <p class="mono ellipsis">${path}</p>
      ${error && html`<p class="error-box">${error}</p>`}
      ${!data && !error && html`<span class="spinner"></span>`}
      ${data && html`<p class="hint">${t("blame.note", { n: number(data.lines) })}</p>
        <${BarList} rows=${data.authors.map((a) => ({ label: a.name, value: a.lines }))}
          format=${(v) => `${Math.round((v / data.lines) * 100)}%`}
          onPick=${(r) => { onClose(); app.select({ kind: "insight", section: "profile", arg: r.label }); }} />`}
      <div class="actions"><button class="btn" autofocus onClick=${onClose}>${t("common.close")}</button></div>
    </div>
  </div>`;
}

// ------------------------------------------------------------------ releases & branches
function Releases() {
  const app = useApp();
  const st = useProjectData("/insights/releases");
  if (!st.data) return html`<${PageHead} title=${t("insights.releases")} /><${Loading} state=${st} />`;
  if (!st.data.length) return html`<${PageHead} title=${t("insights.releases")} /><p class="muted">${t("insights.noReleases")}</p>`;
  return html`
    <${PageHead} title=${t("insights.releases")} sub=${t("insights.releasesNote")} />
    <ol class="releases" role="list">
      ${st.data.map((r) => html`<li key=${r.name} class="card release">
        <div class="row wrap">
          <span class="tag-name mono">${r.name}</span>
          <time class="muted" datetime=${r.date}>${longDate(r.date)}</time>
          <span class="grow"></span>
          <span class="muted">${t("insights.commitsN", { n: r.commit_count })}</span>
          ${r.previous && html`<button class="btn" onClick=${() => app.select({ kind: "insight", section: "branches", arg: `${r.previous}..${r.name}` })}>
            ${t("insights.compareWith", { name: r.previous })}</button>`}
        </div>
        ${r.message && html`<pre class="release-notes">${r.message}</pre>`}
        ${r.highlights.length > 0 && html`<ul class="commit-list">${r.highlights.map((c) => html`<${CommitLine} key=${c.hash} c=${c} />`)}</ul>`}
      </li>`)}
    </ol>`;
}

function Branches({ arg }) {
  const app = useApp();
  const br = useProjectData("/insights/branches");
  const rel = useProjectData("/insights/releases");
  const [base, setBase] = useState(arg ? arg.split("..")[0] : "");
  const [head, setHead] = useState(arg ? arg.split("..")[1] : "");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const run = async (b = base, h = head) => {
    if (!b || !h) return;
    setError(null); setResult(null);
    try { setResult(await api.get(`/api/projects/${app.project.id}/compare${q({ base: b, head: h })}`)); }
    catch (e) { setError(e.message); }
  };
  useEffect(() => { if (arg) run(); }, [arg]);
  const refs = [...(br.data || []).map((b) => b.name), ...(rel.data || []).map((r) => r.name)];
  return html`
    <${PageHead} title=${t("insights.branches")} sub=${t("insights.branchesNote")} />
    <section class="card"><h2>${t("insights.compare")}</h2>
      <form class="row wrap" onSubmit=${(e) => { e.preventDefault(); run(); }}>
        <label class="field inline"><span>${t("insights.base")}</span>
          <input class="input mono" list="refs" value=${base} onInput=${(e) => setBase(e.target.value)} placeholder="v1.0.0" /></label>
        <span class="muted" aria-hidden="true">…</span>
        <label class="field inline"><span>${t("insights.head")}</span>
          <input class="input mono" list="refs" value=${head} onInput=${(e) => setHead(e.target.value)} placeholder="main" /></label>
        <datalist id="refs">${refs.map((r) => html`<option value=${r} />`)}</datalist>
        <button class="btn primary" disabled=${!base || !head}>${t("insights.compare")}</button>
      </form>
      ${error && html`<p class="error-box" style="margin-top:10px">${error}</p>`}
      ${result && html`<div class="compare-result">
        <p><strong>${t("insights.aheadBehind", { ahead: result.ahead, behind: result.behind, head: result.head, base: result.base })}</strong></p>
        <p class="muted">${Object.entries(result.categories).map(([k, v]) => `${t("category." + k)} ${v}`).join(" · ")}</p>
        <div class="two-col">
          <div><h3>${t("insights.commits")}</h3><ul class="commit-list">${result.commits.slice(0, 60).map((c) => html`<${CommitLine} key=${c.hash} c=${c} />`)}</ul></div>
          <div><h3>${t("insights.filesChanged", { n: result.files.length })}</h3>
            <ul class="file-stats">${result.files.slice(0, 80).map((f) => html`<li key=${f.path}><span class="mono ellipsis grow">${f.path}</span>
              <span class="counts"><span class="plus">+${f.additions}</span><span class="minus">−${f.deletions}</span></span></li>`)}</ul></div>
        </div></div>`}
    </section>
    <section class="card"><h2>${t("insights.branchList")}</h2>
      ${!br.data ? html`<${Loading} state=${br} />` : html`<table class="table">
        <thead><tr><th>${t("insights.branch")}</th><th class="num">${t("insights.ahead")}</th><th class="num">${t("insights.behind")}</th>
          <th>${t("insights.lastCommit")}</th><th></th></tr></thead>
        <tbody>${br.data.map((b) => html`<tr key=${b.name}>
          <td class="mono">${b.name} ${b.current ? html`<span class="tag">${t("insights.current")}</span>` : b.merged ? html`<span class="muted">${t("insights.merged")}</span>` : ""}</td>
          <td class="num">${b.ahead}</td><td class="num">${b.behind}</td>
          <td class="ellipsis"><button type="button" class="linklike" onClick=${() => app.openCommit(b.hash)}>${b.subject}</button>
            <span class="muted"> · ${relativeTime(b.date)}</span></td>
          <td>${!b.current && html`<button class="btn" onClick=${() => { const cur = br.data.find((x) => x.current)?.name || "main";
              setBase(cur); setHead(b.name); run(cur, b.name); }}>${t("insights.compare")}</button>`}</td></tr>`)}</tbody>
      </table>`}
    </section>`;
}

// ------------------------------------------------------------------ online
function GitHubInfo() {
  const info = useProjectData("/online/info");
  const rel = useProjectData("/online/releases");
  const d = info.data;
  return html`
    <${PageHead} title=${d ? d.full_name : "GitHub"} sub=${d?.description}>
      ${d?.url && html`<a class="btn" href=${d.url} target="_blank" rel="noopener noreferrer">${t("online.openOnGithub")}</a>`}
    </${PageHead}>
    ${!d ? html`<${Loading} state=${info} />` : html`<div class="stats">
      <div class="stat"><strong>${number(d.stars ?? 0)}</strong><span>${t("online.stars")}</span></div>
      <div class="stat"><strong>${number(d.forks ?? 0)}</strong><span>${t("online.forks")}</span></div>
      <div class="stat"><strong>${number(d.open_issues ?? 0)}</strong><span>${t("online.openIssues")}</span></div>
      <div class="stat"><strong>${d.language || "—"}</strong><span>${t("online.language")}</span></div>
    </div>`}
    <section class="card"><h2>${t("online.releases")}</h2>
      ${!rel.data ? html`<${Loading} state=${rel} />` : !rel.data.length ? html`<p class="muted">${t("insights.noReleases")}</p>`
        : html`<ol class="releases" role="list">${rel.data.slice(0, 15).map((r) => html`<li key=${r.tag} class="release">
          <div class="row"><span class="tag-name mono">${r.tag}</span><span class="grow ellipsis">${r.name}</span>
            <time class="muted">${r.date ? longDate(r.date) : ""}</time>
            <a href=${r.url} target="_blank" rel="noopener noreferrer">${t("online.view")}</a></div>
          ${r.body && html`<pre class="release-notes">${r.body.slice(0, 600)}</pre>`}</li>`)}</ol>`}
    </section>`;
}
