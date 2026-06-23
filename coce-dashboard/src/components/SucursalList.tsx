import { useCallback, useEffect, useMemo, useState } from 'react';

import { Link } from 'react-router-dom';

import type { Sucursal, SucursalEstado } from '../types';

import { deleteBranch, fetchBranchLocation, listBranches } from '../api/coceClient';

import type { BranchLocation } from '../api/coceClient';

import { resolveSucursalEstado, useCoceLive } from '../context/CoceLiveContext';

import { getSucursalEstado, SUCURSAL_ESTADO_LABELS } from '../sucursalEstado';

import { SucursalMap } from './SucursalMap';

import type { SucursalMapItem } from './SucursalMap';

import { ErrorBoundary } from './ErrorBoundary';

import { hasMapCoords } from '../utils/googleMaps';
import { resolveBranchModeDisplay } from '../utils/ruleModeColors';



type EstadoFilter = '' | SucursalEstado;



export function SucursalList() {

  const live = useCoceLive();

  const [list, setList] = useState<Sucursal[]>([]);

  const [search, setSearch] = useState('');

  const [estadoFilter, setEstadoFilter] = useState<EstadoFilter>('');

  const [error, setError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);

  const [locationsLoading, setLocationsLoading] = useState(false);

  const [locations, setLocations] = useState<Record<string, BranchLocation>>({});



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

    if (!list.length) {
      setLocations({});
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

            return [s.id, loc] as const;

          } catch {

            return null;

          }

        }),

      );

      if (cancelled) return;

      const next: Record<string, BranchLocation> = {};

      for (const pair of pairs) {

        if (pair) next[pair[0]] = pair[1];

      }

      setLocations(next);

      setLocationsLoading(false);

    })();

    return () => {
      cancelled = true;
    };
  }, [list]);



  const sorted = useMemo(

    () => [...list].sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')),

    [list],

  );

  const filtered = useMemo(() => {

    let result = sorted;

    const q = search.trim().toLowerCase();

    if (q) {

      result = result.filter(

        (s) =>

          s.nombre.toLowerCase().includes(q) ||

          s.host.toLowerCase().includes(q),

      );

    }

    if (estadoFilter) {

      result = result.filter(

        (s) =>

          resolveSucursalEstado(s.id, getSucursalEstado(s), live) === estadoFilter,

      );

    }

    return result;

  }, [sorted, search, estadoFilter, live]);



  const mapItems = useMemo<SucursalMapItem[]>(

    () =>

      filtered.map((s) => {
        const loc = locations[s.id];
        const liveBranch = live.getLiveBranch(s.id);
        return {
          sucursal: s,
          location: loc,
          estado: resolveSucursalEstado(s.id, getSucursalEstado(s), live),
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

    [filtered, locations, live],

  );



  const withoutLocation = useMemo(

    () => mapItems.filter((item) => !hasMapCoords(item.location)),

    [mapItems],

  );



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

        Las credenciales de cada oficina se almacenan cifradas en <strong>coce-api</strong>. Pulsa un pin en el

        mapa para abrir o editar la sucursal.

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

          <p>No hay sucursales registradas. Pulsa «Añadir sucursal» para conectar un sistema local.</p>

        </div>

      ) : (

        <>

          <div className="sucursal-toolbar">

            <div className="sucursal-search">

              <label className="sucursal-search-label" htmlFor="sucursal-search-input">

                Buscar sucursal

              </label>

              <input

                id="sucursal-search-input"

                type="search"

                className="sucursal-search-input"

                placeholder="Nombre o IP de la oficina…"

                value={search}

                onChange={(e) => setSearch(e.target.value)}

                autoComplete="off"

              />

            </div>



            <div className="sucursal-filter">

              <label className="sucursal-search-label" htmlFor="sucursal-estado-filter">

                Estado

              </label>

              <select

                id="sucursal-estado-filter"

                className="sucursal-filter-select"

                value={estadoFilter}

                onChange={(e) => setEstadoFilter(e.target.value as EstadoFilter)}

              >

                <option value="">Todos</option>

                <option value="operativo">{SUCURSAL_ESTADO_LABELS.operativo}</option>

                <option value="no_operativo">{SUCURSAL_ESTADO_LABELS.no_operativo}</option>

                <option value="apagado">{SUCURSAL_ESTADO_LABELS.apagado}</option>

              </select>

            </div>

          </div>



          {filtered.length === 0 ? (

            <div className="card">

              <p>No hay sucursales con los filtros aplicados.</p>

            </div>

          ) : (
            <div className="sucursal-map-stage">
              <ErrorBoundary>
                <SucursalMap
                  items={mapItems}
                  withoutLocation={withoutLocation}
                  locationsLoading={locationsLoading}
                  onDelete={onDelete}
                />
              </ErrorBoundary>
            </div>
          )}

        </>

      )}

    </div>

  );

}


