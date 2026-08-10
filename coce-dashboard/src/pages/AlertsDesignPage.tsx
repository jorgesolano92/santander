import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchCoceAlerts, listBranches, type CoceAlert } from '../api/coceClient';
import { useCoceLive } from '../context/CoceLiveContext';
import type { Sucursal } from '../types';
import {
  alertTitle,
  deriveAlertsFromBranchState,
  listActiveAlerts,
  type BranchAlert,
} from '../utils/branchAlerts';

function formatWhen(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function alertTypeLabel(t: string): string {
  if (t === 'fire') return 'Incendio';
  if (t === 'emergency') return 'Emergencia';
  if (t.startsWith('door_held')) return 'Puerta abierta';
  return t;
}

type LiveRow = {
  key: string;
  branchId: string;
  branchName: string;
  alert: BranchAlert;
};

export function AlertsDesignPage() {
  const [branches, setBranches] = useState<Sucursal[]>([]);
  const [history, setHistory] = useState<CoceAlert[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const live = useCoceLive();

  useEffect(() => {
    void listBranches()
      .then(setBranches)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    void fetchCoceAlerts({ limit: 100 })
      .then(setHistory)
      .catch(() => setHistory([]));
  }, []);

  const openRows = useMemo(() => {
    const rows: LiveRow[] = [];
    for (const b of branches) {
      const lb = live.getLiveBranch(b.id);
      const alerts = deriveAlertsFromBranchState(
        lb?.currentMode,
        lb?.activeToggleRules,
        lb?.alerts,
      );
      for (const alert of listActiveAlerts(alerts)) {
        rows.push({
          key: `${b.id}-${alert.alert_type}`,
          branchId: b.id,
          branchName: b.nombre,
          alert,
        });
      }
    }
    return rows;
  }, [branches, live]);

  return (
    <div className="content-view">
      <div className="card">
        <h2>Alertas inteligentes y notificaciones</h2>
        <p className="muted">
          Alertas en vivo de incendio, emergencia y puertas abiertas prolongadas, con historial
          reciente.
        </p>
        {error ? <div className="alert alert-error">{error}</div> : null}
        <div className="row-actions">
          <button
            className="btn btn-secondary"
            type="button"
            onClick={() => setShowHistory((v) => !v)}
          >
            {showHistory ? 'Ocultar historial' : 'Ver historial'}
          </button>
        </div>
      </div>

      <div className="card">
        <h2>Alertas abiertas</h2>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Sucursal</th>
                <th>Detalle</th>
                <th>Estado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {openRows.map((row) => (
                <tr key={row.key}>
                  <td>{alertTitle(row.alert)}</td>
                  <td>{row.branchName}</td>
                  <td>{row.alert.message || '—'}</td>
                  <td>
                    <span className="badge badge-danger">Activa</span>
                  </td>
                  <td>
                    <Link className="btn btn-sm btn-primary" to={`/control/${row.branchId}`}>
                      Ir a sucursal
                    </Link>
                  </td>
                </tr>
              ))}
              {!openRows.length ? (
                <tr>
                  <td colSpan={5} className="text-muted">
                    No hay alertas activas en este momento.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {showHistory ? (
        <div className="card">
          <h2>Historial reciente</h2>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Tipo</th>
                  <th>Sucursal</th>
                  <th>Estado</th>
                  <th>Mensaje</th>
                </tr>
              </thead>
              <tbody>
                {history.map((a) => (
                  <tr key={a.id}>
                    <td>{formatWhen(a.createdAt)}</td>
                    <td>{alertTypeLabel(a.alertType)}</td>
                    <td>{a.branchNombre || a.branchId}</td>
                    <td>
                      {a.active ? (
                        <span className="badge badge-danger">Activa</span>
                      ) : (
                        <span className="badge badge-ok">
                          Resuelta {a.resolvedAt ? `(${formatWhen(a.resolvedAt)})` : ''}
                        </span>
                      )}
                    </td>
                    <td>{a.message || '—'}</td>
                  </tr>
                ))}
                {!history.length ? (
                  <tr>
                    <td colSpan={5} className="text-muted">
                      Sin historial de alertas todavía.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
