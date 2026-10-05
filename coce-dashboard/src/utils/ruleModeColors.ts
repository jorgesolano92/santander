export const DEFAULT_MODE_COLORS: Record<string, string> = {
  horario_automatico: '#22c55e',
  horario_esclusa: '#3b82f6',
  horario_extendido: '#eab308',
  horario_autoservicio: '#a855f7',
  horario_cerrado: '#6b7280',
  horario_carga_cajero: '#f97316',
  horario_manual: '#ef4444',
  senal_de_incendio_activada: '#E85D04',
};

const FALLBACK_COLOR = '#6b7280';

export function ruleKeyToLabel(ruleKey: string | null | undefined): string | null {
  if (!ruleKey) return null;
  return ruleKey.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function resolveRuleColor(
  ruleKey: string | null | undefined,
  customColor?: string | null,
): string {
  const value = String(customColor || '').trim();
  if (/^#[0-9a-f]{6}$/i.test(value)) return value;
  if (ruleKey) return DEFAULT_MODE_COLORS[ruleKey] ?? FALLBACK_COLOR;
  return FALLBACK_COLOR;
}

export type ModeDisplay = {
  modeKey: string | null;
  modeLabel: string | null;
  modeColor: string;
};

export function resolveBranchModeDisplay(
  stored: {
    currentMode?: string | null;
    modeLabel?: string | null;
    modeColor?: string | null;
  } | undefined,
  liveMode?: string | null,
  liveConnected?: boolean,
): ModeDisplay {
  const modeKey =
    liveConnected && liveMode ? liveMode : stored?.currentMode ?? liveMode ?? null;
  if (!modeKey) {
    return {
      modeKey: null,
      modeLabel: stored?.modeLabel ?? null,
      modeColor: stored?.modeColor ?? FALLBACK_COLOR,
    };
  }
  const useStored =
    stored?.currentMode === modeKey && (stored.modeLabel || stored.modeColor);
  return {
    modeKey,
    modeLabel: useStored ? stored?.modeLabel ?? ruleKeyToLabel(modeKey) : ruleKeyToLabel(modeKey),
    modeColor: resolveRuleColor(
      modeKey,
      stored?.currentMode === modeKey ? stored?.modeColor : null,
    ),
  };
}
