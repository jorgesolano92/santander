import { FormEvent, useCallback, useEffect, useState } from 'react';
import {
  deleteAllSoftwareDeployments,
  deleteAllSoftwareReleases,
  deleteSoftwareDeployment,
  deleteSoftwareRelease,
  deploySoftwareRelease,
  fetchSoftwareDeployments,
  fetchSoftwareReleases,
  listBranches,
  publishPanelFromLocal,
  uploadSoftwareRelease,
  type SoftwareDeployment,
  type SoftwareRelease,
} from '../api/coceClient';
import type { Sucursal } from '../types';

export function UpdatesDesignPage() {
  const [releases, setReleases] = useState<SoftwareRelease[]>([]);
  const [deployments, setDeployments] = useState<SoftwareDeployment[]>([]);
  const [branches, setBranches] = useState<Sucursal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [apkFile, setApkFile] = useState<File | null>(null);
  const [apkVersion, setApkVersion] = useState('');
  const [apkNotes, setApkNotes] = useState('');
  const [notifyAll, setNotifyAll] = useState(true);
  const [selectedBranchIds, setSelectedBranchIds] = useState<string[]>([]);
  const [selectedReleaseId, setSelectedReleaseId] = useState<string>('');

  const [panelVersion, setPanelVersion] = useState('');
  const [panelNotes, setPanelNotes] = useState('');

  const refresh = useCallback(async () => {
    const [rels, deps, sucs] = await Promise.all([
      fetchSoftwareReleases({ limit: 50 }),
      fetchSoftwareDeployments({ limit: 80 }),
      listBranches().catch(() => [] as Sucursal[]),
    ]);
    setReleases(rels);
    setDeployments(deps);
    setBranches(sucs);
    if (!selectedReleaseId && rels[0]) setSelectedReleaseId(rels[0].id);
  }, [selectedReleaseId]);

  useEffect(() => {
    void refresh().catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [refresh]);

  async function onUploadApk(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    if (!apkFile || !apkVersion.trim()) {
      setError('Indica versión y selecciona el archivo APK');
      return;
    }
    setBusy(true);
    try {
      const release = await uploadSoftwareRelease({
        kind: 'tablet_apk',
        version: apkVersion.trim(),
        changelog: apkNotes,
        file: apkFile,
      });
      setSelectedReleaseId(release.id);
      setInfo(`APK ${release.version} subida. Ya puedes notificar a las sucursales.`);
      setApkFile(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onPublishPanel() {
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      const release = await publishPanelFromLocal({
        version: panelVersion.trim() || undefined,
        changelog: panelNotes,
      });
      setSelectedReleaseId(release.id);
      setInfo(`Paquete panel ${release.version} publicado desde código local.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDeploy() {
    setError(null);
    setInfo(null);
    if (!selectedReleaseId) {
      setError('Selecciona un release');
      return;
    }
    if (!notifyAll && selectedBranchIds.length === 0) {
      setError('Selecciona sucursales o marca “todas”');
      return;
    }
    setBusy(true);
    try {
      const result = await deploySoftwareRelease({
        releaseId: selectedReleaseId,
        branchIds: selectedBranchIds,
        sendToAll: notifyAll,
      });
      const ok = result.deployments.filter((d) => d.delivered).length;
      const offline = result.deployments.length - ok;
      setInfo(
        `Despliegue ${result.release.kind} ${result.release.version}: ${ok} online, ${offline} offline.`,
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function toggleBranch(id: string) {
    setSelectedBranchIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  async function onDeleteRelease(release: SoftwareRelease) {
    if (
      !confirm(
        `¿Eliminar el release [${release.kind}] ${release.version}? También se borrarán sus despliegues asociados.`,
      )
    ) {
      return;
    }
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      await deleteSoftwareRelease(release.id);
      if (selectedReleaseId === release.id) {
        setSelectedReleaseId('');
      }
      setInfo(`Release ${release.version} eliminado.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDeleteAllReleases() {
    if (!releases.length) return;
    if (
      !confirm(
        `¿Eliminar los ${releases.length} releases? Se borrarán también todos los despliegues asociados.`,
      )
    ) {
      return;
    }
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      const count = await deleteAllSoftwareReleases();
      setSelectedReleaseId('');
      setInfo(`${count} release(s) eliminado(s).`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDeleteDeployment(deployment: SoftwareDeployment) {
    if (
      !confirm(
        `¿Eliminar el despliegue de ${deployment.branchNombre || deployment.branchId} (${deployment.kind} ${deployment.version})?`,
      )
    ) {
      return;
    }
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      await deleteSoftwareDeployment(deployment.id);
      setInfo('Despliegue eliminado.');
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDeleteAllDeployments() {
    if (!deployments.length) return;
    if (!confirm(`¿Eliminar los ${deployments.length} registros de la cola de despliegues?`)) {
      return;
    }
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      const count = await deleteAllSoftwareDeployments();
      setInfo(`${count} despliegue(s) eliminado(s).`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="content-view">
      <div className="card">
        <h2>Actualizaciones remotas</h2>
        <p className="muted">
          Sube APK compiladas (fuera del repo) o publica el panel desde el checkout local del COCE.
          Las sucursales reciben aviso por WebSocket y descargan el artefacto desde aquí.
        </p>
        {error ? <p className="error-text">{error}</p> : null}
        {info ? <p className="muted">{info}</p> : null}
      </div>

      <div className="card">
        <h2>Subir APK (tablets Akuvox)</h2>
        <form onSubmit={onUploadApk} className="form-grid">
          <label>
            Versión
            <input
              value={apkVersion}
              onChange={(e) => setApkVersion(e.target.value)}
              placeholder="2.8.1"
              required
            />
          </label>
          <label>
            Archivo .apk
            <input
              type="file"
              accept=".apk,application/vnd.android.package-archive"
              onChange={(e) => setApkFile(e.target.files?.[0] || null)}
              required
            />
          </label>
          <label>
            Notas
            <input
              value={apkNotes}
              onChange={(e) => setApkNotes(e.target.value)}
              placeholder="Opcional"
            />
          </label>
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy ? 'Subiendo…' : 'Subir APK'}
          </button>
        </form>
      </div>

      <div className="card">
        <h2>Publicar panel (código local COCE)</h2>
        <p className="muted">
          Requiere <code>COCE_PANEL_SOURCE_DIR</code> en el API apuntando al checkout con{' '}
          <code>backend/</code> y <code>frontend/</code>.
        </p>
        <div className="form-grid">
          <label>
            Versión (opcional)
            <input
              value={panelVersion}
              onChange={(e) => setPanelVersion(e.target.value)}
              placeholder="auto fecha+sha"
            />
          </label>
          <label>
            Notas
            <input value={panelNotes} onChange={(e) => setPanelNotes(e.target.value)} />
          </label>
          <button className="btn btn-secondary" type="button" disabled={busy} onClick={() => void onPublishPanel()}>
            Publicar desde local
          </button>
        </div>
      </div>

      <div className="card">
        <h2>Notificar / desplegar</h2>
        <div className="form-grid">
          <label>
            Release
            <select
              value={selectedReleaseId}
              onChange={(e) => setSelectedReleaseId(e.target.value)}
            >
              <option value="">—</option>
              {releases.map((r) => (
                <option key={r.id} value={r.id}>
                  [{r.kind}] {r.version} · {new Date(r.createdAt).toLocaleString('es-ES')}
                </option>
              ))}
            </select>
          </label>
          <label className="row-actions">
            <input
              type="checkbox"
              checked={notifyAll}
              onChange={(e) => setNotifyAll(e.target.checked)}
            />
            Todas las sucursales
          </label>
          {!notifyAll ? (
            <div className="branch-checklist">
              {branches.map((b) => (
                <label key={b.id} className="row-actions">
                  <input
                    type="checkbox"
                    checked={selectedBranchIds.includes(b.id)}
                    onChange={() => toggleBranch(b.id)}
                  />
                  {b.nombre || b.id}
                </label>
              ))}
            </div>
          ) : null}
          <button className="btn btn-primary" type="button" disabled={busy} onClick={() => void onDeploy()}>
            Lanzar despliegue
          </button>
        </div>
      </div>

      <div className="card">
        <div className="row-actions" style={{ justifyContent: 'space-between', marginBottom: '0.75rem' }}>
          <h2 style={{ margin: 0 }}>Releases</h2>
          <button
            className="btn btn-danger btn-sm"
            type="button"
            disabled={busy || releases.length === 0}
            onClick={() => void onDeleteAllReleases()}
          >
            Eliminar todos
          </button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Versión</th>
                <th>Origen</th>
                <th>Fecha</th>
                <th>Archivo</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {releases.map((r) => (
                <tr key={r.id}>
                  <td>{r.kind}</td>
                  <td>{r.version}</td>
                  <td>{r.source}</td>
                  <td>{new Date(r.createdAt).toLocaleString('es-ES')}</td>
                  <td>{r.originalFilename}</td>
                  <td>
                    <button
                      className="btn btn-danger btn-sm"
                      type="button"
                      disabled={busy}
                      onClick={() => void onDeleteRelease(r)}
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="row-actions" style={{ justifyContent: 'space-between', marginBottom: '0.75rem' }}>
          <h2 style={{ margin: 0 }}>Cola de despliegues</h2>
          <button
            className="btn btn-danger btn-sm"
            type="button"
            disabled={busy || deployments.length === 0}
            onClick={() => void onDeleteAllDeployments()}
          >
            Eliminar todos
          </button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Sucursal</th>
                <th>Paquete</th>
                <th>Estado</th>
                <th>Actualizado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {deployments.map((j) => (
                <tr key={j.id}>
                  <td>{j.branchNombre || j.branchId}</td>
                  <td>
                    {j.kind} {j.version}
                  </td>
                  <td>{j.status}</td>
                  <td>{new Date(j.updatedAt).toLocaleString('es-ES')}</td>
                  <td>
                    <button
                      className="btn btn-danger btn-sm"
                      type="button"
                      disabled={busy}
                      onClick={() => void onDeleteDeployment(j)}
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
