// Thin client for GitLore's local JSON API.

export class ApiError extends Error {}

async function request(method, url, payload) {
  const init = { method, headers: {} };
  if (payload !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(payload);
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError("offline");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data.error || `HTTP ${res.status}`);
  return data;
}

export const api = {
  get: (url) => request("GET", url),
  post: (url, payload = {}) => request("POST", url, payload),
  put: (url, payload = {}) => request("PUT", url, payload),
  patch: (url, payload = {}) => request("PATCH", url, payload),
  del: (url) => request("DELETE", url),
};

export const q = (params) => "?" + new URLSearchParams(params).toString();

/** Poll a background job until it finishes; onProgress receives the job each time. */
export async function waitForJob(jobId, onProgress, intervalMs = 400) {
  for (;;) {
    const job = await api.get(`/api/jobs/${jobId}`);
    onProgress?.(job);
    if (job.status !== "running") {
      if (job.status === "error") throw new ApiError(job.message);
      return job;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

/** POST a question and read the server-sent events it streams back. */
export async function streamAnswer(chatId, question, focus, onEvent, signal, tags = []) {
  let res;
  try {
    res = await fetch(`/api/chats/${chatId}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, focus, tags }),
      signal,
    });
  } catch (e) {
    if (e.name === "AbortError") return;
    throw new ApiError("offline");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(data.error || `HTTP ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut;
      while ((cut = buffer.indexOf("\n\n")) >= 0) {
        const chunk = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        for (const line of chunk.split("\n")) {
          if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)));
        }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") throw e;
  }
}
