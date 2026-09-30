// Minimal, safe Markdown for model answers. Everything is HTML-escaped first; only the few
// constructs below are turned back into markup, so a model answer can never inject HTML.
// Commit citations like [a1b2c3d] become buttons (data-hash) that open the commit.

const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function inline(text, known) {
  return escape(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([0-9a-f]{7,40})\]/g, (m, hash) =>
      known && !known(hash) ? m : `<button type="button" class="cite" data-hash="${hash}">${hash.slice(0, 7)}</button>`);
}

/** Render `source` to an HTML string. `known(hash)` limits citation chips to real commits. */
export function renderMarkdown(source, known) {
  const out = [];
  const blocks = ("\n" + source.replace(/\r\n/g, "\n")).split(/\n```/);
  blocks.forEach((block, i) => {
    if (i % 2 === 1) { // fenced code: first line is the language tag
      const body = block.replace(/^[^\n]*\n?/, "").replace(/```\s*$/, "");
      out.push(`<pre><code>${escape(body)}</code></pre>`);
      return;
    }
    const text = i === 0 ? block : block.replace(/^\n/, "");
    let list = null;
    const flush = () => { if (list) { out.push(`</${list}>`); list = null; } };
    let para = [];
    const flushPara = () => { if (para.length) { out.push(`<p>${inline(para.join(" "), known)}</p>`); para = []; } };
    for (const line of text.split("\n")) {
      const ul = line.match(/^\s*[-*]\s+(.*)$/);
      const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
      if (ul || ol) {
        flushPara();
        const kind = ul ? "ul" : "ol";
        if (list !== kind) { flush(); out.push(`<${kind}>`); list = kind; }
        out.push(`<li>${inline((ul || ol)[1], known)}</li>`);
      } else if (!line.trim()) {
        flushPara(); flush();
      } else {
        flush();
        para.push(line.replace(/^#{1,6}\s+/, ""));
      }
    }
    flushPara(); flush();
  });
  return out.join("");
}
