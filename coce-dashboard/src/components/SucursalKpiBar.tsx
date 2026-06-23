import type { BranchKpiMetrics } from '../data/mockKpiMetrics';

type Props = {
  metrics: BranchKpiMetrics;
  scopeLabel: string;
  selectedBranchId: string | null;
  onClearSelection?: () => void;
};

const KPI_ITEMS: Array<{
  key: keyof BranchKpiMetrics | 'camaras';
  label: string;
  accent: string;
  format: (m: BranchKpiMetrics) => string;
}> = [
  {
    key: 'modosConfigurados',
    label: 'Modos configurados',
    accent: 'var(--accent)',
    format: (m) => String(m.modosConfigurados),
  },
  {
    key: 'camaras',
    label: 'Cámaras activas',
    accent: 'var(--ok)',
    format: (m) => `${m.camarasActivas} / ${m.camarasTotales}`,
  },
  {
    key: 'alertasCriticas',
    label: 'Alertas críticas',
    accent: '#dc2626',
    format: (m) => String(m.alertasCriticas),
  },
  {
    key: 'mensajesHoy',
    label: 'Mensajes hoy',
    accent: '#0f4c81',
    format: (m) => String(m.mensajesHoy),
  },
  {
    key: 'accionesHoy',
    label: 'Acciones hoy',
    accent: '#7c3aed',
    format: (m) => String(m.accionesHoy),
  },
];

export function SucursalKpiBar({
  metrics,
  scopeLabel,
  selectedBranchId,
  onClearSelection,
}: Props) {
  return (
    <section className="sucursal-kpi-bar" aria-label="Indicadores operativos">
      <div className="sucursal-kpi-bar-head">
        <div>
          <h2 className="sucursal-kpi-bar-title">Panel de control</h2>
          <p className="sucursal-kpi-bar-scope">{scopeLabel}</p>
        </div>
        {selectedBranchId && onClearSelection ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClearSelection}>
            Ver consolidado
          </button>
        ) : null}
      </div>
      <div className="kpi-grid kpi-grid--map">
        {KPI_ITEMS.map((item) => (
          <article
            key={item.key}
            className="kpi-card kpi-card--map"
            style={{ borderLeft: `4px solid ${item.accent}` }}
          >
            <p>{item.label}</p>
            <h3>{item.format(metrics)}</h3>
          </article>
        ))}
      </div>
    </section>
  );
}
