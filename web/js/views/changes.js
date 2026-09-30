// Changes: the working tree like VS Code's Source Control — edit files, then commit them as a new commit.
import { html, useEffect, useRef, useState } from "../../vendor/preact-htm.module.js";
import { api, q } from "../api.js";
import { Icon } from "../icons.js";
import { t } from "../i18n.js";
import { DiffView } from "../monaco.js";
import { useApp, ProjectSwitch, FilePalette } from "../ui.js";
import { EditorGate } from "./editor-gate.js";

const CODE_LABEL = (code) => (code === "??" ? ["untracked", "U", "changes.untracked"]
  : code.includes("D") ? ["deleted", "D", "changes.deletedFile"]
  : code.includes("A") ? ["added", "A", "changes.untracked"]
  : ["modified", "M", "changes.modifiedFile"]);

export function ChangesSidebar() {
  const app = useApp();
  const pid = app.project?.id;
  const [status, setStatus] = useState(null);
  const [checked, setChecked] = useState({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [palette, setPalette] = useState(null);

  useEffect(() => {
    if (!pid || !app.project.available) return;
    api.get(`/api/projects/${pid}/status`).then((s) => {
      setStatus(s);
      setChecked((prev) => Object.fromEntries(s.files.map((f) => [f.path, prev[f.path] ?? true])));
      app.setChangeCount(s.files.length);
    }).catch((e) => setError(e.message));
  }, [pid, app.statusVersion]);

  const selected = (status?.files || []).filter((f) => checked[f.path]).map((f) => f.path);
  const commit = async (e) => {
    e.preventDefault();
    if (!(await app.confirmLeaveEditor())) return;
    setBusy(true); setError(null);
    try {
      const done = await api.post(`/api/projects/${pid}/commit`, { message, paths: selected });
      setMessage("");
      app.toast(t("changes.committed", { hash: done.short_hash }));
      app.refreshAfterCommit();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };
  const openPalette = async () => {
    try { setPalette(await api.get(`/api/projects/${pid}/tree`)); } catch (err) { app.toast(err.message, true); }
  };
  useEffect(() => {
    const onKey = (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "p") { e.preventDefault(); openPalette(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pid]);

  const blocked = status && (status.detached ? t("changes.detached") : status.busy ? t("changes.busy", { op: status.busy }) : null);
  return html`<aside class="sidebar" aria-label=${t("nav.changes")}>
    <${ProjectSwitch} />
    <div class="panel-body">
      <form class="composer" style="border-top:0;border-bottom:1px solid var(--border)" onSubmit=${commit}>
        ${status && html`<div class="row muted"><${Icon} name="changes" />
          <span class="grow">${status.branch ? t("changes.branch", { branch: status.branch }) : t("changes.detached")}</span></div>`}
        <label class="sr-only" for="commit-message">${t("changes.message")}</label>
        <textarea id="commit-message" class="textarea" rows="3" placeholder=${t("changes.message")} value=${message}
          onInput=${(e) => setMessage(e.target.value)}
          onKeyDown=${(e) => (e.ctrlKey || e.metaKey) && e.key === "Enter" && commit(e)}></textarea>
        ${blocked && html`<p class="error-box">${blocked}</p>`}
        ${error && html`<p class="error-box" role="alert">${error}</p>`}
        <button class="btn primary block" disabled=${busy || !message.trim() || !selected.length || !!blocked}>
          <${Icon} name="check" /> ${selected.length === 1 ? t("changes.commit1") : t("changes.commitN", { n: selected.length })}
        </button>
      </form>
      <div class="row" style="padding:8px 8px 4px 12px">
        <h3 class="section-title grow" style="margin:0">${t("nav.changes")}</h3>
        <button class="btn" onClick=${openPalette} title="Ctrl+P"><${Icon} name="file" /> ${t("changes.openFile")}</button>
      </div>
      ${status && !status.files.length && html`<p class="muted" style="padding:4px 12px">${t("changes.none")}</p>`}
      <ul class="files" style="padding-left:6px" role="list">
        ${(status?.files || []).map((f) => {
          const [cls, letter, label] = CODE_LABEL(f.code);
          return html`<li key=${f.path} class="row" style="gap:0">
            <input type="checkbox" aria-label=${f.path} checked=${!!checked[f.path]} style="margin:0 4px 0 6px"
              onChange=${(e) => setChecked({ ...checked, [f.path]: e.target.checked })} />
            <button class="file" aria-current=${app.selection?.kind === "worktree" && app.selection.path === f.path}
              title=${f.path} onClick=${() => app.select({ kind: "worktree", path: f.path })}>
              <span class=${"st " + cls} title=${t(label)}>${letter}</span><span class="fname">${f.path}</span>
            </button>
          </li>`;
        })}
      </ul>
    </div>
    ${palette && html`<${FilePalette} files=${palette} onClose=${() => setPalette(null)}
      onPick=${(path) => { setPalette(null); app.select({ kind: "worktree", path }); }} />`}
  </aside>`;
}

export function WorktreeEditor() {
  const app = useApp();
  const { path } = app.selection;
  const [file, setFile] = useState(null);
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);
  const draft = useRef(null);   // edits live here, not in props, so typing never reloads the editor
  const saved = useRef("");     // last saved text; saving must not reload the editor (it would move the cursor)

  useEffect(() => {
    setFile(null); setError(null); setDirty(false); app.setDirty(null);
    draft.current = null;
    api.get(`/api/projects/${app.project.id}/file${q({ path })}`)
      .then((f) => { saved.current = f.current; setFile(f); })
      .catch((e) => setError(e.message));
  }, [path, app.commitVersion]);

  const save = async () => {
    if (draft.current == null) return;
    try {
      await api.put(`/api/projects/${app.project.id}/file`, { path, content: draft.current });
      saved.current = draft.current;
      setDirty(false); app.setDirty(null);
      app.toast(t("changes.saved"));
      app.bumpStatus();
    } catch (e) { app.toast(e.message, true); }
  };

  if (error) return html`<div class="placeholder"><p class="error-box">${error}</p></div>`;
  if (!file) return html`<div class="placeholder"><span class="spinner"></span></div>`;
  return html`
    <div class="editor-head">
      <div class="title"><strong>${path}</strong>
        <span class="muted">${dirty ? t("changes.unsaved") : ""}</span></div>
      <span class="muted" style="font-size:12px">${t("changes.headLabel")} → ${t("changes.workingLabel")}</span>
      <button class="btn primary" disabled=${!dirty} onClick=${save} title="Ctrl+S"><${Icon} name="save" /> ${t("changes.save")}</button>
    </div>
    <div class="editor-host">
      ${file.binary ? html`<div class="placeholder">${t("diff.binary")}</div>`
        : html`<${EditorGate}>${(monaco) => html`<${DiffView} monaco=${monaco} original=${file.head} modified=${file.current}
            language=${file.language} editable=${true} sideBySide=${app.sideBySide} theme=${app.theme}
            onChange=${(text) => { draft.current = text; const d = text !== saved.current; setDirty(d); app.setDirty(d ? path : null); }}
            onSave=${save}
            onAsk=${(sel, explain) => app.askAbout({ path, commit: "", text: sel.text, side: sel.side }, explain)} />`}<//>`}
    </div>`;
}
