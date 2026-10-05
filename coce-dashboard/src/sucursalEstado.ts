import type { Sucursal, SucursalEstado } from './types';

export const SUCURSAL_ESTADO_LABELS: Record<SucursalEstado, string> = {
  operativo: 'Operativo',
  no_operativo: 'No operativo',
  apagado: 'Apagado',
};

export function getSucursalEstado(s: Sucursal): SucursalEstado {
  return s.estado ?? 'operativo';
}
