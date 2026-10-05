/** Estado de monitorización en el COCE (maqueta / futuro tiempo real). */
export type SucursalEstado = 'operativo' | 'no_operativo' | 'apagado';

/** Registro local de una sucursal (sistema local en oficina). */
export type Sucursal = {
  id: string;
  nombre: string;
  /** IP o hostname, sin protocolo */
  host: string;
  /** Puerto del API FastAPI (p. ej. 8000) */
  port: number;
  useHttps: boolean;
  /** Usuario API tableta v1 (`/api/v1/*`) */
  usuarioTablet: string;
  /** Solo en formulario alta; en listado viene del servidor sin contraseña */
  passwordTablet?: string;
  /** Opcional: usuario panel web para JWT y `/api/panel/status` (placas) */
  usuarioPanel?: string;
  /** Solo en formulario; en API central viene `hasPasswordPanel` */
  passwordPanel?: string;
  hasPasswordPanel?: boolean;
  /** Por defecto operativo si no está definido */
  estado?: SucursalEstado;
};

export type PanelModeRule = {
  key: string;
  enabled: boolean;
  type?: string;
  auto_execute?: boolean;
};

export type PanelChannelConfig = {
  channel_name?: string | null;
  id?: number;
};

export type PanelModuleConfig = {
  id: number;
  name?: string;
  inputs?: PanelChannelConfig[];
  outputs?: PanelChannelConfig[];
};

export type PanelBoardState = {
  id: number;
  connected?: boolean;
  config?: {
    name?: string;
    host?: string;
    port?: number;
    slave_id?: number;
  };
  inputs?: boolean[];
  inputs_raw?: boolean[];
  outputs?: boolean[];
  input_overrides?: Array<boolean | null>;
};
