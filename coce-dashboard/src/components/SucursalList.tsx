import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Link } from "react-router-dom";

import type { Sucursal, SucursalEstado } from "../types";

import {
  deleteBranch,
  fetchBranchLocation,
  listBranches,
} from "../api/coceClient";

import type { BranchLocation } from "../api/coceClient";

import { resolveSucursalEstado, useCoceLive } from "../context/CoceLiveContext";

import { getSucursalEstado } from "../sucursalEstado";

import {
  connectivityFromLegacyEstado,
  CONNECTIVITY_LABELS,
  CONNECTIVITY_PIN_COLORS,
  resolveConnectivityState,
} from "../utils/connectivityState";

import { SucursalMap } from "./SucursalMap";

import type { SucursalMapItem } from "./SucursalMap";

import { SucursalKpiBar } from "./SucursalKpiBar";

import { ErrorBoundary } from "./ErrorBoundary";

import { resolveKpiMetrics } from "../data/mockKpiMetrics";

import { hasMapCoords } from "../utils/googleMaps";
import { resolveBranchModeDisplay } from "../utils/ruleModeColors";
import { SucursalDevicesIcon } from "./SucursalDevicesIcon";

type EstadoFilter = "" | SucursalEstado;

const SEARCH_DEBOUNCE_MS = 300;
const LIVE_LOG_LIMIT = 120;

type BranchLog = {
  id: string;
  branchId: string;
  branchName: string;
  ts: number;
  eventType: string;
  detail: string;
};

function normalizeSearch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function summarizeLogPayload(
  payload: Record<string, unknown> | undefined,
): string {
  if (!payload) return "Actualización en tiempo real";
  const firstText = ["message", "detail", "reason"]
    .map((k) => payload[k])
    .find((v) => typeof v === "string" && String(v).trim());
  if (firstText) return String(firstText).slice(0, 120);
  const firstEntry = Object.entries(payload).find(([, v]) =>
    ["string", "number", "boolean"].includes(typeof v),
  );
  if (!firstEntry) return "Actualización en tiempo real";
  return `${firstEntry[0]}=${String(firstEntry[1]).slice(0, 80)}`;
}

function formatLogTime(ts: number): string {
  return new Date(ts).toLocaleTimeString("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function SucursalList() {
  const live = useCoceLive();

  const [list, setList] = useState<Sucursal[]>([]);

  const [search, setSearch] = useState("");

  const [debouncedSearch, setDebouncedSearch] = useState("");

  const [estadoFilter, setEstadoFilter] = useState<EstadoFilter>("");

  const [error, setError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);

  const [locationsLoading, setLocationsLoading] = useState(false);

  const [locations, setLocations] = useState<Record<string, BranchLocation>>(
    {},
  );

  const [locationReachable, setLocationReachable] = useState<
    Record<string, boolean>
  >({});
  const [liveLogs, setLiveLogs] = useState<BranchLog[]>([]);
  const lastLogSignatureRef = useRef<Record<string, string>>({});
  const [selectedBranchId, setSelectedBranchId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);

    setError(null);

    try {
      setList(await listBranches());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search);
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (!list.length) {
      setLocations({});
      setLocationReachable({});
      setLocationsLoading(false);
      return;
    }

    let cancelled = false;

    setLocationsLoading(true);

    void (async () => {
      const pairs = await Promise.all(
        list.map(async (s) => {
          try {
            const loc = await fetchBranchLocation(s.id);

            return { id: s.id, ok: true as const, loc };
          } catch {
            return { id: s.id, ok: false as const };
          }
        }),
      );

      if (cancelled) return;

      const next: Record<string, BranchLocation> = {};

      const reachable: Record<string, boolean> = {};

      for (const pair of pairs) {
        reachable[pair.id] = pair.ok;

        if (pair.ok) next[pair.id] = pair.loc;
      }

      setLocations(next);

      setLocationReachable(reachable);

      setLocationsLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [list]);

  const sorted = useMemo(
    () => [...list].sort((a, b) => a.nombre.localeCompare(b.nombre, "es")),

    [list],
  );

  const filtered = useMemo(() => {
    let result = sorted;

    const q = normalizeSearch(debouncedSearch);

    if (q) {
      result = result.filter((s) => {
        const location = locations[s.id];

        const searchable = normalizeSearch(
          [s.nombre, s.host, location?.address ?? ""].filter(Boolean).join(" "),
        );

        return searchable.includes(q);
      });
    }

    if (estadoFilter) {
      const want = connectivityFromLegacyEstado(estadoFilter);

      result = result.filter((s) => {
        const loc = locations[s.id];

        const liveBranch = live.getLiveBranch(s.id);

        const currentMode = loc?.currentMode ?? liveBranch?.currentMode ?? null;

        return (
          resolveConnectivityState(s.id, {
            live,

            manualEstado: getSucursalEstado(s),

            locationReachable: locationReachable[s.id] ?? false,

            currentMode,
          }) === want
        );
      });
    }

    return result;
  }, [
    sorted,
    debouncedSearch,
    estadoFilter,
    live,
    locations,
    locationReachable,
  ]);

  const mapItems = useMemo<SucursalMapItem[]>(
    () =>
      filtered.map((s) => {
        const loc = locations[s.id];
        const liveBranch = live.getLiveBranch(s.id);
        const currentMode = loc?.currentMode ?? liveBranch?.currentMode ?? null;
        const manualEstado = getSucursalEstado(s);
        return {
          sucursal: s,
          location: loc,
          estado: resolveSucursalEstado(s.id, manualEstado, live),
          connectivity: resolveConnectivityState(s.id, {
            live,
            manualEstado,
            locationReachable: locationReachable[s.id] ?? false,
            currentMode,
          }),
          mode: resolveBranchModeDisplay(
            loc
              ? {
                  currentMode: loc.currentMode,
                  modeLabel: loc.modeLabel,
                  modeColor: loc.modeColor,
                }
              : undefined,
            liveBranch?.currentMode,
            live.connected,
          ),
        };
      }),

    [filtered, locations, locationReachable, live],
  );

  const withoutLocation = useMemo(
    () => mapItems.filter((item) => !hasMapCoords(item.location)),

    [mapItems],
  );

  useEffect(() => {
    const incoming: BranchLog[] = [];
    for (const item of mapItems) {
      const liveBranch = live.getLiveBranch(item.sucursal.id);
      const ts = liveBranch?.lastEventTs;
      const msg = liveBranch?.lastMessage;
      if (!ts || !msg?.type) continue;
      const signature = `${ts}:${msg.type}`;
      if (lastLogSignatureRef.current[item.sucursal.id] === signature) continue;
      lastLogSignatureRef.current[item.sucursal.id] = signature;
      incoming.push({
        id: `${item.sucursal.id}:${signature}`,
        branchId: item.sucursal.id,
        branchName: item.sucursal.nombre,
        ts,
        eventType: msg.type,
        detail: summarizeLogPayload(msg.payload),
      });
    }
    if (!incoming.length) return;
    incoming.sort((a, b) => b.ts - a.ts);
    setLiveLogs((prev) => [...incoming, ...prev].slice(0, LIVE_LOG_LIMIT));
  }, [mapItems, live]);

  useEffect(() => {
    if (!selectedBranchId) return;
    if (!mapItems.some((item) => item.sucursal.id === selectedBranchId)) {
      setSelectedBranchId(null);
    }
  }, [mapItems, selectedBranchId]);

  const kpiMetrics = useMemo(() => {
    if (selectedBranchId) {
      return resolveKpiMetrics([selectedBranchId], live);
    }
    return resolveKpiMetrics(
      mapItems.map((item) => item.sucursal.id),
      live,
    );
  }, [selectedBranchId, mapItems, live]);

  const kpiScopeLabel = useMemo(() => {
    if (!selectedBranchId) {
      return `Consolidado general · ${mapItems.length} sucursal${mapItems.length === 1 ? "" : "es"}`;
    }
    const selected = mapItems.find((item) => item.sucursal.id === selectedBranchId);
    return selected ? `Sucursal: ${selected.sucursal.nombre}` : "Sucursal seleccionada";
  }, [selectedBranchId, mapItems]);

  const openBranchInNewTab = useCallback((id: string) => {
    window.open(`/control/${id}`, "_blank", "noopener,noreferrer");
  }, []);

  async function onDelete(id: string, nombre: string) {
    if (!confirm(`¿Eliminar la sucursal «${nombre}»?`)) return;

    try {
      await deleteBranch(id);

      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="content-view content-view--map">
      <header className="app-header">
        <div>
          <h1>COCE — Dashboard</h1>

          <span className="tag">Mapa de sucursales</span>
        </div>

        <Link to="/sucursales/nueva" className="btn btn-primary">
          Añadir sucursal
        </Link>
      </header>

      <div className="alert alert-info">
        Las credenciales de cada oficina se almacenan cifradas en{" "}
        <strong>coce-api</strong>. Pulsa un pin en el mapa para abrir o editar
        la sucursal.
        {live.connected && (
          <span className="badge badge-ok" style={{ marginLeft: 8 }}>
            Tiempo real activo
          </span>
        )}
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <p>Cargando sucursales…</p>
      ) : sorted.length === 0 ? (
        <div className="card">
          <p>
            No hay sucursales registradas. Pulsa «Añadir sucursal» para conectar
            un sistema local.
          </p>
        </div>
      ) : (
        <>
          <SucursalKpiBar
            metrics={kpiMetrics}
            scopeLabel={kpiScopeLabel}
            selectedBranchId={selectedBranchId}
            onClearSelection={() => setSelectedBranchId(null)}
          />

          <div className="sucursal-toolbar">
            <div className="sucursal-search">
              <label
                className="sucursal-search-label"
                htmlFor="sucursal-search-input"
              >
                Buscar sucursal
              </label>

              <input
                id="sucursal-search-input"
                type="search"
                className="sucursal-search-input"
                placeholder="Nombre, dirección o IP de la oficina…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                autoComplete="off"
              />
            </div>

            <div className="sucursal-filter">
              <label
                className="sucursal-search-label"
                htmlFor="sucursal-estado-filter"
              >
                Estado
              </label>

              <select
                id="sucursal-estado-filter"
                className="sucursal-filter-select"
                value={estadoFilter}
                onChange={(e) =>
                  setEstadoFilter(e.target.value as EstadoFilter)
                }
              >
                <option value="">Todos</option>

                <option value="operativo">{CONNECTIVITY_LABELS.activo}</option>

                <option value="no_operativo">
                  {CONNECTIVITY_LABELS.inactivo}
                </option>

                <option value="apagado">
                  {CONNECTIVITY_LABELS.desconectado}
                </option>
              </select>
            </div>
          </div>

          {filtered.length === 0 ? (
            <div className="card">
              <p>No hay sucursales con los filtros aplicados.</p>
            </div>
          ) : (
            <div className="sucursal-map-stage sucursal-map-stage--with-panel">
              <ErrorBoundary>
                <SucursalMap
                  items={mapItems}
                  withoutLocation={withoutLocation}
                  locationsLoading={locationsLoading}
                  selectedBranchId={selectedBranchId}
                  onSelectBranch={setSelectedBranchId}
                  onOpenBranch={openBranchInNewTab}
                  onDelete={onDelete}
                />
              </ErrorBoundary>

              <aside
                className="sucursal-side-panel"
                aria-label="Listado y log de sucursales"
              >
                <section className="sucursal-side-section sucursal-side-section--branches">
                  <h2 className="sucursal-side-title">
                    Sucursales ({mapItems.length})
                  </h2>
                  <div className="sucursal-side-list">
                    {mapItems.map((item) => {
                      const addr = item.location?.address?.trim();
                      const summary =
                        addr || `${item.sucursal.host}:${item.sucursal.port}`;
                      return (
                        <article
                          key={item.sucursal.id}
                          className={`sucursal-side-card${selectedBranchId === item.sucursal.id ? " sucursal-side-card--selected" : ""}`}
                          onClick={() => setSelectedBranchId(item.sucursal.id)}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              setSelectedBranchId(item.sucursal.id);
                            }
                          }}
                        >
                          <div className="sucursal-side-card-top">
                            <SucursalDevicesIcon
                              className="sucursal-side-card-icon"
                              width={46}
                              height={24}
                              strokeColor={
                                CONNECTIVITY_PIN_COLORS[item.connectivity]
                              }
                            />
                            <div className="sucursal-side-card-head-main">
                              <strong>{item.sucursal.nombre}</strong>
                              <span
                                className={`sucursal-map-detail-status sucursal-map-detail-status--${item.connectivity}`}
                              >
                                <span
                                  className="sucursal-map-detail-status-dot"
                                  aria-hidden
                                />
                                {CONNECTIVITY_LABELS[item.connectivity]}
                              </span>
                            </div>
                          </div>
                          <p className="sucursal-side-card-summary">
                            {summary}
                          </p>
                          {item.location?.openingHours &&
                          item.location?.schedulesEnabled !== false ? (
                            <p className="sucursal-side-card-hours">
                              {item.location.openingHours}
                            </p>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                </section>

                <section className="sucursal-side-section sucursal-side-section--logs">
                  <h2 className="sucursal-side-title">Log</h2>
                  {live.connected ? (
                    <ul className="sucursal-side-log-list">
                      {liveLogs.length === 0 ? (
                        <li className="sucursal-side-log-empty">
                          Esperando eventos de sucursales…
                        </li>
                      ) : (
                        liveLogs.slice(0, 24).map((log) => (
                          <li key={log.id}>
                            <button
                              type="button"
                              className="sucursal-side-log-item"
                              onClick={() => openBranchInNewTab(log.branchId)}
                            >
                              <span className="sucursal-side-log-head">
                                <strong>{log.branchName}</strong>
                                <span>{formatLogTime(log.ts)}</span>
                              </span>
                              <span className="sucursal-side-log-type">
                                {log.eventType}
                              </span>
                              <span className="sucursal-side-log-detail">
                                {log.detail}
                              </span>
                            </button>
                          </li>
                        ))
                      )}
                    </ul>
                  ) : (
                    <p className="sucursal-side-log-empty">
                      Tiempo real desconectado en COCE.
                    </p>
                  )}
                </section>
              </aside>
            </div>
          )}
        </>
      )}
    </div>
  );
}
