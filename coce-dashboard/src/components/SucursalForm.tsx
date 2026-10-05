import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { branchToSucursal, createBranch, getBranch, updateBranch } from '../api/coceClient';
import type { Sucursal, SucursalEstado } from '../types';

function emptyForm(): {
  nombre: string;
  host: string;
  port: number;
  useHttps: boolean;
  usuarioTablet: string;
  passwordTablet: string;
  usuarioPanel: string;
  passwordPanel: string;
  estado: SucursalEstado;
} {
  return {
    nombre: '',
    host: '',
    port: 8000,
    useHttps: false,
    usuarioTablet: '',
    passwordTablet: '',
    usuarioPanel: '',
    passwordPanel: '',
    estado: 'operativo',
  };
}

export function SucursalForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEdit = Boolean(id);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [createdEnv, setCreatedEnv] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const b = await getBranch(id);
        if (cancelled) return;
        const s = branchToSucursal(b);
        setForm({
          nombre: s.nombre,
          host: s.host,
          port: s.port,
          useHttps: s.useHttps,
          usuarioTablet: s.usuarioTablet,
          passwordTablet: '',
          usuarioPanel: s.usuarioPanel ?? '',
          passwordPanel: '',
          estado: s.estado ?? 'operativo',
        });
      } catch {
        if (!cancelled) navigate('/sucursales', { replace: true });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, navigate]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.host.trim()) {
      alert('Indica la IP o hostname del sistema local.');
      return;
    }
    if (!isEdit && !form.passwordTablet) {
      alert('La contraseña tablet es obligatoria al crear la sucursal.');
      return;
    }
    setBusy(true);
    setError(null);
    const payload = {
      nombre: form.nombre.trim() || 'Sin nombre',
      host: form.host.trim(),
      port: Number(form.port) || 8000,
      useHttps: form.useHttps,
      usuarioTablet: form.usuarioTablet,
      passwordTablet: form.passwordTablet || undefined,
      usuarioPanel: form.usuarioPanel?.trim() || undefined,
      passwordPanel: form.passwordPanel || undefined,
      estado: form.estado,
    };
    try {
      if (isEdit && id) {
        await updateBranch(id, payload);
        navigate('/sucursales');
      } else {
        const created = await createBranch({
          ...payload,
          passwordTablet: form.passwordTablet,
        });
        const wsHint =
          (import.meta.env.VITE_COCE_WS_BRANCH_URL as string | undefined)?.trim() ||
          'ws://localhost:9000/api/coce/ws/branch/' + created.id;
        setCreatedEnv(
          [
            '# Copiar en backend/.env de la sucursal',
            `COCE_WS_ENABLED=true`,
            `COCE_WS_URL=${wsHint}`,
            `COCE_INSTALLATION_ID=${created.id}`,
            `COCE_INGEST_TOKEN=${created.ingestToken ?? ''}`,
          ].join('\n'),
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="content-view">
      <header className="app-header">
        <div>
          <h1>{isEdit ? 'Editar sucursal' : 'Nueva sucursal'}</h1>
          <span className="tag">Guardado en coce-api (SQLite central)</span>
        </div>
        <Link to="/sucursales" className="btn btn-ghost">
          Volver
        </Link>
      </header>

      {error && <div className="alert alert-error">{error}</div>}

      {createdEnv && (
        <div className="card">
          <h2>Configuración canal COCE (sucursal)</h2>
          <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>
            Copia estas variables en <code>backend/.env</code> del PC de la oficina. El token solo se muestra una vez.
          </p>
          <pre
            style={{
              background: 'var(--surface-2, #f4f4f5)',
              padding: '1rem',
              overflow: 'auto',
              fontSize: '0.85rem',
            }}
          >
            {createdEnv}
          </pre>
          <div className="row-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                void navigator.clipboard.writeText(createdEnv);
              }}
            >
              Copiar al portapapeles
            </button>
            <Link to="/sucursales" className="btn btn-secondary">
              Ir al listado
            </Link>
          </div>
        </div>
      )}

      {!createdEnv && (
      <form className="card" onSubmit={submit}>
        <h2>Datos de conexión</h2>
        <label className="field">
          <span>Nombre de la sucursal</span>
          <input
            type="text"
            value={form.nombre}
            onChange={(e) => setForm((f) => ({ ...f, nombre: e.target.value }))}
            placeholder="Ej. Oficina Centro"
            autoComplete="off"
          />
        </label>
        <label className="field">
          <span>IP o hostname (sin http ni :puerto)</span>
          <input
            type="text"
            value={form.host}
            onChange={(e) => setForm((f) => ({ ...f, host: e.target.value }))}
            placeholder="192.168.1.155"
            pattern="^(\d{1,3}\.){3}\d{1,3}$|^localhost$|^[a-zA-Z0-9][a-zA-Z0-9.-]*$"
            title="IPv4 válida, p. ej. 192.168.1.155 (cuatro números, no 192.168.1.1.155)"
            required
            autoComplete="off"
          />
          <small style={{ color: 'var(--muted)' }}>
            El servidor COCE (coce-api) debe poder hacer ping a esta IP. Si backend y COCE están en el mismo PC,
            usa <code>127.0.0.1</code> o <code>localhost</code>.
          </small>
        </label>
        <label className="field">
          <span>Puerto API</span>
          <input
            type="number"
            min={1}
            max={65535}
            value={form.port}
            onChange={(e) => setForm((f) => ({ ...f, port: Number(e.target.value) }))}
          />
        </label>
        <div className="checkbox-row">
          <input
            id="https"
            type="checkbox"
            checked={form.useHttps}
            onChange={(e) => setForm((f) => ({ ...f, useHttps: e.target.checked }))}
          />
          <label htmlFor="https">Usar HTTPS (TLS)</label>
        </div>

        <label className="field">
          <span>Estado operativo (COCE)</span>
          <select
            value={form.estado}
            onChange={(e) => setForm((f) => ({ ...f, estado: e.target.value as SucursalEstado }))}
          >
            <option value="operativo">Operativo</option>
            <option value="no_operativo">No operativo</option>
            <option value="apagado">Apagado</option>
          </select>
        </label>

        <h2>Credenciales API tableta (obligatorio)</h2>
        <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginTop: 0 }}>
          Usuario del PC industrial para <code>/api/v1/*</code>. Solo el servidor COCE las usará al consultar la
          oficina.
        </p>
        <label className="field">
          <span>Usuario</span>
          <input
            type="text"
            value={form.usuarioTablet}
            onChange={(e) => setForm((f) => ({ ...f, usuarioTablet: e.target.value }))}
            required
            autoComplete="off"
          />
        </label>
        <label className="field">
          <span>Contraseña {isEdit && '(vacío = no cambiar)'}</span>
          <input
            type="password"
            value={form.passwordTablet}
            onChange={(e) => setForm((f) => ({ ...f, passwordTablet: e.target.value }))}
            autoComplete="new-password"
          />
        </label>

        <h2>Credenciales panel web (opcional)</h2>
        <label className="field">
          <span>Usuario panel</span>
          <input
            type="text"
            value={form.usuarioPanel}
            onChange={(e) => setForm((f) => ({ ...f, usuarioPanel: e.target.value }))}
            autoComplete="off"
          />
        </label>
        <label className="field">
          <span>Contraseña panel {isEdit && '(vacío = no cambiar)'}</span>
          <input
            type="password"
            value={form.passwordPanel}
            onChange={(e) => setForm((f) => ({ ...f, passwordPanel: e.target.value }))}
            autoComplete="new-password"
          />
        </label>

        <div className="row-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Guardando…' : 'Guardar'}
          </button>
          <Link to="/sucursales" className="btn btn-secondary">
            Cancelar
          </Link>
        </div>
      </form>
      )}
    </div>
  );
}
