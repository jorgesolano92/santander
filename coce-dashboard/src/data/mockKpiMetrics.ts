import type { CoceLiveContextValue } from '../context/CoceLiveContext';

export type BranchKpiMetrics = {
  modosConfigurados: number;
  camarasActivas: number;
  camarasTotales: number;
  alertasCriticas: number;
  mensajesHoy: number;
  accionesHoy: number;
};

function branchSeed(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i += 1) {
    h = (h * 31 + id.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

/** Métricas mock estables por sucursal (hasta tener endpoints reales). */
export function getMockBranchKpis(branchId: string): BranchKpiMetrics {
  const seed = branchSeed(branchId);
  const camarasTotales = 4 + (seed % 5);
  const camarasActivas = Math.max(0, camarasTotales - (seed % 3));
  return {
    modosConfigurados: 6 + (seed % 7),
    camarasActivas,
    camarasTotales,
    alertasCriticas: seed % 9,
    mensajesHoy: 8 + (seed % 24),
    accionesHoy: 12 + (seed % 31),
  };
}

function sumMetrics(list: BranchKpiMetrics[]): BranchKpiMetrics {
  return list.reduce(
    (acc, m) => ({
      modosConfigurados: acc.modosConfigurados + m.modosConfigurados,
      camarasActivas: acc.camarasActivas + m.camarasActivas,
      camarasTotales: acc.camarasTotales + m.camarasTotales,
      alertasCriticas: acc.alertasCriticas + m.alertasCriticas,
      mensajesHoy: acc.mensajesHoy + m.mensajesHoy,
      accionesHoy: acc.accionesHoy + m.accionesHoy,
    }),
    {
      modosConfigurados: 0,
      camarasActivas: 0,
      camarasTotales: 0,
      alertasCriticas: 0,
      mensajesHoy: 0,
      accionesHoy: 0,
    },
  );
}

function liveBonus(branchId: string, live: CoceLiveContextValue): number {
  if (!live.connected) return 0;
  const info = live.getLiveBranch(branchId);
  if (!info?.lastEventTs) return 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (info.lastEventTs < today.getTime()) return 0;
  return 1;
}

export function resolveKpiMetrics(
  branchIds: string[],
  live: CoceLiveContextValue,
): BranchKpiMetrics {
  const baseList = branchIds.map((id) => {
    const mock = getMockBranchKpis(id);
    return {
      ...mock,
      accionesHoy: mock.accionesHoy + liveBonus(id, live),
    };
  });
  return sumMetrics(baseList);
}
