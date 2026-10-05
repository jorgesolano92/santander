import { useCallback, useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  createCoceUser,
  deleteCoceUser,
  listCoceUsers,
  updateCoceUser,
  type CoceRole,
  type CoceUser,
} from '../api/coceClient';

type OutletCtx = { user: CoceUser | null };

export function RolesDesignPage() {
  const { user: me } = useOutletContext<OutletCtx>();
  const [users, setUsers] = useState<CoceUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<CoceRole>('operador');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setUsers(await listCoceUsers());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleCreate() {
    setError(null);
    if (!username.trim() || password.length < 8) {
      setError('Usuario y contraseña (mín. 8) son obligatorios');
      return;
    }
    setBusy(true);
    try {
      await createCoceUser({
        username: username.trim(),
        password,
        role,
      });
      setUsername('');
      setPassword('');
      setRole('operador');
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleRoleChange(u: CoceUser, next: CoceRole) {
    setError(null);
    try {
      await updateCoceUser(u.id, { role: next });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleDelete(u: CoceUser) {
    if (!window.confirm(`¿Eliminar usuario «${u.username}»?`)) return;
    setError(null);
    try {
      await deleteCoceUser(u.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (me && me.role !== 'admin') {
    return (
      <div className="content-view">
        <div className="card">
          <h2>Roles y permisos</h2>
          <p className="muted">Solo administradores pueden gestionar usuarios.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="content-view">
      <div className="card">
        <h2>Gestión de roles y usuarios</h2>
        <p className="muted">
          Roles disponibles: <strong>Admin</strong> (todo) y <strong>Operador</strong> (mensajería,
          reporting, alertas y control remoto; sin usuarios ni publicar updates).
        </p>
        {error ? <div className="alert alert-error">{error}</div> : null}
      </div>

      <div className="card">
        <h3>Nuevo usuario</h3>
        <div className="row-actions" style={{ flexWrap: 'wrap', gap: 8 }}>
          <input
            className="input"
            placeholder="Usuario"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            className="input"
            type="password"
            placeholder="Contraseña"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <select
            className="input"
            value={role}
            onChange={(e) => setRole(e.target.value as CoceRole)}
          >
            <option value="operador">Operador</option>
            <option value="admin">Admin</option>
          </select>
          <button className="btn btn-primary" type="button" disabled={busy} onClick={() => void handleCreate()}>
            Crear
          </button>
        </div>
      </div>

      <div className="card">
        <h3>Usuarios</h3>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Usuario</th>
                <th>Rol</th>
                <th>Creado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.username}</td>
                  <td>
                    <select
                      className="input"
                      value={u.role}
                      onChange={(e) => void handleRoleChange(u, e.target.value as CoceRole)}
                    >
                      <option value="operador">Operador</option>
                      <option value="admin">Admin</option>
                    </select>
                  </td>
                  <td>{u.createdAt ? new Date(u.createdAt).toLocaleString('es-ES') : '—'}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={me?.id === u.id}
                      onClick={() => void handleDelete(u)}
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))}
              {!users.length ? (
                <tr>
                  <td colSpan={4} className="text-muted">
                    No hay usuarios.
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
