import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Sucursal, SucursalEstado } from '../types';
import type { BranchLocation } from '../api/coceClient';
import { SUCURSAL_ESTADO_LABELS } from '../sucursalEstado';
import { sucursalMapDotIconUrl, SucursalMapPin, MAP_DOT_ANCHOR, MAP_DOT_SIZE } from './SucursalDevicesIcon';
import { hasMapCoords, loadGoogleMaps } from '../utils/googleMaps';
import { GOOGLE_MAPS_NIGHT_STYLES } from '../utils/googleMapsNightStyles';
import type { ModeDisplay } from '../utils/ruleModeColors';

export type SucursalMapItem = {
  sucursal: Sucursal;
  location?: BranchLocation;
  estado: SucursalEstado;
  mode: ModeDisplay;
};

type Props = {
  items: SucursalMapItem[];
  withoutLocation: SucursalMapItem[];
  locationsLoading?: boolean;
  onDelete: (id: string, nombre: string) => void;
};

const SPAIN_CENTER = { lat: 40.416775, lng: -3.70379 };

function formatAddress(location?: BranchLocation): string | null {
  if (!location) return null;
  if (location.address?.trim()) return location.address.trim();
  if (hasMapCoords(location)) {
    return `${Number(location.latitude).toFixed(5)}, ${Number(location.longitude).toFixed(5)}`;
  }
  return null;
}

function triggerMapResize(g: typeof google, map: google.maps.Map) {
  window.setTimeout(() => {
    g.maps.event.trigger(map, 'resize');
    const center = map.getCenter();
    if (center) map.setCenter(center);
  }, 120);
}

export function SucursalMap({
  items,
  withoutLocation,
  locationsLoading,
  onDelete,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const googleRef = useRef<typeof google | null>(null);
  const markersRef = useRef<google.maps.Marker[]>([]);
  const [mapError, setMapError] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [selected, setSelected] = useState<SucursalMapItem | null>(null);

  const mappable = useMemo(
    () => items.filter((item) => hasMapCoords(item.location)),
    [items],
  );

  const mappableKey = useMemo(
    () =>
      mappable
        .map(
          (item) =>
            `${item.sucursal.id}:${item.location?.latitude}:${item.location?.longitude}:${item.mode.modeKey}:${item.mode.modeColor}`,
        )
        .join('|'),
    [mappable],
  );

  useEffect(() => {
    let cancelled = false;
    let resizeObserver: ResizeObserver | undefined;

    void loadGoogleMaps()
      .then((g) => {
        if (cancelled || !containerRef.current) return;
        googleRef.current = g;
        const map = new g.maps.Map(containerRef.current, {
          center: SPAIN_CENTER,
          zoom: 6,
          styles: GOOGLE_MAPS_NIGHT_STYLES,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: true,
          gestureHandling: 'greedy',
          backgroundColor: '#242f3e',
          clickableIcons: false,
        });
        mapRef.current = map;
        setMapReady(true);
        triggerMapResize(g, map);

        if (typeof ResizeObserver !== 'undefined') {
          resizeObserver = new ResizeObserver(() => {
            if (mapRef.current && googleRef.current) {
              triggerMapResize(googleRef.current, mapRef.current);
            }
          });
          resizeObserver.observe(containerRef.current);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setMapError(e instanceof Error ? e.message : String(e));
        }
      });

    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      markersRef.current.forEach((m) => m.setMap(null));
      markersRef.current = [];
      mapRef.current = null;
      googleRef.current = null;
      setMapReady(false);
    };
  }, []);

  useEffect(() => {
    const g = googleRef.current;
    const map = mapRef.current;
    if (!mapReady || !g || !map) return;

    try {
      markersRef.current.forEach((m) => m.setMap(null));
      markersRef.current = [];

      const bounds = new g.maps.LatLngBounds();

      for (const item of mappable) {
        const lat = Number(item.location!.latitude);
        const lng = Number(item.location!.longitude);
        const position = { lat, lng };

        const marker = new g.maps.Marker({
          position,
          map,
          title: item.sucursal.nombre,
          icon: {
            url: sucursalMapDotIconUrl(item.mode.modeColor),
            scaledSize: new g.maps.Size(MAP_DOT_SIZE, MAP_DOT_SIZE),
            anchor: new g.maps.Point(MAP_DOT_ANCHOR, MAP_DOT_ANCHOR),
          },
        });

        marker.addListener('click', () => {
          setSelected(item);
          map.panTo(position);
        });

        markersRef.current.push(marker);
        bounds.extend(position);
      }

      if (mappable.length === 1) {
        map.setCenter(bounds.getCenter()!);
        map.setZoom(14);
      } else if (mappable.length > 1) {
        map.fitBounds(bounds, 56);
      } else {
        map.setCenter(SPAIN_CENTER);
        map.setZoom(6);
      }
      triggerMapResize(g, map);
    } catch (e) {
      console.error('SucursalMap markers:', e);
      setMapError(e instanceof Error ? e.message : String(e));
    }
  }, [mappableKey, mapReady, mappable]);

  useEffect(() => {
    if (!selected) return;
    const stillVisible = mappable.some((i) => i.sucursal.id === selected.sucursal.id);
    if (!stillVisible) setSelected(null);
  }, [mappable, selected]);

  if (mapError) {
    return (
      <div className="alert alert-error sucursal-map-error">
        No se pudo cargar Google Maps: {mapError}
      </div>
    );
  }

  const selectedAddress = selected ? formatAddress(selected.location) : null;

  return (
    <div className="sucursal-map-wrap">
      <div ref={containerRef} className="sucursal-map" aria-label="Mapa de sucursales" />

      {locationsLoading ? (
        <div className="sucursal-map-overlay">Cargando ubicaciones…</div>
      ) : null}

      {!mapReady && !mapError ? (
        <div className="sucursal-map-overlay">Iniciando mapa…</div>
      ) : null}

      {selected ? (
        <aside className="sucursal-map-detail" role="dialog" aria-label={selected.sucursal.nombre}>
          <button
            type="button"
            className="sucursal-map-detail-close"
            onClick={() => setSelected(null)}
            aria-label="Cerrar"
          >
            ×
          </button>
          <div className="sucursal-map-detail-icon">
            <SucursalMapPin modeColor={selected.mode.modeColor} />
          </div>
          <div className="sucursal-map-detail-name">{selected.sucursal.nombre}</div>
          {selectedAddress ? (
            <div className="sucursal-map-detail-address">{selectedAddress}</div>
          ) : null}
          {selected.mode.modeLabel ? (
            <div
              className="sucursal-map-detail-mode"
              style={{
                color: selected.mode.modeColor,
                borderColor: selected.mode.modeColor,
                background: `${selected.mode.modeColor}18`,
              }}
            >
              <span
                className="sucursal-map-detail-mode-dot"
                style={{ background: selected.mode.modeColor }}
                aria-hidden
              />
              {selected.mode.modeLabel}
            </div>
          ) : null}
          <div
            className={`sucursal-map-detail-status sucursal-map-detail-status--${selected.estado}`}
          >
            <span className="sucursal-map-detail-status-dot" aria-hidden />
            {SUCURSAL_ESTADO_LABELS[selected.estado]}
          </div>
          <div className="sucursal-map-detail-actions">
            <Link to={`/control/${selected.sucursal.id}`} className="btn btn-open btn-sm">
              Abrir
            </Link>
            <Link to={`/sucursales/editar/${selected.sucursal.id}`} className="btn btn-ghost btn-sm">
              Editar
            </Link>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              onClick={() => onDelete(selected.sucursal.id, selected.sucursal.nombre)}
            >
              Eliminar
            </button>
          </div>
        </aside>
      ) : null}

      {withoutLocation.length > 0 ? (
        <section className="sucursal-map-missing card">
          <h2 className="sucursal-map-missing-title">
            {withoutLocation.length} sucursal{withoutLocation.length === 1 ? '' : 'es'} sin ubicación en mapa
          </h2>
          <p className="sucursal-map-missing-hint">
            Configura latitud y longitud en la consola de la oficina (Horarios → Ubicación) o edita la
            sucursal para comprobar la conexión.
          </p>
          <ul className="sucursal-map-missing-list">
            {withoutLocation.map((item) => (
              <li key={item.sucursal.id}>
                <span>{item.sucursal.nombre}</span>
                <Link to={`/sucursales/editar/${item.sucursal.id}`} className="btn btn-ghost btn-sm">
                  Editar
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
