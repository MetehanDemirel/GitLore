// History: commit timeline in the sidebar, colored diff of the selected file in the editor.
import { html, useEffect, useState } from "../../vendor/preact-htm.module.js";
import { api, q } from "../api.js";
import { Icon } from "../icons.js";
import { t, relativeTime, longDate } from "../i18n.js";
import { DiffView } from "../monaco.js";
import { useApp, ProjectSwitch, authorColor } from "../ui.js";
import { EditorGate } from "./editor-gate.js";

const STATUS_LETTER = { added: "A", deleted: "D", modified: "M", renamed: "R" };

export function HistorySidebar() {
  const app = useApp();
  const pid = app.project?.id;
  const [query, setQuery] = useState("");
  const [commits, setCommits] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!pid || !app.project.available) { setCommits([]); return; }
    let live = true;
    const timer = setTimeout(async () => {
      try {
        const list = await api.get(`/api/projects/${pid}/commits${q({ q: query, limit: 500 })}`);
        if (live) { setCommits(list); setError(null); }
      } catch (e) { if (live) setError(e.message); }
    }, query ? 200 : 0);
    return () => { live = false; clearTimeout(timer); };
  }, [pid, query, app.historyVersion]);

  return html`<aside class="sidebar" aria-label=${t("nav.history")}>
    <${ProjectSwitch} />
    <div class="search">
      <label class="sr-only" for="commit-search">${t("history.search")}</label>
      <input id="commit-search" class="input" type="search" placeholder=${t("history.search")} value=${query}
        autocomplete="off" spellcheck="false" onInput=${(e) => setQuery(e.target.value)} />
    </div>
    <div class="panel-body">
      ${error && html`<p class="error-box" style="margin:8px">${error}</p>`}
      ${commits && commits.length === 0 && html`<p class="muted" style="padding:12px">
        ${query ? t("history.noMatch", { q: query }) : t("history.empty")}</p>`}
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
        ${commit.is_merge && html`<span>${t("history.merge")}</span>`}
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

  return html`
    <div class="editor-head">
      <div class="title">
        <strong>${path || subject}</strong>
        ${path && html`<span class="muted" style="overflow:hidden;text-overflow:ellipsis">${subject}</span>`}
      </div>
      ${body && html`<button class="btn" onClick=${() => setShowMessage(!showMessage)} aria-expanded=${showMessage}>
        ${showMessage ? t("diff.hideDetails") : t("diff.details")}</button>`}
      <div class="segmented" role="group" aria-label="${t("diff.sideBySide")} / ${t("diff.inline")}">
        <button aria-pressed=${app.sideBySide} onClick=${() => app.setSideBySide(true)}>${t("diff.sideBySide")}</button>
        <button aria-pressed=${!app.sideBySide} onClick=${() => app.setSideBySide(false)}>${t("diff.inline")}</button>
      </div>
    </div>
    ${showMessage && html`<div class="commit-message">
      <span class="who" style=${{ color: authorColor(detail.author) }}>${detail.author}</span>
      <span class="muted"> · ${longDate(detail.date)} · </span><span class="mono">${detail.short_hash}</span>
      ${"\n"}<strong>${subject}</strong>${body && "\n\n" + body}
    </div>`}
    ${file?.status === "renamed" && html`<div class="editor-note">${t("diff.renamed", { from: file.old_path })}</div>`}
    <div class="editor-host">
      ${!path ? html`<div class="placeholder">${t("diff.pickFile")}</div>`
        : !versions ? html`<div class="placeholder"><span class="spinner"></span></div>`
        : versions.binary ? html`<div class="placeholder">${t("diff.binary")}</div>`
        : html`<${EditorGate}>${(monaco) => html`<${DiffView} monaco=${monaco} original=${versions.original}
            modified=${versions.modified} language=${versions.language} sideBySide=${app.sideBySide} theme=${app.theme}
            collapseUnchanged=${true}
            onAsk=${(sel, explain) => app.askAbout({ path, commit: hash, text: sel.text, side: sel.side }, explain)} />`}<//>`}
    </div>`;
}
