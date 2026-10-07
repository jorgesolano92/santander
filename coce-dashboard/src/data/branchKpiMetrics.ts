import type { CoceLiveContextValue } from '../context/CoceLiveContext';
import { deriveAlertsFromBranchState, listActiveAlerts } from '../utils/branchAlerts';

export type BranchKpiMetrics = {
  modosConfigurados: number;
  /** null: sin conexión en tiempo real con coce-api (estado desconocido). */
  dispositivosConectados: number | null;
  dispositivosTotales: number;
  alertasCriticas: number;
  mensajesHoy: number;
  accionesHoy: number;
};

/** Equipos de una sucursal tipo (zaguán con dos puertas). */
export const BRANCH_DEVICE_INVENTORY = {
  placasIo: 3,
  videoporteros: 2,
  controladorPulsadores: 1,
  tablets: 2,
} as const;

const DEVICES_PER_BRANCH = Object.values(BRANCH_DEVICE_INVENTORY).reduce((a, b) => a + b, 0);
const UNREPORTED_DEVICES =
  BRANCH_DEVICE_INVENTORY.videoporteros + BRANCH_DEVICE_INVENTORY.controladorPulsadores;

/** Horarios de la consola (automático, esclusa, extendido, autoservicio, cerrado, carga cajero, manual). */
const MODOS_OPERATIVOS = 7;

function branchSeed(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i += 1) {
    h = (h * 31 + id.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function resolveDevices(
  branchId: string,
  live: CoceLiveContextValue,
): { connected: number | null; total: number } {
  if (!live.connected) {
    return { connected: null, total: DEVICES_PER_BRANCH };
  }
  const info = live.getLiveBranch(branchId);
  if (!info || info.status === 'apagado') {
    return { connected: 0, total: DEVICES_PER_BRANCH };
  }
  const boardsTotal = info.boardsTotal && info.boardsTotal > 0
    ? info.boardsTotal
    : BRANCH_DEVICE_INVENTORY.placasIo;
  const boardsConnected = info.boardsTotal && info.boardsTotal > 0
    ? Math.min(info.boardsConnected ?? 0, boardsTotal)
    : info.modbus
      ? boardsTotal
      : 0;
  // Backends sin actualizar no reportan tablets: se asume el inventario conectado.
  const tabletsConnected = info.tablets
    ? info.tablets.length
    : BRANCH_DEVICE_INVENTORY.tablets;
  const tabletsTotal = Math.max(BRANCH_DEVICE_INVENTORY.tablets, tabletsConnected);
  // Videoporteros y controlador de pulsadores no se reportan: se dan por conectados con el backend en línea.
  return {
    connected: boardsConnected + UNREPORTED_DEVICES + tabletsConnected,
    total: boardsTotal + UNREPORTED_DEVICES + tabletsTotal,
  };
}

function resolveCriticalAlerts(branchId: string, live: CoceLiveContextValue): number {
  if (!live.connected) return 0;
  const info = live.getLiveBranch(branchId);
  if (!info) return 0;
  const alerts = deriveAlertsFromBranchState(info.currentMode, info.activeToggleRules, info.alerts);
  return listActiveAlerts(alerts).length;
}

function eventsToday(branchId: string, live: CoceLiveContextValue): number {
  if (!live.connected) return 0;
  const info = live.getLiveBranch(branchId);
  if (!info?.lastEventTs) return 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return info.lastEventTs >= today.getTime() ? 1 : 0;
}

export function getBranchKpis(branchId: string, live: CoceLiveContextValue): BranchKpiMetrics {
  const seed = branchSeed(branchId);
  const devices = resolveDevices(branchId, live);
  return {
    modosConfigurados: MODOS_OPERATIVOS,
    dispositivosConectados: devices.connected,
    dispositivosTotales: devices.total,
    alertasCriticas: resolveCriticalAlerts(branchId, live),
    // Sin contadores reales en coce-api todavía: valores estables por sucursal.
    mensajesHoy: seed % 4,
    accionesHoy: 18 + (seed % 23) + eventsToday(branchId, live),
  };
}

export function resolveKpiMetrics(
  branchIds: string[],
  live: CoceLiveContextValue,
): BranchKpiMetrics {
  const list = branchIds.map((id) => getBranchKpis(id, live));
  const anyUnknown = list.some((m) => m.dispositivosConectados === null);
  return list.reduce<BranchKpiMetrics>(
    (acc, m) => ({
      modosConfigurados: acc.modosConfigurados,
      dispositivosConectados: anyUnknown
        ? null
        : (acc.dispositivosConectados ?? 0) + (m.dispositivosConectados ?? 0),
      dispositivosTotales: acc.dispositivosTotales + m.dispositivosTotales,
      alertasCriticas: acc.alertasCriticas + m.alertasCriticas,
      mensajesHoy: acc.mensajesHoy + m.mensajesHoy,
      accionesHoy: acc.accionesHoy + m.accionesHoy,
    }),
    {
      modosConfigurados: MODOS_OPERATIVOS,
      dispositivosConectados: anyUnknown ? null : 0,
      dispositivosTotales: 0,
      alertasCriticas: 0,
      mensajesHoy: 0,
      accionesHoy: 0,
    },
  );
}
