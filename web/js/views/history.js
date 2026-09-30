// History: commit timeline in the sidebar, colored diff of the selected file in the editor.
import { html, useEffect, useState } from "../../vendor/preact-htm.module.js";
import { api, q } from "../api.js";
import { Icon } from "../icons.js";
import { t, relativeTime, longDate } from "../i18n.js";
import { DiffView } from "../monaco.js";
import { useApp, ProjectSwitch, authorColor } from "../ui.js";
import { EditorGate } from "./editor-gate.js";
import { BlameDialog, CategoryChip } from "./insights.js";

const STATUS_LETTER = { added: "A", deleted: "D", modified: "M", renamed: "R" };
const TYPE_FILTERS = ["feature", "bugfix", "security", "performance", "refactor", "docs"];

export function HistorySidebar() {
  const app = useApp();
  const pid = app.project?.id;
  const query = app.historyQuery;
  const [commits, setCommits] = useState(null);
  const [error, setError] = useState(null);
  const [help, setHelp] = useState(false);
  const advanced = /\b\w+:/.test(query);

  useEffect(() => {
    if (!pid || !app.project.available) { setCommits([]); return; }
    let live = true;
    const timer = setTimeout(async () => {
      try {
        const list = advanced
          ? (await api.get(`/api/projects/${pid}/search${q({ q: query })}`)).results
          : await api.get(`/api/projects/${pid}/commits${q({ q: query, limit: 1000 })}`);
        if (live) { setCommits(list); setError(null); }
      } catch (e) { if (live) { setError(e.message); setCommits([]); } }
    }, query ? 220 : 0);
    return () => { live = false; clearTimeout(timer); };
  }, [pid, query, app.historyVersion]);

  const activeType = (query.match(/\btype:(\w+)/) || [])[1];
  const toggleType = (type) => {
    const rest = query.replace(/\s*\btype:\w+/g, "").trim();
    app.setHistoryQuery(activeType === type ? rest : `${rest} type:${type}`.trim());
  };

  return html`<aside class="sidebar" aria-label=${t("nav.history")}>
    <${ProjectSwitch} />
    <div class="search">
      <div class="row" style="gap:4px">
        <label class="sr-only" for="commit-search">${t("history.search")}</label>
        <input id="commit-search" class="input grow" type="search" placeholder=${t("history.search")} value=${query}
          autocomplete="off" spellcheck="false" onInput=${(e) => app.setHistoryQuery(e.target.value)} />
        <button class="icon-btn" aria-label=${t("search.help")} title=${t("search.help")} aria-expanded=${help}
          onClick=${() => setHelp(!help)}><${Icon} name="more" /></button>
      </div>
      ${help && html`<p class="hint search-help">${t("search.syntax")}</p>`}
      <div class="filters compact" role="group" aria-label=${t("search.types")}>
        ${TYPE_FILTERS.map((k) => html`<button type="button" class="pill" aria-pressed=${activeType === k}
          onClick=${() => toggleType(k)}>${t("category." + k)}</button>`)}
      </div>
    </div>
    <div class="panel-body">
      ${error && html`<p class="error-box" style="margin:8px">${error}</p>`}
      ${commits && commits.length === 0 && html`<p class="muted" style="padding:12px">
        ${query ? t("history.noMatch", { q: query }) : t("history.empty")}</p>`}
      ${advanced && commits && commits.length > 0 && html`<p class="hint" style="padding:6px 12px 0">${t("search.results", { n: commits.length })}</p>`}
      <ul class="commits" role="list">
        ${(commits || []).map((c) => html`<${CommitRow} key=${c.hash} commit=${c} />`)}
      </ul>
    </div>
  </aside>`;
}

function CommitRow({ commit }) {
  const app = useApp();
  const selected = app.selection?.kind === "commit" && app.selection.hash === commit.hash;
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (!selected) return;
    // Opening a commit also opens its first file, so there is always a diff to look at.
    const openFirst = (d) => !app.selection.path && d.files.length &&
      app.select({ kind: "commit", hash: commit.hash, path: d.files[0].path });
    if (detail) { openFirst(detail); return; }
    api.get(`/api/projects/${app.project.id}/commits/${commit.hash}`)
      .then((d) => { setDetail(d); openFirst(d); })
      .catch((e) => app.toast(e.message, true));
  }, [selected]);

  return html`<li>
    <button class=${"commit" + (commit.is_merge ? " merge" : "")} aria-current=${selected}
      style=${{ "--who": authorColor(commit.author) }}
      onClick=${() => app.select({ kind: "commit", hash: commit.hash, path: null })}>
      <span class="node" aria-hidden="true"></span>
      <span class="subject">${commit.subject}</span>
      <span class="meta">
        <span class="who">${commit.author}</span>
        <time datetime=${commit.date} title=${longDate(commit.date)}>${relativeTime(commit.date)}</time>
        <span class="mono">${commit.short_hash}</span>
        <${CategoryChip} category=${commit.category} large=${commit.large} />
      </span>
    </button>
    ${selected && detail && html`<ul class="files" role="list" aria-label=${t(detail.files.length === 1 ? "history.file" : "history.files", { n: detail.files.length })}>
      ${detail.files.map((f) => html`<li key=${f.path}>
        <button class="file" aria-current=${app.selection.path === f.path} title=${f.path}
          onClick=${() => app.select({ kind: "commit", hash: commit.hash, path: f.path })}>
          <span class=${"st " + f.status} title=${t("diff." + f.status, { from: f.old_path })}>${STATUS_LETTER[f.status]}</span>
          <span class="fname">${f.path}</span>
          ${f.additions != null && html`<span class="counts"><span class="plus">+${f.additions}</span><span class="minus">−${f.deletions}</span></span>`}
        </button>
      </li>`)}
    </ul>`}
  </li>`;
}

export function CommitEditor() {
  const app = useApp();
  const { hash, path } = app.selection;
  const [detail, setDetail] = useState(null);
  const [versions, setVersions] = useState(null);
  const [showMessage, setShowMessage] = useState(true);
  const [blame, setBlame] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setDetail(null); setError(null);
    api.get(`/api/projects/${app.project.id}/commits/${hash}`).then(setDetail).catch((e) => setError(e.message));
  }, [hash]);

  useEffect(() => {
    setVersions(null);
    if (!path || !detail) return;
    const file = detail.files.find((f) => f.path === path);
    const params = { path, ...(file?.old_path ? { old_path: file.old_path } : {}) };
    api.get(`/api/projects/${app.project.id}/commits/${hash}/file${q(params)}`).then(setVersions).catch((e) => setError(e.message));
  }, [hash, path, detail]);

  if (error) return html`<div class="placeholder"><p class="error-box">${error}</p></div>`;
  if (!detail) return html`<div class="placeholder"><span class="spinner"></span></div>`;
  const file = detail.files.find((f) => f.path === path);
  const [subject, ...rest] = detail.message.split("\n");
  const body = rest.join("\n").trim();
  const explainCommit = () => app.askAbout({ path: "", commit: hash, text: "", side: "" }, "commit");

  return html`
    <div class="editor-head">
      <div class="title">
        <strong>${path || subject}</strong>
        ${path && html`<span class="muted" style="overflow:hidden;text-overflow:ellipsis">${subject}</span>`}
      </div>
      <button class="btn" onClick=${explainCommit} title=${t("explain.commitHint")}><${Icon} name="sparkle" /> ${t("explain.commit")}</button>
      ${path && file?.status !== "deleted" && html`<button class="icon-btn" onClick=${() => setBlame(true)}
        aria-label=${t("blame.who")} title=${t("blame.who")}><${Icon} name="people" /></button>`}
      ${body && html`<button class="icon-btn" onClick=${() => setShowMessage(!showMessage)} aria-expanded=${showMessage}
        aria-label=${showMessage ? t("diff.hideDetails") : t("diff.details")} title=${showMessage ? t("diff.hideDetails") : t("diff.details")}>
        <${Icon} name="book" /></button>`}
      <div class="segmented" role="group" aria-label="${t("diff.sideBySide")} / ${t("diff.inline")}">
        <button aria-pressed=${app.sideBySide} onClick=${() => app.setSideBySide(true)}>${t("diff.sideBySide")}</button>
        <button aria-pressed=${!app.sideBySide} onClick=${() => app.setSideBySide(false)}>${t("diff.inline")}</button>
      </div>
    </div>
    ${showMessage && html`<div class="commit-message">
      <button type="button" class="linklike who" style=${{ color: authorColor(detail.author) }}
        onClick=${() => app.select({ kind: "insight", section: "profile", arg: detail.author })}>${detail.author}</button>
      <span class="muted"> · ${longDate(detail.date)} · </span><span class="mono">${detail.short_hash}</span>
      ${"\n"}<strong>${subject}</strong>${body && "\n\n" + body}
    </div>`}
    ${app.project.online && html`<${Discussions} hash=${hash} />`}
    ${file?.status === "renamed" && html`<div class="editor-note">${t("diff.renamed", { from: file.old_path })}</div>`}
    <div class="editor-host">
      ${!path ? html`<div class="placeholder">${t("diff.pickFile")}</div>`
        : !versions ? html`<div class="placeholder"><span class="spinner"></span></div>`
        : versions.binary ? html`<div class="placeholder">${t("diff.binary")}</div>`
        : html`<${EditorGate}>${(monaco) => html`<${DiffView} monaco=${monaco} original=${versions.original}
            modified=${versions.modified} language=${versions.language} sideBySide=${app.sideBySide} theme=${app.theme}
            collapseUnchanged=${true}
            onAsk=${(sel, explain) => app.askAbout({ path, commit: hash, text: sel.text, side: sel.side }, explain)} />`}<//>`}
    </div>
    ${blame && html`<${BlameDialog} path=${path} onClose=${() => setBlame(false)} />`}`;
}

/** Online projects: the pull requests and issues behind a commit. */
function Discussions({ hash }) {
  const app = useApp();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!open || items) return;
    api.get(`/api/projects/${app.project.id}/online/discussions/${hash}`).then(setItems).catch((e) => setError(e.message));
  }, [open]);
  return html`<details class="discussions" open=${open} onToggle=${(e) => setOpen(e.target.open)}>
    <summary><${Icon} name="chat" size=${14} /> ${t("online.discussions")}</summary>
    ${error && html`<p class="error-box">${error}</p>`}
    ${open && !items && !error && html`<span class="spinner"></span>`}
    ${items && !items.length && html`<p class="muted">${t("online.noDiscussions")}</p>`}
    ${items && items.map((d) => html`<div class="discussion" key=${d.number}>
      <div class="row wrap"><span class="tag">${d.kind === "pull" ? (d.merged ? t("online.merged") : t("online.pull")) : t("online.issue")}</span>
        <a href=${d.url} target="_blank" rel="noopener noreferrer"><strong>#${d.number} ${d.title}</strong></a>
        <span class="muted">${d.author} · ${d.comments ?? 0} ${t("online.comments")}</span></div>
      ${d.body && html`<p class="small">${d.body.slice(0, 400)}${d.body.length > 400 ? "…" : ""}</p>`}
    </div>`)}
  </details>`;
}
