import { useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import {
  coceLogin,
  coceRegister,
  fetchCoceSetupStatus,
  getCoceToken,
  type CoceSetupStatus,
} from '../api/coceClient';

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [setupToken, setSetupToken] = useState('');
  const [setup, setSetup] = useState<CoceSetupStatus | null>(null);
  const [showRegister, setShowRegister] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchCoceSetupStatus()
      .then((s) => {
        setSetup(s);
        if (!s.hasUsers) setShowRegister(true);
      })
      .catch(() => setSetup({ hasUsers: true, allowRegister: false, requiresSetupToken: false }));
  }, []);

  if (getCoceToken()) {
    return <Navigate to="/overview" replace />;
  }

  const canRegister = setup?.allowRegister ?? false;
  const needsSetupToken = setup?.requiresSetupToken ?? false;
  const firstUser = setup && !setup.hasUsers;

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await coceLogin(username, password);
      navigate('/overview', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await coceRegister(username, password, setupToken || undefined);
      await coceLogin(username, password);
      navigate('/overview', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!setup) {
    return (
      <div className="login-page">
        <p>Cargando…</p>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="card login-card">
        <h1>COCE — Acceso</h1>
        <p style={{ color: 'var(--muted)', marginTop: 0 }}>
          Servidor central <code>coce-api</code>. Las sucursales y credenciales de oficina se guardan en el servidor,
          no en este navegador.
        </p>
        {firstUser && (
          <div className="alert alert-info">
            No hay administradores COCE. Crea el <strong>primer usuario</strong> (mínimo 8 caracteres en la
            contraseña).
          </div>
        )}
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={showRegister ? onRegister : onLogin}>
          <label className="field">
            <span>Usuario administrador COCE</span>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
            />
          </label>
          <label className="field">
            <span>Contraseña</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete={showRegister ? 'new-password' : 'current-password'}
            />
          </label>
          {showRegister && needsSetupToken && (
            <label className="field">
              <span>Token de alta COCE (obligatorio)</span>
              <input
                type="password"
                value={setupToken}
                onChange={(e) => setSetupToken(e.target.value)}
                required
                autoComplete="off"
              />
              <small style={{ color: 'var(--muted)' }}>
                Valor configurado en el servidor como <code>COCE_SETUP_TOKEN</code> (solo para dar de alta más
                administradores cuando ya existe al menos uno).
              </small>
            </label>
          )}
          <div className="row-actions">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? 'Espere…' : showRegister ? 'Registrar y entrar' : 'Entrar'}
            </button>
            {canRegister && !firstUser && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowRegister((v) => !v)}
              >
                {showRegister ? 'Ya tengo cuenta' : 'Alta de administrador'}
              </button>
            )}
            {canRegister && firstUser && showRegister && (
              <button type="button" className="btn btn-secondary" onClick={() => setShowRegister(false)}>
                Ya tengo cuenta
              </button>
            )}
          </div>
        </form>
        {setup.hasUsers && !canRegister && (
          <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginBottom: 0 }}>
            El alta de nuevos usuarios está deshabilitada. Contacta con quien administra el servidor COCE o define{' '}
            <code>COCE_SETUP_TOKEN</code> en <code>coce-api/.env</code> para permitir altas con token.
          </p>
        )}
      </div>
    </div>
  );
}
