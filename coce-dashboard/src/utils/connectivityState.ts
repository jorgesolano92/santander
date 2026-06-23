import type { CoceLiveContextValue } from '../context/CoceLiveContext';
import type { SucursalEstado } from '../types';

/** Estado de conectividad / operación en el mapa COCE. */
export type ConnectivityState = 'activo' | 'inactivo' | 'desconectado';

export const CONNECTIVITY_LABELS: Record<ConnectivityState, string> = {
  activo: 'Activo',
  inactivo: 'Inactivo',
  desconectado: 'Desconectado',
};

export const CONNECTIVITY_DESCRIPTIONS: Record<ConnectivityState, string> = {
  activo: 'Operando con normalidad',
  inactivo: 'Apagado o fuera de horario',
  desconectado: 'Sin comunicación con la central',
};

/** Color del pin en el mapa por estado de conectividad. */
export const CONNECTIVITY_PIN_COLORS: Record<ConnectivityState, string> = {
  activo: '#22c55e',
  inactivo: '#9ca3af',
  desconectado: '#dc2626',
};

const CLOSED_MODES = new Set(['horario_cerrado']);

export function resolveConnectivityState(
  branchId: string,
  options: {
    live: CoceLiveContextValue;
    manualEstado?: SucursalEstado;
    locationReachable: boolean;
    currentMode?: string | null;
  },
): ConnectivityState {
  const { live, manualEstado, locationReachable, currentMode } = options;
  const modeClosed = currentMode != null && CLOSED_MODES.has(currentMode);

  if (live.connected) {
    const liveBranch = live.getLiveBranch(branchId);
    const wsStatus = live.getLiveStatus(branchId);
    if (!liveBranch?.wsConnected || wsStatus === 'apagado' || !wsStatus) {
      return 'desconectado';
    }
    if (modeClosed || wsStatus === 'no_operativo') {
      return 'inactivo';
    }
    return 'activo';
  }

  if (!locationReachable) {
    return 'desconectado';
  }
  if (modeClosed) {
    return 'inactivo';
  }
  const manual = manualEstado ?? 'operativo';
  if (manual === 'operativo') return 'activo';
  if (manual === 'no_operativo') return 'inactivo';
  return 'desconectado';
}

/** Mapeo filtro legacy (operativo / no_operativo / apagado) → conectividad. */
export function connectivityFromLegacyEstado(estado: SucursalEstado): ConnectivityState {
  if (estado === 'operativo') return 'activo';
  if (estado === 'no_operativo') return 'inactivo';
  return 'desconectado';
}

export function legacyEstadoFromConnectivity(state: ConnectivityState): SucursalEstado {
  if (state === 'activo') return 'operativo';
  if (state === 'inactivo') return 'no_operativo';
  return 'apagado';
}
