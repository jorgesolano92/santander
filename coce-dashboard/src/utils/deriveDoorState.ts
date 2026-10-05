import type { PanelBoardState } from '../types';

/** Estado de puerta derivado de salidas Modbus (placa 2 = calle, placa 3 = oficina). */
export type DoorState = 'abierta' | 'cerrada' | 'bloqueada' | 'no_operativa';

export const DOOR_STATE_LABELS: Record<DoorState, string> = {
  abierta: 'Abierta',
  cerrada: 'Cerrada',
  bloqueada: 'Bloqueada',
  no_operativa: 'No operativa',
};

export const DOOR_STATE_HINTS: Record<DoorState, string> = {
  abierta: 'OUT 7 encendido',
  cerrada: 'OUT 7 apagado',
  bloqueada: 'OUT 1 y OUT 2 encendidos (prioridad sobre OUT 7)',
  no_operativa: 'Placa desconectada o sin lectura de salidas',
};

function outputOn(outputs: boolean[] | undefined, channel: number): boolean {
  return Boolean(outputs?.[channel - 1]);
}

/** OUT1+OUT2 → bloqueada; si no, OUT7 → abierta; si no → cerrada. */
export function deriveDoorState(board: PanelBoardState | undefined): DoorState {
  if (!board || board.connected === false) {
    return 'no_operativa';
  }
  const outs = board.outputs ?? [];
  if (outputOn(outs, 1) && outputOn(outs, 2)) {
    return 'bloqueada';
  }
  if (outputOn(outs, 7)) {
    return 'abierta';
  }
  return 'cerrada';
}

export const DOOR_BOARD_CONFIG = [
  { id: 'calle', boardId: '2', name: 'Puerta calle' },
  { id: 'oficina', boardId: '3', name: 'Puerta oficina' },
] as const;
