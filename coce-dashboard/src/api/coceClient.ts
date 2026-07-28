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
  activeToggleRules?: string[];
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

export type CoceOutboundMessage = {
  id: string;
  createdAt: string;
  actorUsername: string;
  title: string;
  body: string;
  urgent: boolean;
  branchId: string;
  branchNombre: string;
  deliveryStatus: 'pending' | 'delivered' | 'offline';
  deliveredAt?: string | null;
};

export async function sendCoceMessage(payload: {
  title: string;
  body: string;
  urgent: boolean;
  branchIds: string[];
  sendToAll: boolean;
}): Promise<CoceOutboundMessage[]> {
  const res = await apiFetch('/api/coce/messages/send', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { messages?: CoceOutboundMessage[] };
  return data.messages ?? [];
}

export async function fetchCoceMessages(params?: {
  limit?: number;
  offset?: number;
  branchId?: string;
  urgent?: boolean;
  deliveryStatus?: 'pending' | 'delivered' | 'offline';
  q?: string;
}): Promise<CoceOutboundMessage[]> {
  const q = new URLSearchParams();
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  if (params?.branchId) q.set('branch_id', params.branchId);
  if (params?.urgent !== undefined) q.set('urgent', params.urgent ? 'true' : 'false');
  if (params?.deliveryStatus) q.set('delivery_status', params.deliveryStatus);
  if (params?.q) q.set('q', params.q);
  const qs = q.toString();
  const res = await apiFetch(`/api/coce/messages${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { messages?: CoceOutboundMessage[] };
  return data.messages ?? [];
}

export type CoceTechnician = {
  dni: string;
  nombre: string;
  apellidos: string;
  empresa: string;
  valido_hasta?: string | null;
  active: boolean;
  updated_at?: string;
};

export async function fetchTechnicians(): Promise<CoceTechnician[]> {
  const res = await apiFetch('/api/coce/technicians');
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { technicians?: CoceTechnician[] };
  return data.technicians ?? [];
}

export async function importTechniciansCsv(file: File): Promise<{
  technicians: CoceTechnician[];
  sync: { delivered: number; offline: number };
}> {
  const base = getCoceApiBase();
  if (!base) throw new Error('Define VITE_COCE_API_URL');
  const token = getCoceToken();
  const body = new FormData();
  body.append('file', file);
  const res = await fetch(`${base}/api/coce/technicians/import`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body,
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as {
    technicians: CoceTechnician[];
    sync: { delivered: number; offline: number };
  };
}

export async function syncTechniciansToBranches(): Promise<{
  delivered: number;
  offline: number;
}> {
  const res = await apiFetch('/api/coce/technicians/sync-branches', { method: 'POST' });
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { sync?: { delivered: number; offline: number } };
  return data.sync ?? { delivered: 0, offline: 0 };
}

export type SoftwareRelease = {
  id: string;
  kind: 'panel' | 'tablet_apk';
  version: string;
  changelog: string;
  sha256: string;
  originalFilename: string;
  source: string;
  createdAt: string;
  createdBy: string;
  downloadPath: string;
};

export type SoftwareDeployment = {
  id: string;
  releaseId: string;
  branchId: string;
  branchNombre: string;
  status: string;
  error?: string | null;
  createdAt: string;
  updatedAt: string;
  version?: string | null;
  kind?: string | null;
  delivered?: boolean;
};

export async function fetchSoftwareReleases(params?: {
  kind?: 'panel' | 'tablet_apk';
  limit?: number;
}): Promise<SoftwareRelease[]> {
  const q = new URLSearchParams();
  if (params?.kind) q.set('kind', params.kind);
  if (params?.limit) q.set('limit', String(params.limit));
  const qs = q.toString();
  const res = await apiFetch(`/api/coce/updates/releases${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { releases?: SoftwareRelease[] };
  return data.releases ?? [];
}

export async function uploadSoftwareRelease(payload: {
  kind: 'panel' | 'tablet_apk';
  version: string;
  changelog?: string;
  file: File;
}): Promise<SoftwareRelease> {
  const base = getCoceApiBase();
  if (!base) throw new Error('Define VITE_COCE_API_URL');
  const token = getCoceToken();
  const body = new FormData();
  body.append('kind', payload.kind);
  body.append('version', payload.version);
  body.append('changelog', payload.changelog || '');
  body.append('file', payload.file);
  const res = await fetch(`${base}/api/coce/updates/releases`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body,
  });
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { release?: SoftwareRelease };
  if (!data.release) throw new Error('Respuesta sin release');
  return data.release;
}

export async function publishPanelFromLocal(payload?: {
  version?: string;
  changelog?: string;
}): Promise<SoftwareRelease> {
  const res = await apiFetch('/api/coce/updates/releases/from-local', {
    method: 'POST',
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { release?: SoftwareRelease };
  if (!data.release) throw new Error('Respuesta sin release');
  return data.release;
}

export async function deploySoftwareRelease(payload: {
  releaseId: string;
  branchIds: string[];
  sendToAll: boolean;
}): Promise<{ release: SoftwareRelease; deployments: SoftwareDeployment[] }> {
  const res = await apiFetch('/api/coce/updates/deploy', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as { release: SoftwareRelease; deployments: SoftwareDeployment[] };
}

export async function fetchSoftwareDeployments(params?: {
  releaseId?: string;
  limit?: number;
}): Promise<SoftwareDeployment[]> {
  const q = new URLSearchParams();
  if (params?.releaseId) q.set('release_id', params.releaseId);
  if (params?.limit) q.set('limit', String(params.limit));
  const qs = q.toString();
  const res = await apiFetch(`/api/coce/updates/deployments${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { deployments?: SoftwareDeployment[] };
  return data.deployments ?? [];
}

export async function deleteSoftwareRelease(releaseId: string): Promise<void> {
  const res = await apiFetch(`/api/coce/updates/releases/${encodeURIComponent(releaseId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(await readError(res));
}

export async function deleteAllSoftwareReleases(): Promise<number> {
  const res = await apiFetch('/api/coce/updates/releases', { method: 'DELETE' });
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { deleted?: number };
  return data.deleted ?? 0;
}

export async function deleteSoftwareDeployment(deploymentId: string): Promise<void> {
  const res = await apiFetch(
    `/api/coce/updates/deployments/${encodeURIComponent(deploymentId)}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error(await readError(res));
}

export async function deleteAllSoftwareDeployments(): Promise<number> {
  const res = await apiFetch('/api/coce/updates/deployments', { method: 'DELETE' });
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { deleted?: number };
  return data.deleted ?? 0;
}
