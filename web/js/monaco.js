// Monaco (VS Code's editor): loading, GitLore themes, and the diff view with "Ask GitLore" actions.
import { html, useEffect, useRef } from "../vendor/preact-htm.module.js";
import { t } from "./i18n.js";

let loading = null;

const addScript = (src) => new Promise((resolve, reject) => {
  const script = document.createElement("script");
  script.src = src;
  script.onload = resolve;
  script.onerror = () => reject(new Error("editor files missing"));
  document.head.appendChild(script);
});

/** Load Monaco once, with its menus in `lang` (tr, fr and de ship with Monaco). */
export function loadMonaco(basePath, lang) {
  if (loading) return loading;
  loading = (async () => {
    // Monaco's translations are plain scripts that set globals; they must run before the editor loads.
    const nls = { zh: "zh-cn" }[lang] || lang;  // Monaco names Simplified Chinese "zh-cn"
    if (lang !== "en") await addScript(`${basePath}/nls/lang/${nls}.js`).catch(() => {});
    await addScript(`${basePath}/loader.js`);
    window.require.config({ paths: { vs: basePath } });
    await new Promise((resolve, reject) => window.require(["vs/editor/editor.main"], resolve, reject));
    return window.monaco;
  })();
  return loading;
}

const DARK = new Set(["dark", "dim", "solarized-dark", "contrast-dark"]);
const defined = new Set();

/**
 * Monaco theme built from the app's CSS variables, so every GitLore theme (styles.css) has a matching
 * editor theme without keeping two color lists in sync. Call after data-theme is set on <html>.
 */
export function monacoTheme(theme) {
  const name = `gitlore-${theme}`;
  const monaco = window.monaco;
  if (!monaco || defined.has(name)) return name;
  const css = getComputedStyle(document.documentElement);
  const v = (k) => css.getPropertyValue(k).trim();
  const contrast = theme.startsWith("contrast-");
  monaco.editor.defineTheme(name, {
    base: contrast ? (DARK.has(theme) ? "hc-black" : "hc-light") : DARK.has(theme) ? "vs-dark" : "vs",
    inherit: true, rules: [],
    colors: {
      "editor.background": v("--panel"), "editorGutter.background": v("--panel"),
      "editor.lineHighlightBackground": v("--raised"), "editorLineNumber.foreground": v("--muted"),
      "editor.selectionBackground": v("--accent-soft"), "focusBorder": v("--accent"),
      "diffEditor.insertedTextBackground": v("--add") + "33", "diffEditor.removedTextBackground": v("--del") + "33",
      "diffEditor.insertedLineBackground": v("--add") + "18", "diffEditor.removedLineBackground": v("--del") + "18",
    },
  });
  defined.add(name);
  return name;
}

/**
 * Side-by-side (or inline) diff. Left = before, right = after.
 * editable: the right side can be edited (working tree); onChange/onSave are then used.
 * onAsk({text, side}, explain) is called from the right-click menu on a selection.
 */
export function DiffView({ monaco, original, modified, language, editable = false, sideBySide = true,
                           theme, collapseUnchanged = false, onAsk, onChange, onSave }) {
  const host = useRef(null);
  const editor = useRef(null);
  const handlers = useRef({});
  const content = useRef({});
  const changeSub = useRef(null);
  handlers.current = { onAsk, onChange, onSave };
  content.current = { original, modified, language };

  // Put the current before/after text into the editor (used on create and whenever the text changes).
  const applyModel = () => {
    const diff = editor.current;
    if (!diff) return;
    const old = diff.getModel();
    const { original: before, modified: after, language: lang } = content.current;
    if (old && old.original.getValue() === before && old.modified.getValue() === after &&
        old.modified.getLanguageId() === lang) return;  // unchanged: don't cancel a diff that is computing
    const model = { original: monaco.editor.createModel(before, lang), modified: monaco.editor.createModel(after, lang) };
    diff.setModel(model);
    changeSub.current?.dispose();
    changeSub.current = model.modified.onDidChangeContent(() => handlers.current.onChange?.(model.modified.getValue()));
    old?.original.dispose();
    old?.modified.dispose();
  };

  useEffect(() => {
    const diff = monaco.editor.createDiffEditor(host.current, {
      automaticLayout: true, readOnly: !editable, originalEditable: false, renderSideBySide: sideBySide,
      minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false, renderOverviewRuler: true,
      hideUnchangedRegions: { enabled: collapseUnchanged },
      useInlineViewWhenSpaceIsLimited: true, renderSideBySideInlineBreakpoint: 560,
      fontFamily: getComputedStyle(document.documentElement).getPropertyValue("--mono"),
    });
    editor.current = diff;
    const sides = [["original", diff.getOriginalEditor()], ["modified", diff.getModifiedEditor()]];
    for (const [side, ed] of sides) {
      const run = (explain) => () => {
        const selection = ed.getSelection();
        const text = selection && ed.getModel().getValueInRange(selection);
        if (text && text.trim()) handlers.current.onAsk?.({ text, side }, explain);
      };
      ed.addAction({ id: "gitlore.ask", label: t("menu.ask"), contextMenuGroupId: "navigation",
                     contextMenuOrder: 0, precondition: "editorHasSelection", run: run(false) });
      ed.addAction({ id: "gitlore.explain", label: t("menu.explain"), contextMenuGroupId: "navigation",
                     contextMenuOrder: 0.1, precondition: "editorHasSelection", run: run(true) });
    }
    diff.getModifiedEditor().addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => handlers.current.onSave?.());

    // A small "Explain" button at the end of each changed block — no right-click needed.
    let widgets = [];
    const clearWidgets = () => { widgets.forEach(([ed, w]) => ed.removeContentWidget(w)); widgets = []; };
    const placeWidgets = () => {
      clearWidgets();
      if (editable || !handlers.current.onAsk) return;
      (diff.getLineChanges() || []).slice(0, 40).forEach((ch, i) => {
        const added = ch.modifiedEndLineNumber >= ch.modifiedStartLineNumber && ch.modifiedEndLineNumber > 0;
        const ed = added ? diff.getModifiedEditor() : diff.getOriginalEditor();
        const [from, to] = added ? [ch.modifiedStartLineNumber, ch.modifiedEndLineNumber]
                                 : [ch.originalStartLineNumber, ch.originalEndLineNumber];
        const model = ed.getModel();
        if (!model || from < 1 || from > model.getLineCount()) return;
        const node = document.createElement("button");
        node.type = "button";
        node.className = "hunk-explain";
        node.textContent = t("explain.change");
        node.title = t("explain.changeHint");
        node.onmousedown = (e) => e.stopPropagation();
        node.onclick = (e) => {
          e.stopPropagation();
          const text = model.getValueInRange(new monaco.Range(from, 1, to, model.getLineMaxColumn(to)));
          handlers.current.onAsk?.({ text, side: added ? "modified" : "original" }, "change");
        };
        const widget = {
          getId: () => `gitlore.explain.${i}`, getDomNode: () => node,
          getPosition: () => ({ position: { lineNumber: from, column: model.getLineMaxColumn(from) },
                                preference: [monaco.editor.ContentWidgetPositionPreference.EXACT] }),
        };
        ed.addContentWidget(widget);
        widgets.push([ed, widget]);
      });
    };
    const diffSub = diff.onDidUpdateDiff(placeWidgets);
    applyModel();
    return () => {
      const model = diff.getModel();
      diffSub.dispose();
      clearWidgets();
      changeSub.current?.dispose();
      diff.dispose();
      editor.current = null;
      model?.original.dispose();
      model?.modified.dispose();
    };
  }, [monaco, editable, collapseUnchanged]);

  useEffect(applyModel, [original, modified, language]);

  useEffect(() => { editor.current.updateOptions({ renderSideBySide: sideBySide }); }, [sideBySide]);
  // One frame later: the app sets data-theme in its own (parent) effect, which runs after this one.
  useEffect(() => { requestAnimationFrame(() => monaco.editor.setTheme(monacoTheme(theme))); }, [theme]);

  return html`<div class="monaco-host" ref=${host}></div>`;
}
