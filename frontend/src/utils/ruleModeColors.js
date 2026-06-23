/** Colores por defecto si el modo no tiene `color` en panel_rules.json */
export const DEFAULT_MODE_COLORS = {
  horario_automatico: "#22c55e",
  horario_esclusa: "#3b82f6",
  horario_extendido: "#eab308",
  horario_autoservicio: "#a855f7",
  horario_cerrado: "#6b7280",
  horario_carga_cajero: "#f97316",
  horario_manual: "#ef4444",
};

const FALLBACK_COLOR = "#6b7280";

export function normalizeRuleColor(raw, ruleKey) {
  const value = String(raw || "").trim();
  if (/^#[0-9a-f]{6}$/i.test(value)) return value;
  return DEFAULT_MODE_COLORS[ruleKey] || FALLBACK_COLOR;
}

export function resolveRuleColor(ruleKey, rules) {
  const rule = rules?.[ruleKey];
  return normalizeRuleColor(rule?.color, ruleKey);
}

export function ruleKeyToLabel(ruleKey) {
  return String(ruleKey || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
