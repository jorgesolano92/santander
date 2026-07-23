import { useCallback, useEffect, useState } from 'react';
import {
  fetchTechnicians,
  importTechniciansCsv,
  syncTechniciansToBranches,
  type CoceTechnician,
} from '../api/coceClient';

export function TechniciansPage() {
  const [items, setItems] = useState<CoceTechnician[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [syncInfo, setSyncInfo] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await fetchTechnicians());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setSyncInfo(null);
    try {
      const result = await importTechniciansCsv(file);
      setItems(result.technicians);
      setSyncInfo(
        `Importados ${result.technicians.length}. Sync sucursales: ${result.sync.delivered} conectadas, ${result.sync.offline} offline.`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onSync() {
    setBusy(true);
    setError(null);
    try {
      const sync = await syncTechniciansToBranches();
      setSyncInfo(
        `Reenviado a sucursales: ${sync.delivered} conectadas, ${sync.offline} offline.`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const filtered = items.filter((t) => {
    const hay = `${t.dni} ${t.nombre} ${t.apellidos} ${t.empresa}`.toLowerCase();
    return hay.includes(q.trim().toLowerCase());
  });

  return (
    <div className="content-view">
      <div className="card">
        <h2>Técnicos habilitados</h2>
        <p className="muted">
          Sube un CSV con columnas <code>dni,nombre,apellidos,empresa,valido_hasta</code>.
          El listado se envía por WebSocket a las sucursales conectadas; la tablet consulta al PC
          industrial.
        </p>
        {error ? <div className="alert alert-error">{error}</div> : null}
        {syncInfo ? <div className="alert alert-ok">{syncInfo}</div> : null}
        <div className="row-actions" style={{ gap: 10, flexWrap: 'wrap' }}>
          <label className="btn btn-primary" style={{ cursor: busy ? 'wait' : 'pointer' }}>
            {busy ? 'Procesando…' : 'Importar CSV'}
            <input
              type="file"
              accept=".csv,text/csv"
              hidden
              disabled={busy}
              onChange={(e) => void onFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void onSync()}>
            Reenviar a sucursales
          </button>
          <button type="button" className="btn btn-ghost" disabled={loading} onClick={() => void refresh()}>
            Actualizar
          </button>
          <input
            className="input"
            style={{ maxWidth: 280 }}
            placeholder="Filtrar…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>

      <div className="card">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>DNI</th>
                <th>Nombre</th>
                <th>Apellidos</th>
                <th>Empresa</th>
                <th>Válido hasta</th>
                <th>Activo</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => (
                <tr key={t.dni}>
                  <td>{t.dni}</td>
                  <td>{t.nombre}</td>
                  <td>{t.apellidos}</td>
                  <td>{t.empresa}</td>
                  <td>{t.valido_hasta || '—'}</td>
                  <td>{t.active ? 'Sí' : 'No'}</td>
                </tr>
              ))}
              {!filtered.length && !loading ? (
                <tr>
                  <td colSpan={6} className="text-muted">
                    No hay técnicos cargados.
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
