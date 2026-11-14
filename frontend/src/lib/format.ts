export function fmtDuration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "—";
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h} h ${String(m).padStart(2, "0")}`;
  if (m > 0) return `${m} min`;
  return `${s} s`;
}

export function fmtRelative(ts?: number | null): string {
  if (!ts) return "—";
  const diff = Date.now() / 1000 - ts;
  if (diff < 45) return "à l'instant";
  if (diff < 3600) return `il y a ${Math.round(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.round(diff / 3600)} h`;
  return `il y a ${Math.round(diff / 86400)} j`;
}

export function fmtDate(ts?: number | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtNumber(n?: number | null, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("fr-FR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export const STATUS_TEXT: Record<string, string> = {
  docked: "Sur la station",
  charging: "En charge",
  cleaning: "Nettoyage en cours",
  paused: "En pause",
  returning: "Retour à la station",
  stopped: "Arrêté",
  error: "Erreur",
  bin_full: "Bac plein",
  emptying: "Vidage du bac",
  idle: "Au repos",
  unknown: "État inconnu",
  unconfigured: "Non appairé",
  connecting: "Connexion…",
  reconnecting: "Reconnexion…",
  online: "En ligne",
  offline: "Hors ligne",
  auth_error: "Authentification refusée",
  no_host: "Adresse introuvable",
};

export function statusText(s?: string | null): string {
  if (!s) return "—";
  return STATUS_TEXT[s] ?? s;
}

export const KIND_ICON: Record<string, string> = {
  robot: "◉",
  router: "⌂",
  tv: "▣",
  speaker: "♪",
  phone: "▤",
  computer: "▭",
  iot: "◇",
  printer: "⎙",
  nas: "▦",
  unknown: "·",
};
