import { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  clearCoceToken,
  coceMe,
  getCoceToken,
  type CoceRole,
  type CoceUser,
} from '../api/coceClient';
import { CoceLiveProvider } from '../context/CoceLiveContext';
import { CoceGlobalAlertsBar } from '../components/CoceGlobalAlertsBar';

type MenuItem = {
  to: string;
  label: string;
  adminOnly?: boolean;
};

const MENU: MenuItem[] = [
  { to: '/overview', label: 'Resumen ejecutivo' },
  { to: '/sucursales', label: 'Sucursales' },
  { to: '/auditoria', label: 'Auditoría' },
  { to: '/updates', label: 'Actualizaciones remotas', adminOnly: true },
  { to: '/mensajeria', label: 'Mensajeria avanzada' },
  { to: '/tecnicos', label: 'Técnicos habilitados' },
  { to: '/reporting', label: 'Reporting avanzado' },
  { to: '/roles', label: 'Roles y permisos', adminOnly: true },
  { to: '/alertas', label: 'Alertas y notificaciones' },
];

function roleLabel(role: CoceRole): string {
  return role === 'admin' ? 'Admin' : 'Operador';
}

export function AdminLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const inControl = location.pathname.startsWith('/control/');
  const [user, setUser] = useState<CoceUser | null>(null);

  useEffect(() => {
    if (!getCoceToken()) {
      navigate('/login', { replace: true });
      return;
    }
    coceMe()
      .then(setUser)
      .catch(() => {
        clearCoceToken();
        navigate('/login', { replace: true });
      });
  }, [navigate, location.pathname]);

  useEffect(() => {
    if (!user) return;
    if (user.role !== 'admin') {
      if (location.pathname.startsWith('/roles') || location.pathname.startsWith('/updates')) {
        navigate('/overview', { replace: true });
      }
    }
  }, [user, location.pathname, navigate]);

  const visibleMenu = useMemo(
    () => MENU.filter((item) => !item.adminOnly || user?.role === 'admin'),
    [user],
  );

  function logout() {
    clearCoceToken();
    navigate('/login', { replace: true });
  }

  return (
    <CoceLiveProvider>
    <div className="coce-layout">
      <aside className="coce-sidebar">
        <div className="coce-brand">
          <div className="coce-brand-dot">C</div>
          <div>
            <strong>COCE Santander</strong>
            <small>Dashboard operativo</small>
          </div>
        </div>
        <nav className="coce-nav">
          {visibleMenu.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? 'coce-nav-link active' : 'coce-nav-link')}
            >
              {item.label}
            </NavLink>
          ))}
          {inControl && (
            <NavLink to={location.pathname} className="coce-nav-link active">
              Modo y control
            </NavLink>
          )}
        </nav>
      </aside>

      <div className="coce-main">
        <header className="coce-topbar">
          <div>
            <h1>Centro de Operaciones y Control Externo</h1>
            <p>Datos en servidor COCE central · credenciales de oficina no expuestas al navegador</p>
          </div>
          <div className="topbar-badges">
            {user ? (
              <span className="badge badge-ok">
                {user.username} · {roleLabel(user.role)}
              </span>
            ) : null}
            <button type="button" className="btn btn-ghost btn-sm" onClick={logout}>
              Salir
            </button>
          </div>
        </header>
        <CoceGlobalAlertsBar />
        <main className="coce-content">
          <Outlet context={{ user }} />
        </main>
      </div>
    </div>
    </CoceLiveProvider>
  );
}
