// Tiny translation layer: t("key", {vars}), falling back to English for missing keys.

let strings = {};
let fallback = {};
export let locale = "en";

export async function loadLanguage(lang) {
  const get = (l) => fetch(`/static/i18n/${l}.json`, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : {}));
  fallback = await get("en");
  strings = lang === "en" ? fallback : { ...fallback, ...(await get(lang)) };
  locale = lang;
  document.documentElement.lang = lang;
}

export function t(key, vars = {}) {
  const template = strings[key] ?? fallback[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => (name in vars ? String(vars[name]) : `{${name}}`));
}

/** "3 days ago" in the current language. */
export function relativeTime(iso) {
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000;
  const units = [["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]];
  const fmt = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return fmt.format(Math.round(seconds / size), unit);
  }
  return fmt.format(0, "minute");
}

export function longDate(iso) {
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
}

export function number(n, digits = 0) {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(n);
}
