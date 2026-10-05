import type { PanelBoardState } from '../types';
import {
  deriveAlertsFromBranchState,
  type BranchAlertType,
  type BranchAlertsMap,
} from './branchAlerts';

export type PanelLoadState = {
  modes: import('../types').PanelModeRule[];
  currentMode: string | null;
  activeToggleRules: string[];
  branchAlerts: BranchAlertsMap;
  boards: Array<{ id: string; data: PanelBoardState }>;
  modulesConfig: import('../types').PanelModuleConfig[];
  panelTimestamp: string | null;
  panelOk: boolean;
  panelError: string | null;
};

function syncDerivedAlerts(state: PanelLoadState): PanelLoadState {
  return {
    ...state,
    branchAlerts: deriveAlertsFromBranchState(
      state.currentMode,
      state.activeToggleRules,
      state.branchAlerts,
    ),
  };
}

/** Aplica un evento WS de sucursal sin volver a pedir snapshot (evita ~5s de Modbus remoto). */
export function applyLivePatch(
  prev: PanelLoadState,
  eventType: string,
  payload: Record<string, unknown>,
): PanelLoadState | null {
  if (eventType === 'heartbeat') {
    const mode = payload.current_mode;
    return syncDerivedAlerts({
      ...prev,
      currentMode:
        mode === undefined
          ? prev.currentMode
          : (mode as string | null),
    });
  }

  if (eventType === 'mode_changed') {
    return syncDerivedAlerts({
      ...prev,
      currentMode: (payload.current_mode as string | null) ?? null,
    });
  }

  if (eventType === 'toggle_rules_changed') {
    const rules = payload.active_toggle_rules;
    return syncDerivedAlerts({
      ...prev,
      activeToggleRules: Array.isArray(rules) ? rules.map(String) : [],
    });
  }

  if (eventType === 'branch_alert') {
    const alertType = String(payload.alert_type ?? '') as BranchAlertType;
    if (alertType !== 'fire' && alertType !== 'emergency') return null;
    const nextAlerts = { ...prev.branchAlerts };
    if (payload.active) {
      nextAlerts[alertType] = {
        alert_type: alertType,
        active: true,
        rule_key: payload.rule_key as string | undefined,
        message: payload.message as string | undefined,
        current_mode: (payload.current_mode as string | null) ?? null,
        active_toggle_rules: Array.isArray(payload.active_toggle_rules)
          ? payload.active_toggle_rules.map(String)
          : undefined,
      };
    } else {
      delete nextAlerts[alertType];
    }
    return syncDerivedAlerts({
      ...prev,
      branchAlerts: nextAlerts,
    });
  }

  if (eventType === 'output_changed') {
    const boardId = String(payload.board_id ?? '');
    const channel = Number(payload.channel);
    const state = Boolean(payload.state);
    if (!boardId || !channel) return null;
    return {
      ...prev,
      boards: prev.boards.map((b) => {
        if (b.id !== boardId) return b;
        const outs = [...(b.data.outputs ?? [])];
        while (outs.length < channel) outs.push(false);
        outs[channel - 1] = state;
        return { id: b.id, data: { ...b.data, outputs: outs } };
      }),
    };
  }

  if (eventType === 'input_override') {
    const boardId = String(payload.board_id ?? '');
    const channel = Number(payload.channel);
    if (!boardId || !channel) return null;
    const override = payload.override as boolean | null | undefined;
    return {
      ...prev,
      boards: prev.boards.map((b) => {
        if (b.id !== boardId) return b;
        const ov = [...(b.data.input_overrides ?? [])];
        while (ov.length < channel) ov.push(null);
        ov[channel - 1] = override === undefined ? null : override;
        return { id: b.id, data: { ...b.data, input_overrides: ov } };
      }),
    };
  }

  if (eventType === 'panel_status' || eventType === 'snapshot') {
    const boardsObj = payload.boards as Record<string, PanelBoardState> | undefined;
    if (!boardsObj) return null;
    const boards = Object.entries(boardsObj).map(([bid, b]) => ({
      id: bid,
      data: b,
    }));
    const modules = payload.modules_config as PanelLoadState['modulesConfig'] | undefined;
    const toggleRules = payload.active_toggle_rules;
    return syncDerivedAlerts({
      ...prev,
      currentMode:
        payload.current_mode !== undefined
          ? (payload.current_mode as string | null)
          : prev.currentMode,
      activeToggleRules: Array.isArray(toggleRules)
        ? toggleRules.map(String)
        : prev.activeToggleRules,
      boards,
      modulesConfig: modules ?? prev.modulesConfig,
      panelTimestamp:
        typeof payload.timestamp === 'string' ? payload.timestamp : prev.panelTimestamp,
      panelOk: true,
      panelError: null,
    });
  }

  if (eventType === 'board_connected' || eventType === 'board_disconnected') {
    const boardId = String(payload.board_id ?? '');
    const connected = Boolean(payload.connected);
    if (!boardId) return null;
    return {
      ...prev,
      boards: prev.boards.map((b) =>
        b.id === boardId ? { id: b.id, data: { ...b.data, connected } } : b,
      ),
    };
  }

  return null;
}
