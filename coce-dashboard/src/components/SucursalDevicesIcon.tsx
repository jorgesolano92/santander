import type { SucursalEstado } from '../types';

const ESTADO_STROKE: Record<SucursalEstado, string> = {
  operativo: '#16a34a',
  no_operativo: '#d97706',
  apagado: '#dc2626',
};

export const MAP_ICON_STROKE = '#ec1c24';
export const MAP_MARKER_SIZE = 56;
export const MAP_MARKER_ANCHOR = 28;

type Props = {
  estado?: SucursalEstado;
  className?: string;
  width?: number;
  height?: number;
  strokeColor?: string;
};

/** Icono PC + móvil (card de sucursal / listado). */
export function SucursalDevicesIcon({
  estado = 'operativo',
  className,
  width = 120,
  height = 60,
  strokeColor,
}: Props) {
  const stroke = strokeColor ?? ESTADO_STROKE[estado];
  return (
    <svg
      className={className}
      width={width}
      height={height}
      viewBox="0 0 120 60"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect x="4" y="10" width="52" height="38" rx="4" stroke={stroke} strokeWidth="2.5" />
      <rect x="10" y="16" width="40" height="24" rx="2" fill={stroke} opacity="0.12" />
      <rect x="22" y="48" width="16" height="3" rx="1" fill={stroke} opacity="0.35" />
      <rect x="16" y="52" width="28" height="2" rx="1" fill={stroke} opacity="0.2" />
      <rect x="68" y="6" width="28" height="46" rx="5" stroke={stroke} strokeWidth="2.5" />
      <rect x="72" y="12" width="20" height="32" rx="2" fill={stroke} opacity="0.12" />
      <circle cx="80" cy="48" r="2" fill={stroke} opacity="0.35" />
    </svg>
  );
}

function MapPinIconGlyph() {
  const s = MAP_ICON_STROKE;
  return (
    <g transform="translate(11, 18) scale(0.33)" fill="none" stroke={s} strokeWidth="2.8">
      <rect x="4" y="10" width="52" height="38" rx="4" fill="#ffffff" />
      <rect x="10" y="16" width="40" height="24" rx="2" fill={s} opacity="0.12" />
      <rect x="22" y="48" width="16" height="3" rx="1" fill={s} opacity="0.35" />
      <rect x="16" y="52" width="28" height="2" rx="1" fill={s} opacity="0.2" />
      <rect x="68" y="6" width="28" height="46" rx="5" fill="#ffffff" />
      <rect x="72" y="12" width="20" height="32" rx="2" fill={s} opacity="0.12" />
      <circle cx="80" cy="48" r="2" fill={s} opacity="0.35" />
    </g>
  );
}

/** Pin circular (mapa y panel de detalle): borde = color del modo, icono rojo dentro. */
export function SucursalMapPin({
  modeColor,
  size = MAP_MARKER_SIZE,
  className,
}: {
  modeColor: string;
  size?: number;
  className?: string;
}) {
  const border = modeColor || '#6b7280';
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 56 56"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <circle cx="28" cy="28" r="25" fill="#ffffff" stroke={border} strokeWidth="3.5" />
      <MapPinIconGlyph />
    </svg>
  );
}

/** Pin del mapa Google Maps (misma apariencia que SucursalMapPin). */
export function sucursalMarkerIconUrl(modeColor: string): string {
  const border = modeColor || '#6b7280';
  const s = MAP_ICON_STROKE;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 56 56" width="56" height="56">
    <circle cx="28" cy="28" r="25" fill="#ffffff" stroke="${border}" stroke-width="3.5"/>
    <g transform="translate(11, 18) scale(0.33)" fill="none" stroke="${s}" stroke-width="2.8">
      <rect x="4" y="10" width="52" height="38" rx="4" fill="#ffffff"/>
      <rect x="10" y="16" width="40" height="24" rx="2" fill="${s}" opacity="0.12"/>
      <rect x="22" y="48" width="16" height="3" rx="1" fill="${s}" opacity="0.35"/>
      <rect x="16" y="52" width="28" height="2" rx="1" fill="${s}" opacity="0.2"/>
      <rect x="68" y="6" width="28" height="46" rx="5" fill="#ffffff"/>
      <rect x="72" y="12" width="20" height="32" rx="2" fill="${s}" opacity="0.12"/>
      <circle cx="80" cy="48" r="2" fill="${s}" opacity="0.35"/>
    </g>
  </svg>`;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}
