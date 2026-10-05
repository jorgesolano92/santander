export type BranchAlertType = 'fire' | 'emergency' | 'door_held' | string;

export type BranchAlert = {
  alert_type: BranchAlertType;
  active: boolean;
  rule_key?: string;
  message?: string;
  current_mode?: string | null;
  active_toggle_rules?: string[];
  door?: string;
  held_seconds?: number;
};

export type BranchAlertsMap = Partial<Record<string, BranchAlert>>;

export function parseBranchAlerts(raw: unknown): BranchAlertsMap {
  if (!raw || typeof raw !== 'object') return {};
  const out: BranchAlertsMap = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!value || typeof value !== 'object') continue;
    const v = value as BranchAlert;
    if (v.active) {
      out[key] = { ...v, alert_type: (v.alert_type || key) as BranchAlertType };
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
  return Object.values(alerts).some((a) => Boolean(a?.active));
}

export function listActiveAlerts(alerts: BranchAlertsMap): BranchAlert[] {
  return Object.values(alerts).filter((a): a is BranchAlert => Boolean(a?.active));
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
  const t = String(alert.alert_type || '');
  if (t === 'fire') return 'Alarma de incendio';
  if (t === 'emergency') return 'Emergencia en sucursal';
  if (t.startsWith('door_held')) {
    const door = alert.door || t.replace('door_held_', '').toUpperCase();
    return `Puerta abierta (${door})`;
  }
  return t || 'Alerta';
}
