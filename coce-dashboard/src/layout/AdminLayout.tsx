import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { clearCoceToken, coceMe, getCoceToken } from '../api/coceClient';
import { CoceLiveProvider } from '../context/CoceLiveContext';
import { CoceGlobalAlertsBar } from '../components/CoceGlobalAlertsBar';

const MENU = [
  { to: '/overview', label: 'Resumen ejecutivo' },
  { to: '/sucursales', label: 'Sucursales' },
  { to: '/auditoria', label: 'Auditoría' },
  { to: '/updates', label: 'Actualizaciones remotas' },
  { to: '/mensajeria', label: 'Mensajeria avanzada' },
  { to: '/reporting', label: 'Reporting avanzado' },
  { to: '/roles', label: 'Roles y permisos' },
  { to: '/alertas', label: 'Alertas y notificaciones' },
];

export function AdminLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const inControl = location.pathname.startsWith('/control/');
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    if (!getCoceToken()) {
      navigate('/login', { replace: true });
      return;
    }
    coceMe()
      .then((u) => setUsername(u.username))
      .catch(() => {
        clearCoceToken();
        navigate('/login', { replace: true });
      });
  }, [navigate, location.pathname]);

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
          {MENU.map((item) => (
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
            {username && <span className="badge badge-ok">{username}</span>}
            <button type="button" className="btn btn-ghost btn-sm" onClick={logout}>
              Salir
            </button>
          </div>
        </header>
        <CoceGlobalAlertsBar />
        <main className="coce-content">
          <Outlet />
        </main>
      </div>
    </div>
    </CoceLiveProvider>
  );
}
