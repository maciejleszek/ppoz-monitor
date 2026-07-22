// Klient API.
// - lokalnie: VITE_API_URL puste -> zapytania idą przez proxy Vite (/api),
// - na Render: VITE_API_URL to hostname backendu (z render.yaml) -> https://host.

const raw = import.meta.env.VITE_API_URL || "";
export const API_BASE = raw
  ? raw.startsWith("http")
    ? raw.replace(/\/$/, "")
    : `https://${raw}`
  : "";

function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === "" || value === null || value === undefined || value === false) return;
    search.set(key, value);
  });
  const str = search.toString();
  return str ? `?${str}` : "";
}

async function get(path, params) {
  const res = await fetch(`${API_BASE}${path}${qs(params)}`);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export function getTenders({ q, region, source, sort, activeOnly, page }) {
  return get("/api/tenders", {
    q,
    region,
    source,
    sort,
    active_only: activeOnly ? "true" : "",
    page,
    page_size: 20,
  });
}

export const getStats = () => get("/api/stats");
export const getRegions = () => get("/api/regions");
