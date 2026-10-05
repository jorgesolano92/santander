import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchSoftwareDeployments, listBranches } from '../api/coceClient';
import { useCoceLive } from '../context/CoceLiveContext';
import type { Sucursal } from '../types';
import {
  deriveAlertsFromBranchState,
  hasActiveBranchAlert,
} from '../utils/branchAlerts';

export function OverviewPage() {
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [pendingUpdates, setPendingUpdates] = useState<number | null>(null);
  const live = useCoceLive();

  useEffect(() => {
    listBranches().then(setSucursales).catch(() => setSucursales([]));
    fetchSoftwareDeployments({ limit: 200 })
      .then((rows) => {
        const pending = rows.filter((d) => {
          const s = String(d.status || '').toLowerCase();
          return s === 'pending' || s === 'sent' || s === 'downloading' || s === 'applying';
        }).length;
        setPendingUpdates(pending);
      })
      .catch(() => setPendingUpdates(null));
  }, []);

  const total = sucursales.length;
  const conPanel = sucursales.filter((s) => s.usuarioPanel?.trim()).length;

  const openAlerts = useMemo(() => {
    let n = 0;
    for (const s of sucursales) {
      const lb = live.getLiveBranch(s.id);
      const alerts = deriveAlertsFromBranchState(
        lb?.currentMode,
        lb?.activeToggleRules,
        lb?.alerts,
      );
      if (hasActiveBranchAlert(alerts)) n += 1;
    }
    return n;
  }, [sucursales, live]);

  return (
    <div className="content-view">
      <div className="kpi-grid">
        <article className="kpi-card">
          <p>Total sucursales registradas</p>
          <h3>{total}</h3>
        </article>
        <article className="kpi-card">
          <p>Sucursales con lectura de placas</p>
          <h3>{conPanel}</h3>
        </article>
        <article className="kpi-card">
          <p>Alertas abiertas</p>
          <h3>{openAlerts}</h3>
        </article>
        <article className="kpi-card">
          <p>Actualizaciones pendientes</p>
          <h3>{pendingUpdates ?? '—'}</h3>
        </article>
      </div>

      <div className="card">
        <h2>Estado del alcance</h2>
        <p>
          Este dashboard integra la operativa de sucursales/modos y los modulos de actualizaciones, mensajeria,
          reporting y alertas. Usa el menú lateral para navegar.
        </p>
        <p>
          <Link to="/alertas">Ver alertas</Link>
          {' · '}
          <Link to="/reporting">Reporting</Link>
          {' · '}
          <Link to="/actualizaciones">Actualizaciones</Link>
        </p>
      </div>
    </div>
  );
}
