export type BranchAlertType = 'fire' | 'emergency';

export type BranchAlert = {
  alert_type: BranchAlertType;
  active: boolean;
  rule_key?: string;
  message?: string;
  current_mode?: string | null;
  active_toggle_rules?: string[];
};

export type BranchAlertsMap = Partial<Record<BranchAlertType, BranchAlert>>;

export function parseBranchAlerts(raw: unknown): BranchAlertsMap {
  if (!raw || typeof raw !== 'object') return {};
  const out: BranchAlertsMap = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!value || typeof value !== 'object') continue;
    const v = value as BranchAlert;
    if (v.active && (key === 'fire' || key === 'emergency')) {
      out[key] = v;
    }
  }
  return out;
}

export function deriveAlertsFromBranchState(
  currentMode?: string | null,
  activeToggleRules?: string[] | null,
  storedAlerts?: BranchAlertsMap,
): BranchAlertsMap {
  const alerts: BranchAlertsMap = { ...(storedAlerts ?? {}) };
  const fireKey = 'senal_de_incendio_activada';
  if (currentMode === fireKey) {
    alerts.fire = {
      alert_type: 'fire',
      active: true,
      rule_key: fireKey,
      current_mode: currentMode,
      message:
        alerts.fire?.message ??
        'Alarma de incendio activada en la sucursal. Contactar de inmediato con la oficina.',
    };
  } else {
    delete alerts.fire;
  }

  const emergKeys = (activeToggleRules ?? []).filter((k) =>
    k.startsWith('pulsador_emergencia_verde_'),
  );
  if (emergKeys.length > 0) {
    alerts.emergency = {
      alert_type: 'emergency',
      active: true,
      rule_key: emergKeys[0],
      active_toggle_rules: emergKeys,
      current_mode: currentMode,
      message:
        alerts.emergency?.message ??
        'Emergencia activada en la sucursal. Contactar de inmediato con la oficina.',
    };
  } else {
    delete alerts.emergency;
  }
  return alerts;
}

export function hasActiveBranchAlert(alerts: BranchAlertsMap): boolean {
  return Boolean(alerts.fire?.active || alerts.emergency?.active);
}

export function isPanelModeActiveNow(
  ruleKey: string,
  currentMode?: string | null,
  activeToggleRules?: string[] | null,
): boolean {
  if (currentMode === ruleKey) return true;
  return (activeToggleRules ?? []).includes(ruleKey);
}

export function alertTitle(alert: BranchAlert): string {
  if (alert.alert_type === 'fire') return 'Alarma de incendio';
  return 'Emergencia en sucursal';
}
