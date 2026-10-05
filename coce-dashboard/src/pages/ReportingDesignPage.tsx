import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  downloadBranchPanelStatsCsv,
  fetchBranchPanelStats,
  listBranches,
  type BranchPanelStats,
} from '../api/coceClient';
import type { Sucursal } from '../types';

function fmt(n: number | undefined): string {
  return new Intl.NumberFormat('es-ES').format(n ?? 0);
}

export function ReportingDesignPage() {
  const [branches, setBranches] = useState<Sucursal[]>([]);
  const [branchId, setBranchId] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [stats, setStats] = useState<BranchPanelStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listBranches()
      .then((rows) => {
        setBranches(rows);
        setBranchId((prev) => prev || (rows[0]?.id ?? ''));
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const load = useCallback(async () => {
    if (!branchId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBranchPanelStats(branchId, {
        from: from || undefined,
        to: to || undefined,
      });
      setStats(data);
    } catch (e) {
      setStats(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [branchId, from, to]);

  useEffect(() => {
    void load();
  }, [load]);

  const indicadores = useMemo(() => {
    const k = stats?.kpis;
    return [
      ['Pulsaciones (canales IN)', fmt(k?.pulse_total)],
      ['Aperturas tablet', fmt(k?.door_openings)],
      ['Activaciones de modo', fmt(k?.mode_activations)],
      ['Modos bloqueados', fmt(k?.mode_blocked)],
      ['Ciclos de cierre', fmt(k?.door_closed_cycles)],
      ['Incidencias (WARN/ERR/Modbus)', fmt(k?.incidents)],
      ['Modos en cola', fmt(k?.queued_modes)],
    ] as Array<[string, string]>;
  }, [stats]);

  async function handleExport() {
    if (!branchId) return;
    setError(null);
    try {
      const blob = await downloadBranchPanelStatsCsv(branchId, {
        from: from || undefined,
        to: to || undefined,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `reporting-${branchId}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="content-view">
      <div className="card">
        <h2>Reporting avanzado</h2>
        <p className="muted">
          KPIs operativos por sucursal: pulsaciones de canales IN y eventos tipados del panel.
        </p>
        {error ? <div className="alert alert-error">{error}</div> : null}
        <div className="row-actions" style={{ flexWrap: 'wrap', gap: 8 }}>
          <select
            className="input"
            value={branchId}
            onChange={(e) => setBranchId(e.target.value)}
          >
            {!branches.length ? <option value="">Sin sucursales</option> : null}
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.nombre}
              </option>
            ))}
          </select>
          <input
            className="input"
            type="datetime-local"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            title="Desde"
          />
          <input
            className="input"
            type="datetime-local"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            title="Hasta"
          />
          <button className="btn btn-secondary" type="button" onClick={() => void load()} disabled={loading}>
            {loading ? 'Cargando…' : 'Actualizar'}
          </button>
          <button className="btn btn-primary" type="button" onClick={() => void handleExport()} disabled={!branchId}>
            Exportar CSV
          </button>
        </div>
        {stats?.current_mode ? (
          <p className="muted" style={{ marginTop: 12 }}>
            Modo actual: <strong>{stats.current_mode}</strong>
            {stats.pending_mode ? ` · En cola: ${stats.pending_mode}` : ''}
          </p>
        ) : null}
      </div>

      <div className="kpi-grid">
        {indicadores.map(([label, value]) => (
          <article className="kpi-card" key={label}>
            <p>{label}</p>
            <h3>{value}</h3>
          </article>
        ))}
      </div>

      <div className="card">
        <h3>Pulsaciones por canal IN</h3>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Canal</th>
                <th>Etiqueta</th>
                <th>Módulo</th>
                <th>Pulsaciones</th>
              </tr>
            </thead>
            <tbody>
              {(stats?.channels || []).map((ch) => (
                <tr key={`${ch.module_id}-${ch.channel_id}-${ch.io_code}`}>
                  <td>{ch.io_code || '—'}</td>
                  <td>{ch.label || '—'}</td>
                  <td>{ch.module_name || ch.module_id || '—'}</td>
                  <td>{fmt(ch.pulse_count)}</td>
                </tr>
              ))}
              {!stats?.channels?.length && !loading ? (
                <tr>
                  <td colSpan={4} className="text-muted">
                    Sin datos de canales.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
