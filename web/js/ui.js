// Shared app context and small building blocks: dialogs, toasts, project switcher, file palette.
import { html, createContext, useContext, useEffect, useRef, useState } from "../vendor/preact-htm.module.js";
import { Icon } from "./icons.js";
import { t, number } from "./i18n.js";

export const AppCtx = createContext(null);
export const useApp = () => useContext(AppCtx);

/** Stable color per author, drawn from a muted palette that works in light and dark. */
const AUTHOR_COLORS = ["#2A7A6F", "#8250DF", "#BC4C00", "#0969DA", "#BF3989", "#6E7781", "#1A7F37", "#9A6700"];
export function authorColor(name) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AUTHOR_COLORS[h % AUTHOR_COLORS.length];
}

export function Dialog({ title, children, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    ref.current?.querySelector("input, textarea, .primary, button")?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); previous?.focus?.(); };
  }, []);
  return html`<div class="backdrop" onMouseDown=${(e) => e.target === e.currentTarget && onClose()}>
    <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title" ref=${ref}>
      <h2 id="dialog-title">${title}</h2>
      ${children}
    </div>
  </div>`;
}

/** Confirmation for destructive actions. */
export function ConfirmDialog({ title, body, action, onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  return html`<${Dialog} title=${title} onClose=${onClose}>
    <p>${body}</p>
    <div class="actions">
      <button class="btn" onClick=${onClose}>${t("confirm.cancel")}</button>
      <button class="btn danger primary" disabled=${busy}
        onClick=${async () => { setBusy(true); try { await onConfirm(); } finally { onClose(); } }}>${action}</button>
    </div>
  <//>`;
}

/** A one-field prompt (rename, commit message elsewhere). */
export function PromptDialog({ title, label, value = "", action, onSubmit, onClose, placeholder = "" }) {
  const [text, setText] = useState(value);
  const [error, setError] = useState(null);
  const submit = async (e) => {
    e.preventDefault();
    try { await onSubmit(text.trim()); onClose(); } catch (err) { setError(err.message); }
  };
  return html`<${Dialog} title=${title} onClose=${onClose}>
    <form onSubmit=${submit}>
      <label class="field"><span>${label}</span>
        <input class="input" value=${text} placeholder=${placeholder} autocomplete="off" spellcheck="false"
          onInput=${(e) => setText(e.target.value)} />
      </label>
      ${error && html`<p class="error-box" role="alert">${error}</p>`}
      <div class="actions">
        <button type="button" class="btn" onClick=${onClose}>${t("confirm.cancel")}</button>
        <button type="submit" class="btn primary" disabled=${!text.trim()}>${action}</button>
      </div>
    </form>
  <//>`;
}

export function Toasts({ toasts }) {
  return html`<div class="toasts" role="status" aria-live="polite">
    ${toasts.map((x) => html`<div key=${x.id} class=${"toast" + (x.error ? " error" : "")}>${x.text}</div>`)}
  </div>`;
}

export function Progress({ value }) {
  return html`<div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow=${Math.round(value)}>
    <i style=${{ width: `${Math.max(2, Math.min(100, value))}%` }}></i></div>`;
}

/** Project picker at the top of the sidebar. */
export function ProjectSwitch() {
  const app = useApp();
  const [open, setOpen] = useState(false);
  const project = app.project;
  const box = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = (e) => !box.current?.contains(e.target) && setOpen(false);
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  if (!project) return null;
  const job = app.indexJobs[project.id];
  const sub = !project.available ? t("project.unavailable")
    : job ? t("project.indexing", { done: job.done, total: job.total || "…" })
    : t("project.indexed", { n: number(project.indexed) });
  return html`<div class="project-switch" ref=${box}>
    <button aria-haspopup="listbox" aria-expanded=${open} title=${t("project.switch")} onClick=${() => setOpen(!open)}>
      <${Icon} name="repo" />
      <span class="grow">
        <span class="row"><span class="name">${project.name}</span>${project.is_demo && html`<span class="tag">${t("project.demo")}</span>`}</span>
        <span class="sub" style="display:block">${sub}</span>
      </span>
      <${Icon} name="chevron" />
    </button>
    ${open && html`<div class="menu" role="listbox" aria-label=${t("project.switch")}>
      ${app.projects.map((p) => html`<button role="option" aria-selected=${p.id === project.id}
          onClick=${() => { setOpen(false); app.openProject(p.id); }}>
        <span class="grow" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.name}</span>
        ${p.is_demo && html`<span class="tag">${t("project.demo")}</span>`}
        ${p.online && html`<span class="tag" title=${p.remote_url}><${Icon} name="cloud" size=${12} /></span>`}
      </button>`)}
      <hr />
      <button onClick=${() => { setOpen(false); app.showAddProject(); }}><${Icon} name="plus" /> ${t("project.add")}</button>
      <button onClick=${() => { setOpen(false); app.showAddOnline(); }}><${Icon} name="cloud" /> ${t("project.addOnline")}</button>
    </div>`}
  </div>`;
}

/** Quick file picker (Ctrl+P style) for opening a working-tree file to edit. */
export function FilePalette({ files, onPick, onClose }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const matches = files.filter((f) => f.toLowerCase().includes(query.toLowerCase())).slice(0, 200);
  useEffect(() => setActive(0), [query]);
  const key = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(Math.min(active + 1, matches.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(Math.max(active - 1, 0)); }
    else if (e.key === "Enter" && matches[active]) { onPick(matches[active]); }
    else if (e.key === "Escape") onClose();
  };
  return html`<div class="backdrop" style="place-items:start center" onMouseDown=${(e) => e.target === e.currentTarget && onClose()}>
    <div class="palette" role="dialog" aria-label=${t("changes.openFile")}>
      <input class="input" autofocus placeholder=${t("changes.filter")} value=${query} spellcheck="false" autocomplete="off"
        role="combobox" aria-expanded="true" aria-controls="palette-list" onInput=${(e) => setQuery(e.target.value)} onKeyDown=${key} />
      <ul id="palette-list" role="listbox">
        ${matches.map((f, i) => html`<li key=${f}><button class="file" role="option" aria-selected=${i === active}
            aria-current=${i === active} onClick=${() => onPick(f)}><${Icon} name="file" /><span class="fname">${f}</span></button></li>`)}
      </ul>
    </div>
  </div>`;
}
