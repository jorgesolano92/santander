import type {
  PanelBoardState,
  PanelModeRule,
  PanelModuleConfig,
  Sucursal,
  SucursalEstado,
} from '../types';

const TOKEN_KEY = 'coce_api_token';

export function getCoceApiBase(): string {
  const base = (import.meta.env.VITE_COCE_API_URL as string | undefined)?.trim();
  if (base) return base.replace(/\/$/, '');
  return '';
}

export function getCoceToken(): string | null {
  const local = localStorage.getItem(TOKEN_KEY);
  if (local) return local;
  const session = sessionStorage.getItem(TOKEN_KEY);
  if (session) {
    // Migración transparente para evitar re-login al abrir nuevas pestañas.
    localStorage.setItem(TOKEN_KEY, session);
    return session;
  }
  return null;
}

export function setCoceToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearCoceToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
}

async function readError(res: Response): Promise<string> {
  const t = await res.text();
  try {
    const j = JSON.parse(t) as { detail?: unknown };
    if (typeof j.detail === 'string') return j.detail;
    if (j.detail && typeof j.detail === 'object') return JSON.stringify(j.detail);
  } catch {
    /* ignore */
  }
  return t || res.statusText;
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const base = getCoceApiBase();
  if (!base) throw new Error('Define VITE_COCE_API_URL (ej. http://localhost:9000)');
  const token = getCoceToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  return fetch(`${base}${path}`, { ...init, headers });
}

export async function coceLogin(username: string, password: string): Promise<string> {
  const res = await apiFetch('/api/coce/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { access_token: string };
  if (!data.access_token) throw new Error('Respuesta sin access_token');
  setCoceToken(data.access_token);
  return data.access_token;
}

export async function coceRegister(
  username: string,
  password: string,
  setupToken?: string,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (setupToken?.trim()) headers['X-Coce-Setup-Token'] = setupToken.trim();
  const res = await fetch(`${getCoceApiBase()}/api/coce/auth/register`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(await readError(res));
}

export type CoceSetupStatus = {
  hasUsers: boolean;
  allowRegister: boolean;
  requiresSetupToken: boolean;
};

export async function fetchCoceSetupStatus(): Promise<CoceSetupStatus> {
  const base = getCoceApiBase();
  if (!base) throw new Error('Define VITE_COCE_API_URL');
  const res = await fetch(`${base}/api/coce/auth/setup-status`);
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as CoceSetupStatus;
}

export async function coceMe(): Promise<{ username: string }> {
  const res = await apiFetch('/api/coce/auth/me');
  if (res.status === 401) throw new Error('SESSION_EXPIRED');
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as { username: string };
}

export type BranchApi = {
  id: string;
  nombre: string;
  host: string;
  port: number;
  useHttps: boolean;
  usuarioTablet: string;
  hasPasswordTablet?: boolean;
  usuarioPanel?: string | null;
  hasPasswordPanel?: boolean;
  estado?: SucursalEstado;
};

export function branchToSucursal(b: BranchApi): Sucursal {
  return {
    id: b.id,
    nombre: b.nombre,
    host: b.host,
    port: b.port,
    useHttps: b.useHttps,
    usuarioTablet: b.usuarioTablet,
    usuarioPanel: b.usuarioPanel ?? undefined,
    hasPasswordPanel: b.hasPasswordPanel,
    estado: b.estado,
  };
}

export async function listBranches(): Promise<Sucursal[]> {
  const res = await apiFetch('/api/coce/branches');
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { branches?: BranchApi[] };
  return (data.branches ?? []).map(branchToSucursal);
}

export async function getBranch(id: string): Promise<BranchApi> {
  const res = await apiFetch(`/api/coce/branches/${id}`);
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as BranchApi;
}

export type BranchPayload = {
  nombre: string;
  host: string;
  port: number;
  useHttps: boolean;
  usuarioTablet: string;
  passwordTablet?: string;
  usuarioPanel?: string;
  passwordPanel?: string;
  estado?: SucursalEstado;
};

export type BranchCreateResult = BranchApi & { ingestToken?: string };

export async function createBranch(payload: BranchPayload): Promise<BranchCreateResult> {
  const res = await apiFetch('/api/coce/branches', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as BranchCreateResult;
}

export async function updateBranch(id: string, payload: BranchPayload): Promise<BranchApi> {
  const res = await apiFetch(`/api/coce/branches/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as BranchApi;
}

export async function deleteBranch(id: string): Promise<void> {
  const res = await apiFetch(`/api/coce/branches/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await readError(res));
}

export type BranchLocation = {
  address: string;
  latitude: number | null;
  longitude: number | null;
  captured_at?: string | null;
  currentMode?: string | null;
  modeLabel?: string | null;
  modeColor?: string | null;
  openingHours?: string | null;
  schedulesEnabled?: boolean | null;
};

export type BranchSnapshot = {
  branchId: string;
  baseUrl: string;
  modes: PanelModeRule[];
  currentMode: string | null;
  boards: Record<string, PanelBoardState & Record<string, unknown>>;
  modulesConfig?: PanelModuleConfig[];
  panelTimestamp?: string | null;
  panelOk: boolean;
  panelError: string | null;
  location?: BranchLocation;
};

function mapBranchLocation(raw: Record<string, unknown> | BranchLocation): BranchLocation {
  return {
    address: String(raw.address ?? '').trim(),
    latitude: raw.latitude == null || raw.latitude === '' ? null : Number(raw.latitude),
    longitude: raw.longitude == null || raw.longitude === '' ? null : Number(raw.longitude),
    captured_at: (raw.captured_at as string | null | undefined) ?? null,
    currentMode:
      (raw as BranchLocation).currentMode ??
      (raw.current_mode as string | null | undefined) ??
      null,
    modeLabel:
      (raw as BranchLocation).modeLabel ??
      (raw.mode_label as string | null | undefined) ??
      null,
    modeColor:
      (raw as BranchLocation).modeColor ??
      (raw.mode_color as string | null | undefined) ??
      null,
    openingHours:
      (raw as BranchLocation).openingHours ??
      (raw.opening_hours as string | null | undefined) ??
      null,
    schedulesEnabled:
      (raw as BranchLocation).schedulesEnabled ??
      (typeof raw.schedules_enabled === 'boolean' ? raw.schedules_enabled : null),
  };
}

export async function fetchBranchLocation(branchId: string): Promise<BranchLocation> {
  const res = await apiFetch(`/api/coce/branches/${branchId}/location`);
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { location?: Record<string, unknown> };
  return mapBranchLocation(
    data.location ?? {
      address: '',
      latitude: null,
      longitude: null,
    },
  );
}

export async function fetchBranchSnapshot(
  branchId: string,
  options?: { refreshHardware?: boolean },
): Promise<BranchSnapshot> {
  const q =
    options?.refreshHardware === true ? '?refresh_hardware=true' : '';
  const res = await apiFetch(`/api/coce/branches/${branchId}/snapshot${q}`);
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as BranchSnapshot;
}

/** Solo /api/panel/status vía proxy (rápido, como ETD8A12Panel local). */
export async function fetchBranchPanelStatus(
  branchId: string,
  options?: { refreshHardware?: boolean },
): Promise<Pick<
  BranchSnapshot,
  'boards' | 'modulesConfig' | 'currentMode' | 'panelTimestamp' | 'panelOk' | 'panelError'
>> {
  const q =
    options?.refreshHardware === true ? '?refresh_hardware=true' : '';
  const res = await apiFetch(`/api/coce/branches/${branchId}/panel-status${q}`);
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as BranchSnapshot;
  return data;
}

export async function panelConnectBoard(branchId: string, boardId: number): Promise<void> {
  const res = await apiFetch(`/api/coce/branches/${branchId}/panel/boards/${boardId}/connect`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(await readError(res));
}

export async function panelDisconnectBoard(branchId: string, boardId: number): Promise<void> {
  const res = await apiFetch(`/api/coce/branches/${branchId}/panel/boards/${boardId}/disconnect`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(await readError(res));
}

export async function panelSetOutput(
  branchId: string,
  boardId: number,
  channel: number,
  state: boolean,
): Promise<void> {
  const res = await apiFetch(`/api/coce/branches/${branchId}/panel/boards/${boardId}/output`, {
    method: 'POST',
    body: JSON.stringify({ channel, state }),
  });
  if (!res.ok) throw new Error(await readError(res));
}

export async function panelSetInputOverride(
  branchId: string,
  boardId: number,
  channel: number,
  state: boolean | null,
): Promise<void> {
  const res = await apiFetch(
    `/api/coce/branches/${branchId}/panel/boards/${boardId}/input-override`,
    {
      method: 'POST',
      body: JSON.stringify({ channel, state }),
    },
  );
  if (!res.ok) throw new Error(await readError(res));
}

export async function setBranchMode(
  branchId: string,
  ruleKey: string,
  active = true,
): Promise<void> {
  const res = await apiFetch(`/api/coce/branches/${branchId}/set-mode`, {
    method: 'POST',
    body: JSON.stringify({ rule_key: ruleKey, active }),
  });
  if (!res.ok) throw new Error(await readError(res));
}

export type AuditLog = {
  id: number;
  createdAt: string;
  actorUsername: string;
  action: string;
  branchId: string | null;
  branchNombre: string | null;
  success: boolean;
  detail: Record<string, unknown> | null;
  ipAddress: string | null;
};

export async function listAuditLogs(params?: {
  limit?: number;
  branchId?: string;
  action?: string;
}): Promise<AuditLog[]> {
  const q = new URLSearchParams();
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.branchId) q.set('branch_id', params.branchId);
  if (params?.action) q.set('action', params.action);
  const qs = q.toString();
  const res = await apiFetch(`/api/coce/audit${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { logs?: AuditLog[] };
  return data.logs ?? [];
}
