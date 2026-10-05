import { useEffect, useState } from 'react';
import { listAuditLogs, type AuditLog } from '../api/coceClient';

export function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await listAuditLogs({ limit: 300 });
        if (!cancelled) setLogs(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="content-view">
      <header className="app-header">
        <div>
          <h1>Auditoría COCE</h1>
          <span className="tag">Acciones administrativas en servidor central</span>
        </div>
      </header>

      {error && <div className="alert alert-error">{error}</div>}
      {loading ? (
        <p>Cargando…</p>
      ) : logs.length === 0 ? (
        <div className="card">
          <p>No hay registros de auditoría.</p>
        </div>
      ) : (
        <div className="card audit-table-wrap">
          <table className="audit-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Usuario</th>
                <th>Acción</th>
                <th>Sucursal</th>
                <th>OK</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((row) => (
                <tr key={row.id} className={row.success ? '' : 'audit-fail'}>
                  <td>{new Date(row.createdAt).toLocaleString('es-ES')}</td>
                  <td>{row.actorUsername}</td>
                  <td>
                    <code>{row.action}</code>
                  </td>
                  <td>{row.branchNombre ?? row.branchId ?? '—'}</td>
                  <td>{row.success ? 'Sí' : 'No'}</td>
                  <td>
                    {row.detail ? (
                      <code style={{ fontSize: '0.75rem' }}>{JSON.stringify(row.detail)}</code>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
