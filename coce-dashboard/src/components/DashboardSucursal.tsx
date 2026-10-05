import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { PanelBoardState, PanelModeRule, Sucursal } from "../types";
import {
  branchToSucursal,
  fetchBranchPanelStatus,
  fetchBranchSnapshot,
  getBranch,
  setBranchMode,
} from "../api/coceClient";
import { resolveSucursalEstado, useCoceLive } from "../context/CoceLiveContext";
import { applyLivePatch } from "../utils/applyLivePatch";
import { BranchCriticalAlertBanner } from "./BranchCriticalAlertBanner";
import { isPanelModeActiveNow, deriveAlertsFromBranchState } from "../utils/branchAlerts";
import {
  DOOR_BOARD_CONFIG,
  DOOR_STATE_HINTS,
  DOOR_STATE_LABELS,
  deriveDoorState,
  type DoorState,
} from "../utils/deriveDoorState";
import { getSucursalEstado, SUCURSAL_ESTADO_LABELS } from "../sucursalEstado";
import type { PanelModuleConfig } from "../types";
import { BoardIoPanel } from "./BoardIoPanel";

type LoadState = {
  modes: PanelModeRule[];
  currentMode: string | null;
  activeToggleRules: string[];
  branchAlerts: import("../utils/branchAlerts").BranchAlertsMap;
  boards: Array<{ id: string; data: PanelBoardState }>;
  modulesConfig: PanelModuleConfig[];
  panelTimestamp: string | null;
  panelOk: boolean;
  panelError: string | null;
};

function moduleForBoard(
  modules: PanelModuleConfig[],
  boardId: string,
): PanelModuleConfig | undefined {
  const n = Number(boardId);
  return modules.find((m) => m.id === n || String(m.id) === boardId);
}

export function DashboardSucursal() {
  const { id } = useParams<{ id: string }>();
  const live = useCoceLive();
  const liveBranch = id ? live.getLiveBranch(id) : undefined;
  const navigate = useNavigate();
  const [sucursal, setSucursal] = useState<Sucursal | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<LoadState | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  // Función para transformar "horario_esclusa" -> "Horario esclusa"
  function formatModeName(
    key: string | null | undefined,
    fallback = "— ninguna regla activa —",
  ): string {
    if (!key) return fallback;
    const withSpaces = key.replace(/_/g, " ");
    return withSpaces.charAt(0).toUpperCase() + withSpaces.slice(1);
  }

  function PcIcon() {
    return (
      <svg
        viewBox="0 0 60 56"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
      >
        <rect
          x="4"
          y="8"
          width="52"
          height="38"
          rx="4"
          stroke="currentColor"
          strokeWidth="2.5"
        />
        <rect
          x="10"
          y="14"
          width="40"
          height="24"
          rx="2"
          fill="currentColor"
          opacity="0.12"
        />
        <rect
          x="22"
          y="46"
          width="16"
          height="3"
          rx="1"
          fill="currentColor"
          opacity="0.35"
        />
        <rect
          x="16"
          y="50"
          width="28"
          height="2"
          rx="1"
          fill="currentColor"
          opacity="0.2"
        />
      </svg>
    );
  }

  function RestartIcon() {
    return (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
      >
        <path
          d="M4 12a8 8 0 0 1 13.3-5.9M20 12a8 8 0 0 1-13.3 5.9"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M16 6h4V2M8 18H4v4"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }

  function DoorIcon() {
    return (
      <svg
        viewBox="0 0 56 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
      >
        <rect
          x="4"
          y="6"
          width="20"
          height="36"
          rx="2"
          stroke="currentColor"
          strokeWidth="2"
        />
        <rect
          x="32"
          y="6"
          width="20"
          height="36"
          rx="2"
          stroke="currentColor"
          strokeWidth="2"
        />
        <path
          d="M24 24h8"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="20" cy="24" r="1.5" fill="currentColor" />
        <circle cx="36" cy="24" r="1.5" fill="currentColor" />
      </svg>
    );
  }

  type DoorStatusCardProps = {
    name: string;
    state: DoorState;
  };

  function DoorStatusCard({ name, state }: DoorStatusCardProps) {
    return (
      <article className={`door-status-card door-status-card--${state}`}>
        <div className="door-status-card-icon">
          <DoorIcon />
        </div>
        <div className="door-status-card-body">
          <h3 className="door-status-card-title">{name}</h3>
          <p className="door-status-card-label">Estado de puerta</p>
          <span className={`door-status-badge door-status-badge--${state}`}>
            <span className="door-status-badge-dot" aria-hidden />
            {DOOR_STATE_LABELS[state]}
          </span>
        </div>
      </article>
    );
  }

  function TabletIcon() {
    return (
      <svg
        viewBox="0 0 36 56"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
      >
        <rect
          x="4"
          y="4"
          width="28"
          height="46"
          rx="5"
          stroke="currentColor"
          strokeWidth="2.5"
        />
        <rect
          x="8"
          y="10"
          width="20"
          height="32"
          rx="2"
          fill="currentColor"
          opacity="0.12"
        />
        <circle cx="18" cy="46" r="2" fill="currentColor" opacity="0.35" />
      </svg>
    );
  }

  type DeviceCardProps = {
    title: string;
    icon: ReactNode;
    statusLabel: string;
    statusVariant: "operativo" | "no_operativo" | "apagado";
    version: string;
    updateAvailable?: boolean;
    availableVersion?: string;
    showRestart?: boolean;
    onRestart?: () => void;
  };

  function DeviceCard({
    title,
    icon,
    statusLabel,
    statusVariant,
    version,
    updateAvailable = false,
    availableVersion,
    showRestart = false,
    onRestart,
  }: DeviceCardProps) {
    return (
      <article className="device-card">
        {(updateAvailable || showRestart) && (
          <div className="device-card-actions">
            {showRestart && (
              <button
                type="button"
                className="btn btn-sm device-card-action-btn device-card-restart-btn"
                title="Reiniciar software de control"
                onClick={onRestart}
              >
                <RestartIcon />
                Reiniciar
              </button>
            )}
            {updateAvailable && (
              <button
                type="button"
                className="btn btn-primary btn-sm device-card-action-btn"
                title={
                  availableVersion
                    ? `Actualizar a ${availableVersion}`
                    : "Actualizar software"
                }
              >
                Actualizar
              </button>
            )}
          </div>
        )}
        <div className="device-card-icon">{icon}</div>
        <div className="device-card-body">
          <h3 className="device-card-title">{title}</h3>
          <dl className="device-card-meta">
            <div className="device-card-row">
              <dt>Estado</dt>
              <dd>
                <span
                  className={`device-card-status device-card-status--${statusVariant}`}
                >
                  <span className="device-card-status-dot" aria-hidden />
                  {statusLabel}
                </span>
              </dd>
            </div>
            <div className="device-card-row">
              <dt>Versión software</dt>
              <dd className="device-card-version">{version}</dd>
            </div>
          </dl>
        </div>
      </article>
    );
  }

  function DevicesIcon() {
    return (
      <svg
        className="sucursal-card-icon"
        viewBox="0 0 120 60"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
      >
        <rect
          x="4"
          y="10"
          width="52"
          height="38"
          rx="4"
          stroke="currentColor"
          strokeWidth="2.5"
        />
        <rect
          x="10"
          y="16"
          width="40"
          height="24"
          rx="2"
          fill="currentColor"
          opacity="0.12"
        />
        <rect
          x="22"
          y="48"
          width="16"
          height="3"
          rx="1"
          fill="currentColor"
          opacity="0.35"
        />
        <rect
          x="16"
          y="52"
          width="28"
          height="2"
          rx="1"
          fill="currentColor"
          opacity="0.2"
        />
        <rect
          x="68"
          y="6"
          width="28"
          height="46"
          rx="5"
          stroke="currentColor"
          strokeWidth="2.5"
        />
        <rect
          x="72"
          y="12"
          width="20"
          height="32"
          rx="2"
          fill="currentColor"
          opacity="0.12"
        />
        <circle cx="80" cy="48" r="2" fill="currentColor" opacity="0.35" />
      </svg>
    );
  }

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const b = await getBranch(id);
        if (!cancelled) setSucursal(branchToSucursal(b));
      } catch {
        if (!cancelled) navigate("/sucursales", { replace: true });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, navigate]);

  const refresh = useCallback(
    async (opts?: { full?: boolean }) => {
      if (!sucursal || !id) return;
      setLoading(true);
      setError(null);
      try {
        if (opts?.full || !data?.modes.length) {
          const snap = await fetchBranchSnapshot(id);
          const boards = Object.entries(snap.boards ?? {}).map(([bid, b]) => ({
            id: bid,
            data: b as PanelBoardState,
          }));
          setData({
            modes: snap.modes,
            currentMode: snap.currentMode,
            activeToggleRules: snap.activeToggleRules ?? [],
            branchAlerts: deriveAlertsFromBranchState(
              snap.currentMode,
              snap.activeToggleRules ?? [],
              {},
            ),
            boards,
            modulesConfig: snap.modulesConfig ?? [],
            panelTimestamp: snap.panelTimestamp ?? null,
            panelOk: snap.panelOk,
            panelError: snap.panelError,
          });
        } else {
          const st = await fetchBranchPanelStatus(id);
          const boards = Object.entries(st.boards ?? {}).map(([bid, b]) => ({
            id: bid,
            data: b as PanelBoardState,
          }));
          setData((prev) =>
            prev
              ? {
                  ...prev,
                  currentMode: st.currentMode ?? prev.currentMode,
                  boards,
                  modulesConfig: st.modulesConfig ?? prev.modulesConfig,
                  panelTimestamp: st.panelTimestamp ?? prev.panelTimestamp,
                  panelOk: st.panelOk,
                  panelError: st.panelError,
                }
              : prev,
          );
        }
      } catch (e) {
        setData(null);
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [sucursal, id, data?.modes.length],
  );

  useEffect(() => {
    if (sucursal) void refresh();
  }, [sucursal, refresh]);

  // Eventos WS: parche local (sin snapshot lento vía ZeroTier + Modbus).
  useEffect(() => {
    const msg = liveBranch?.lastMessage;
    if (!id || !live.connected || !msg) return;
    setData((prev) => {
      if (!prev) return prev;
      return applyLivePatch(prev, msg.type, msg.payload) ?? prev;
    });
  }, [id, live.connected, liveBranch?.lastMessage]);

  const doors = useMemo(() => {
    if (!data) return [];
    return DOOR_BOARD_CONFIG.map((door) => {
      const entry = data.boards.find((b) => b.id === door.boardId);
      const state = deriveDoorState(entry?.data);
      return {
        ...door,
        state,
      };
    });
  }, [data]);

  async function activateMode(ruleKey: string) {
    if (!sucursal || !id) return;
    setBusyKey(ruleKey);
    setError(null);
    try {
      await setBranchMode(id, ruleKey, true);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyKey(null);
    }
  }

  if (!sucursal) {
    return (
      <div className="content-view">
        <p>Cargando…</p>
      </div>
    );
  }

  const baseLabel = `${sucursal.useHttps ? "https" : "http"}://${sucursal.host}:${sucursal.port}`;
  const estadoLive = resolveSucursalEstado(
    sucursal.id,
    getSucursalEstado(sucursal),
    live,
  );
  const estadoLabel = SUCURSAL_ESTADO_LABELS[estadoLive];

  // Maqueta: versiones y conectividad fina hasta API COCE / heartbeat
  const PC_SOFTWARE_VERSION = "v1.3.0";
  const TABLET_SOFTWARE_VERSION = "v2.8.1";
  // Maqueta: hay versión homologada más nueva disponible en COCE
  const PC_AVAILABLE_VERSION = "v1.4.0";
  const TABLET_AVAILABLE_VERSION = "v2.9.0";
  const pcUpdateAvailable = true;
  const tabletUpdateAvailable = true;
  const panelReachable = !!data && !error;
  const tabletConnected = panelReachable;

  return (
    <div className="content-view">
      <header className="app-header app-header--sucursal">
        <div className="app-header-start">
          <div
            style={{ width: "80px", height: "40px", color: "var(--accent)" }}
          >
            <DevicesIcon />
          </div>
          <div>
            <h1>{sucursal.nombre}</h1>
            <span className="tag">{baseLabel}</span>
          </div>
        </div>

        <div
          className={`dashboard-sucursal-status dashboard-sucursal-status--${estadoLive}`}
          aria-label={`Estado: ${estadoLabel}`}
        >
          <span className="dashboard-sucursal-status-dot" aria-hidden />
          <span>{estadoLabel}</span>
        </div>

        <div className="row-actions app-header-end">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? "Actualizando…" : "Actualizar"}
          </button>
          <Link to="/sucursales" className="btn btn-ghost">
            Lista
          </Link>
          <Link
            to={`/sucursales/editar/${sucursal.id}`}
            className="btn btn-ghost"
          >
            Editar
          </Link>
        </div>
      </header>

      {error && <div className="alert alert-error">{error}</div>}

      {data ? (
        <BranchCriticalAlertBanner
          branchId={sucursal.id}
          branchName={sucursal.nombre}
          currentMode={data.currentMode}
          activeToggleRules={data.activeToggleRules}
          storedAlerts={data.branchAlerts}
        />
      ) : null}

      {!data && !error && loading && <p>Conectando con el sistema local…</p>}

      {data && (
        <div className="dashboard-content-wrapper">
          {/* Fila de KPIs */}
          <div className="kpi-grid">
            <article
              className="kpi-card"
              style={{ borderLeft: "4px solid var(--accent)" }}
            >
              <p>Modo activo en panel</p>
              <h3
                style={{
                  color: data.currentMode ? "var(--text)" : "var(--muted)",
                }}
              >
                {formatModeName(data.currentMode)}
              </h3>
            </article>
            <article
              className="kpi-card"
              style={{ borderLeft: "4px solid var(--ok)" }}
            >
              <p>Reglas habilitadas</p>
              <h3>
                {data.modes.filter((m) => m.enabled).length}{" "}
                <small
                  style={{
                    fontSize: "0.8rem",
                    color: "var(--muted)",
                    fontWeight: "normal",
                  }}
                >
                  de {data.modes.length}
                </small>
              </h3>
            </article>
            <article
              className="kpi-card"
              style={{ borderLeft: "4px solid #0f4c81" }}
            >
              <p>Módulos ETD8A12</p>
              <h3>
                {data.boards.length}{" "}
                <small
                  style={{
                    fontSize: "0.8rem",
                    color: "var(--muted)",
                    fontWeight: "normal",
                  }}
                >
                  conectados
                </small>
              </h3>
            </article>
          </div>

          <div className="device-cards-grid">
            <DeviceCard
              title="PC industrial"
              icon={<PcIcon />}
              statusLabel={estadoLabel}
              statusVariant={estadoLive}
              version={panelReachable ? PC_SOFTWARE_VERSION : "—"}
              updateAvailable={pcUpdateAvailable}
              availableVersion={PC_AVAILABLE_VERSION}
              showRestart
              onRestart={() => {
                if (
                  confirm(
                    "¿Reiniciar el software de control del PC industrial?",
                  )
                ) {
                  // Maqueta: acción remota pendiente de API COCE
                }
              }}
            />
            <DeviceCard
              title="Tablet"
              icon={<TabletIcon />}
              statusLabel={
                loading && !data
                  ? "Comprobando…"
                  : tabletConnected
                    ? "Operativo"
                    : "No operativo"
              }
              statusVariant={
                loading && !data
                  ? "no_operativo"
                  : tabletConnected
                    ? "operativo"
                    : "no_operativo"
              }
              version={tabletConnected ? TABLET_SOFTWARE_VERSION : "—"}
              updateAvailable={tabletUpdateAvailable}
              availableVersion={TABLET_AVAILABLE_VERSION}
            />
          </div>

          <section className="doors-section ">
            <div className="doors-section-header">
              <h2>Estado de las puertas</h2>
            </div>
            <div className="doors-grid">
              {doors.map((door) => (
                <DoorStatusCard
                  key={door.id}
                  name={door.name}
                  state={door.state}
                />
              ))}
            </div>
          </section>

          <div className="dashboard-panels-grid">
            {/* Panel de Modos */}
            <div className="card dashboard-panel">
              <div className="panel-header">
                <h2>Modos y reglas disponibles</h2>
                <p className="panel-subtitle">
                  Ejecución remota vía <code>POST /api/v1/set_mode</code>
                </p>
              </div>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Clave</th>
                      <th>Tipo</th>
                      <th style={{ textAlign: "center" }}>Habilitada</th>
                      <th style={{ textAlign: "center" }}>Activa ahora</th>
                      <th style={{ textAlign: "right" }}>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.modes.map((m) => {
                      const isCurrent = isPanelModeActiveNow(
                        m.key,
                        data.currentMode,
                        data.activeToggleRules,
                      );
                      return (
                        <tr
                          key={m.key}
                          className={isCurrent ? "row-highlight" : ""}
                        >
                          <td style={{ fontWeight: 500 }}>
                            {formatModeName(m.key)} <br />
                            <small
                              className="text-muted"
                              style={{
                                fontWeight: "normal",
                                fontSize: "0.8rem",
                              }}
                            >
                              {m.key}
                            </small>
                          </td>
                          <td className="text-muted">
                            {formatModeName(m.type, "—")}
                          </td>
                          <td style={{ textAlign: "center" }}>
                            {m.enabled ? (
                              <span className="badge badge-ok">Sí</span>
                            ) : (
                              <span className="badge badge-off">No</span>
                            )}
                          </td>
                          <td style={{ textAlign: "center" }}>
                            {isCurrent ? (
                              <span className="badge badge-ok">Activa</span>
                            ) : (
                              <span className="text-muted">—</span>
                            )}
                          </td>
                          <td style={{ textAlign: "right" }}>
                            <button
                              type="button"
                              className={
                                isCurrent
                                  ? "btn btn-ghost btn-sm"
                                  : "btn btn-primary btn-sm"
                              }
                              disabled={
                                !m.enabled || busyKey !== null || isCurrent
                              }
                              onClick={() => void activateMode(m.key)}
                            >
                              {busyKey === m.key
                                ? "Activando…"
                                : isCurrent
                                  ? "En uso"
                                  : "Activar"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Panel de Placas */}
            <div className="card dashboard-panel">
              <div className="panel-header">
                <h2>Hardware (Placas ETD8A12)</h2>
                <p className="panel-subtitle">
                  Estado de hardware local vía <code>/api/panel/status</code>
                </p>
              </div>

              {!sucursal.usuarioPanel?.trim() ||
              !(sucursal.hasPasswordPanel || sucursal.passwordPanel) ? (
                <div className="empty-state">
                  <svg
                    width="48"
                    height="48"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    style={{ color: "var(--muted)", marginBottom: "1rem" }}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"
                    />
                  </svg>
                  <p>Faltan credenciales del panel web.</p>
                  <Link
                    to={`/sucursales/editar/${sucursal.id}`}
                    className="btn btn-ghost btn-sm"
                    style={{ marginTop: "0.5rem" }}
                  >
                    Configurar credenciales
                  </Link>
                </div>
              ) : data.panelError ? (
                <div className="alert alert-error" style={{ margin: "1rem" }}>
                  Panel: {data.panelError}
                </div>
              ) : data.panelOk && data.boards.length === 0 ? (
                <div className="empty-state">
                  <p>No se han detectado placas configuradas.</p>
                </div>
              ) : (
                <>
                  {data.panelTimestamp && (
                    <p className="panel-io-timestamp">
                      Última lectura panel:{" "}
                      {new Date(data.panelTimestamp).toLocaleString("es-ES")}
                    </p>
                  )}
                  <div className="board-io-stack">
                    {[...data.boards]
                      .sort((a, b) => Number(a.id) - Number(b.id))
                      .map(({ id: bid, data: b }) => (
                        <BoardIoPanel
                          key={bid}
                          branchId={id!}
                          boardId={bid}
                          board={b}
                          moduleConfig={moduleForBoard(data.modulesConfig, bid)}
                          canControl={
                            !!(
                              sucursal?.usuarioPanel?.trim() &&
                              (sucursal.hasPasswordPanel ||
                                sucursal.passwordPanel)
                            )
                          }
                          onRefresh={refresh}
                        />
                      ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
