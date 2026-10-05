import { useCallback, useEffect, useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  deleteCoceMessage,
  fetchCoceMessages,
  listBranches,
  sendCoceMessage,
  type CoceOutboundMessage,
  type CoceUser,
} from '../api/coceClient';
import type { Sucursal } from '../types';

function formatWhen(iso: string): string {
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

function statusLabel(m: CoceOutboundMessage): string {
  if (m.readAt) return 'Leído';
  if (m.deliveryStatus === 'delivered') return 'Entregado';
  if (m.deliveryStatus === 'offline') return 'Sucursal desconectada';
  return 'Enviado';
}

function statusBadgeClass(m: CoceOutboundMessage): string {
  if (m.readAt) return 'badge badge-ok';
  if (m.deliveryStatus === 'delivered') return 'badge badge-ok';
  if (m.deliveryStatus === 'offline') return 'badge badge-warn';
  return 'badge badge-off';
}

export function MessagingDesignPage() {
  const { user: me } = useOutletContext<{ user: CoceUser | null }>();
  const canDelete = me?.role === 'admin';
  const [branches, setBranches] = useState<Sucursal[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sendToAll, setSendToAll] = useState(false);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [urgent, setUrgent] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<CoceOutboundMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [filterBranch, setFilterBranch] = useState('');
  const [filterUrgent, setFilterUrgent] = useState<'all' | 'yes' | 'no'>('all');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterQ, setFilterQ] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    void listBranches()
      .then(setBranches)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const refreshHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const rows = await fetchCoceMessages({
        limit: 200,
        branchId: filterBranch || undefined,
        urgent:
          filterUrgent === 'all' ? undefined : filterUrgent === 'yes',
        deliveryStatus: filterStatus
          ? (filterStatus as CoceOutboundMessage['deliveryStatus'])
          : undefined,
        q: filterQ.trim() || undefined,
      });
      setMessages(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingHistory(false);
    }
  }, [filterBranch, filterUrgent, filterStatus, filterQ]);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  const allSelected = useMemo(
    () => branches.length > 0 && selected.size === branches.length,
    [branches.length, selected.size],
  );

  function toggleBranch(id: string) {
    setSendToAll(false);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllBranches() {
    if (allSelected) {
      setSelected(new Set());
      setSendToAll(false);
      return;
    }
    setSelected(new Set(branches.map((b) => b.id)));
    setSendToAll(false);
  }

  async function handleSend() {
    setError(null);
    if (!title.trim() || !body.trim()) {
      setError('Título y mensaje son obligatorios');
      return;
    }
    if (!sendToAll && selected.size === 0) {
      setError('Selecciona al menos una sucursal o marca enviar a todas');
      return;
    }
    setSending(true);
    try {
      await sendCoceMessage({
        title: title.trim(),
        body: body.trim(),
        urgent,
        branchIds: Array.from(selected),
        sendToAll,
      });
      setTitle('');
      setBody('');
      setUrgent(false);
      await refreshHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  async function handleDelete(m: CoceOutboundMessage) {
    const ok = window.confirm(
      `¿Borrar el mensaje «${m.title}» enviado a ${m.branchNombre}?`,
    );
    if (!ok) return;
    setDeletingId(m.id);
    setError(null);
    try {
      await deleteCoceMessage(m.id);
      await refreshHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="content-view messaging-page">
      <div className="card">
        <h2>Mensajería avanzada</h2>
        <p className="muted">
          Envía avisos del COCE a las sucursales. Llegan en tiempo real a la tablet como
          notificación emergente y quedan en el historial. El estado pasa a «Leído» cuando
          se abre en panel o tablet.
        </p>
        {error ? <div className="alert alert-error">{error}</div> : null}
        <div className="messaging-compose-grid">
          <section className="messaging-compose-form">
            <label className="field-label" htmlFor="msg-title">
              Título
            </label>
            <input
              id="msg-title"
              className="input"
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Asunto del mensaje"
            />
            <label className="field-label" htmlFor="msg-body">
              Mensaje
            </label>
            <textarea
              id="msg-body"
              className="input messaging-textarea"
              value={body}
              maxLength={4000}
              rows={8}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Texto que verá la sucursal en la tablet"
            />
            <label className="messaging-urgent-check">
              <input
                type="checkbox"
                checked={urgent}
                onChange={(e) => setUrgent(e.target.checked)}
              />
              Marcar como urgente (borde rojo e icono en la tablet)
            </label>
            <div className="row-actions">
              <button
                type="button"
                className="btn btn-primary"
                disabled={sending}
                onClick={() => void handleSend()}
              >
                {sending ? 'Enviando…' : 'Enviar mensaje'}
              </button>
            </div>
          </section>

          <aside className="messaging-branch-picker">
            <div className="messaging-branch-picker-head">
              <h3>Destinatarios</h3>
              <label className="messaging-urgent-check">
                <input
                  type="checkbox"
                  checked={sendToAll}
                  onChange={(e) => {
                    setSendToAll(e.target.checked);
                    if (e.target.checked) setSelected(new Set());
                  }}
                />
                Enviar a todas
              </label>
            </div>
            {!sendToAll ? (
              <>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={toggleAllBranches}
                >
                  {allSelected ? 'Quitar selección' : 'Seleccionar todas'}
                </button>
                <div className="messaging-branch-list">
                  {branches.map((branch) => (
                    <label key={branch.id} className="messaging-branch-item">
                      <input
                        type="checkbox"
                        checked={selected.has(branch.id)}
                        onChange={() => toggleBranch(branch.id)}
                      />
                      <span>
                        <strong>{branch.nombre}</strong>
                        <small>{branch.host}</small>
                      </span>
                    </label>
                  ))}
                  {!branches.length ? (
                    <p className="muted">No hay sucursales registradas.</p>
                  ) : null}
                </div>
              </>
            ) : (
              <p className="muted">
                El mensaje se enviará a todas las sucursales registradas en el COCE.
              </p>
            )}
          </aside>
        </div>
      </div>

      <div className="card">
        <div className="messaging-history-head">
          <h2>Historial de envíos</h2>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={loadingHistory}
            onClick={() => void refreshHistory()}
          >
            {loadingHistory ? 'Actualizando…' : 'Actualizar'}
          </button>
        </div>
        <div className="messaging-filters">
          <input
            className="input"
            placeholder="Buscar título, texto o sucursal…"
            value={filterQ}
            onChange={(e) => setFilterQ(e.target.value)}
          />
          <select
            className="input"
            value={filterBranch}
            onChange={(e) => setFilterBranch(e.target.value)}
          >
            <option value="">Todas las sucursales</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.nombre}
              </option>
            ))}
          </select>
          <select
            className="input"
            value={filterUrgent}
            onChange={(e) => setFilterUrgent(e.target.value as 'all' | 'yes' | 'no')}
          >
            <option value="all">Urgente: todos</option>
            <option value="yes">Solo urgentes</option>
            <option value="no">Solo normales</option>
          </select>
          <select
            className="input"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="">Estado: todos</option>
            <option value="delivered">Entregado</option>
            <option value="read">Leído</option>
            <option value="offline">Desconectada</option>
            <option value="pending">Enviado</option>
          </select>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Sucursal</th>
                <th>Título</th>
                <th>Urgente</th>
                <th>Estado</th>
                <th>Operador</th>
                {canDelete ? <th></th> : null}
              </tr>
            </thead>
            <tbody>
              {messages.map((m) => (
                <tr key={m.id} className={m.urgent ? 'row-highlight' : ''}>
                  <td>{formatWhen(m.createdAt)}</td>
                  <td>{m.branchNombre}</td>
                  <td>
                    <strong>{m.title}</strong>
                    <br />
                    <small className="text-muted">{m.body}</small>
                  </td>
                  <td>{m.urgent ? <span className="badge badge-danger">Sí</span> : 'No'}</td>
                  <td>
                    <span className={statusBadgeClass(m)}>{statusLabel(m)}</span>
                    {m.readAt ? (
                      <>
                        <br />
                        <small className="text-muted">
                          {formatWhen(m.readAt)}
                          {m.readBy ? ` · ${m.readBy}` : ''}
                        </small>
                      </>
                    ) : null}
                  </td>
                  <td>{m.actorUsername}</td>
                  {canDelete ? (
                    <td>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={deletingId === m.id}
                        onClick={() => void handleDelete(m)}
                      >
                        {deletingId === m.id ? '…' : 'Borrar'}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
              {!messages.length && !loadingHistory ? (
                <tr>
                  <td colSpan={canDelete ? 7 : 6} className="text-muted">
                    No hay mensajes enviados con estos filtros.
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
