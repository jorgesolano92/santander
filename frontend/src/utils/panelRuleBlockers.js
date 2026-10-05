/** Comprueba si entradas/salidas de bloqueo de una regla están activas (estado panel en RAM). */

function parseInCode(code) {
  const m = /^IN_(\d+)_(\d+)$/i.exec(String(code || "").trim());
  if (!m) return null;
  return { boardId: Number(m[1]), channel: Number(m[2]) };
}

function parseOutCode(code) {
  const m = /^OUT_(\d+)_(\d+)$/i.exec(String(code || "").trim());
  if (!m) return null;
  return { boardId: Number(m[1]), channel: Number(m[2]) };
}

export function isPanelSignalActive(code, boards) {
  const raw = String(code || "").trim();
  if (!raw) return false;
  const head = raw.split("_")[0].toUpperCase();
  if (head === "OUT" || head === "DO") {
    const p = parseOutCode(raw);
    if (!p) return false;
    const b = boards[p.boardId];
    if (!b) return false;
    return Boolean((b.outputs || [])[p.channel - 1]);
  }
  const p = parseInCode(raw);
  if (!p) return false;
  const b = boards[p.boardId];
  if (!b) return false;
  return Boolean((b.inputs || [])[p.channel - 1]);
}

export function ruleBlockersActive(ruleKey, rulesMap, boards) {
  const rule = rulesMap?.[ruleKey];
  if (!rule) return false;
  const codes = rule.blocked_if_active;
  if (!Array.isArray(codes) || codes.length === 0) return false;
  return codes.some((code) => isPanelSignalActive(code, boards));
}
