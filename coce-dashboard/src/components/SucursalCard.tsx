import { Link } from "react-router-dom";
import type { Sucursal } from "../types";
import type { BranchLocation } from "../api/coceClient";
import { SucursalDevicesIcon } from "./SucursalDevicesIcon";
import { resolveSucursalEstado, useCoceLive } from "../context/CoceLiveContext";
import { getSucursalEstado, SUCURSAL_ESTADO_LABELS } from "../sucursalEstado";

function formatPerfil(sucursal: Sucursal): string {
  const hostLabel =
    sucursal.port === 80 || sucursal.port === 443
      ? sucursal.host
      : `${sucursal.host}:${sucursal.port}`;
  const proto = sucursal.useHttps ? "https" : "http";
  return `${proto}://${hostLabel}`;
}

function formatLocation(loc?: BranchLocation): string | null {
  if (!loc) return null;
  if (loc.address?.trim()) return loc.address.trim();
  if (loc.latitude != null && loc.longitude != null) {
    return `${Number(loc.latitude).toFixed(5)}, ${Number(loc.longitude).toFixed(5)}`;
  }
  return null;
}

type Props = {
  sucursal: Sucursal;
  location?: BranchLocation;
  onDelete: (id: string, nombre: string) => void;
};

export function SucursalCard({ sucursal, location, onDelete }: Props) {
  const live = useCoceLive();
  const estado = resolveSucursalEstado(
    sucursal.id,
    getSucursalEstado(sucursal),
    live,
  );
  const estadoLabel = SUCURSAL_ESTADO_LABELS[estado];
  const perfil = formatPerfil(sucursal);
  const ubicacion = formatLocation(location);

  return (
    <article className="sucursal-list-item">
      <div className="sucursal-list-item-icon-wrap" aria-hidden>
        <SucursalDevicesIcon estado={estado} className="sucursal-list-item-icon" />
      </div>

      <div className="sucursal-list-item-info">
        <div className="sucursal-list-item-name">{sucursal.nombre}</div>
        <div className="sucursal-list-item-perfil" title="Perfil de conexión">
          {perfil}
        </div>
        {ubicacion ? (
          <div className="sucursal-list-item-perfil" title="Ubicación configurada en la oficina">
            {ubicacion}
          </div>
        ) : null}
      </div>

      <div
        className={`sucursal-list-item-status sucursal-list-item-status--${estado}`}
        aria-label={`Estado: ${estadoLabel}`}
      >
        <span className="sucursal-list-item-status-dot" aria-hidden />
        <span className="sucursal-list-item-status-label">{estadoLabel}</span>
      </div>

      <footer className="sucursal-list-item-actions">
        <Link to={`/control/${sucursal.id}`} className="btn btn-open btn-sm">
          Abrir
        </Link>
        <Link
          to={`/sucursales/editar/${sucursal.id}`}
          className="btn btn-ghost btn-sm"
        >
          Editar
        </Link>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          onClick={() => onDelete(sucursal.id, sucursal.nombre)}
        >
          Eliminar
        </button>
      </footer>
    </article>
  );
}
