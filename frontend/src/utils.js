// Formatowanie dat i statusów terminów.

export function fmtDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function fmtDateTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pl-PL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Ile pełnych dni zostało do terminu (null gdy brak terminu).
export function daysLeft(deadline) {
  if (!deadline) return null;
  const d = new Date(deadline);
  if (Number.isNaN(d.getTime())) return null;
  return Math.floor((d.getTime() - Date.now()) / 86400000);
}

// Status używany do koloru "szyny strefowej" na karcie.
export function deadlineStatus(deadline) {
  const left = daysLeft(deadline);
  if (left === null) return "none";
  if (left < 0) return "closed";
  if (left <= 5) return "urgent";
  if (left <= 14) return "soon";
  return "open";
}

export function daysLeftLabel(left) {
  if (left === null) return "";
  if (left < 0) return "po terminie";
  if (left === 0) return "termin dziś";
  if (left === 1) return "został 1 dzień";
  return `zostało ${left} dni`;
}

export const SOURCE_LABELS = { bzp: "BZP", ted: "TED" };
