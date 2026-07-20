import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { getCoceApiBase, getCoceToken } from '../api/coceClient';
import type { SucursalEstado } from '../types';
import { parseBranchAlerts, type BranchAlertsMap } from '../utils/branchAlerts';

export type LiveBranchInfo = {
  installationId: string;
  nombre: string;
  status: SucursalEstado;
  currentMode?: string | null;
  activeToggleRules?: string[];
  alerts?: BranchAlertsMap;
  wsConnected?: boolean;
  modbus?: boolean;
  boardsConnected?: number;
  boardsTotal?: number;
  lastEventTs?: number | null;
  lastMessage?: { type: string; payload: Record<string, unknown> };
};

type CoceLiveContextValue = {
  connected: boolean;
  getLiveStatus: (installationId: string) => SucursalEstado | undefined;
  getLiveBranch: (installationId: string) => LiveBranchInfo | undefined;
  getAllLiveBranches: () => LiveBranchInfo[];
};

const CoceLiveContext = createContext<CoceLiveContextValue | null>(null);

function wsLiveUrl(): string | null {
  const base = getCoceApiBase();
  const token = getCoceToken();
  if (!base || !token) return null;
  const wsBase = base.replace(/^http/i, (m) => (m.toLowerCase() === 'https' ? 'wss' : 'ws'));
  return `${wsBase}/api/coce/ws/live?token=${encodeURIComponent(token)}`;
}

function parseBranch(raw: Record<string, unknown>): LiveBranchInfo {
  const status = (raw.status as SucursalEstado) || 'apagado';
  const partial = (raw.partial as Record<string, unknown> | null) ?? {};
  const activeToggleRules = Array.isArray(partial.active_toggle_rules)
    ? partial.active_toggle_rules.map(String)
    : [];
  return {
    installationId: String(raw.installationId ?? ''),
    nombre: String(raw.nombre ?? ''),
    status,
    currentMode: (raw.currentMode as string | null) ?? null,
    activeToggleRules,
    alerts: parseBranchAlerts(partial.alerts),
    wsConnected: Boolean(raw.wsConnected),
    modbus: Boolean(raw.modbus),
    boardsConnected: Number(raw.boardsConnected ?? 0),
    boardsTotal: Number(raw.boardsTotal ?? 0),
    lastEventTs:
      raw.lastEventTs != null ? Number(raw.lastEventTs) : null,
  };
}

export function CoceLiveProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false);
  const [branches, setBranches] = useState<Record<string, LiveBranchInfo>>({});

  useEffect(() => {
    const url = wsLiveUrl();
    if (!url) return;

    let ws: WebSocket | null = null;
    let pingTimer: ReturnType<typeof setInterval> | undefined;
    let closed = false;

    function connect() {
      ws = new WebSocket(url!);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) {
          window.setTimeout(connect, 4000);
        }
      };
      ws.onerror = () => setConnected(false);
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(String(ev.data)) as {
            type?: string;
            installationId?: string;
            status?: SucursalEstado;
            branch?: Record<string, unknown>;
            branches?: Record<string, unknown>[];
            message?: { type?: string; payload?: Record<string, unknown> };
          };
          if (data.type === 'live_snapshot' && Array.isArray(data.branches)) {
            const next: Record<string, LiveBranchInfo> = {};
            for (const b of data.branches) {
              const info = parseBranch(b);
              if (info.installationId) next[info.installationId] = info;
            }
            setBranches(next);
            return;
          }
          if (data.type === 'branch_update' && data.branch) {
            const info = parseBranch(data.branch);
            if (!info.installationId) return;
            if (data.message?.type) {
              info.lastMessage = {
                type: data.message.type,
                payload: data.message.payload ?? {},
              };
            }
            setBranches((prev) => ({ ...prev, [info.installationId]: info }));
          }
        } catch {
          /* ignore malformed */
        }
      };
    }

    connect();
    pingTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send('ping');
    }, 25000);

    return () => {
      closed = true;
      clearInterval(pingTimer);
      ws?.close();
    };
  }, []);

  const getLiveStatus = useCallback(
    (installationId: string) => branches[installationId]?.status,
    [branches],
  );

  const getLiveBranch = useCallback(
    (installationId: string) => branches[installationId],
    [branches],
  );

  const getAllLiveBranches = useCallback(
    () => Object.values(branches),
    [branches],
  );

  const value = useMemo(
    () => ({ connected, getLiveStatus, getLiveBranch, getAllLiveBranches }),
    [connected, getLiveStatus, getLiveBranch, getAllLiveBranches],
  );

  return <CoceLiveContext.Provider value={value}>{children}</CoceLiveContext.Provider>;
}

export function useCoceLive(): CoceLiveContextValue {
  const ctx = useContext(CoceLiveContext);
  if (!ctx) {
    return {
      connected: false,
      getLiveStatus: () => undefined,
      getLiveBranch: () => undefined,
      getAllLiveBranches: () => [],
    };
  }
  return ctx;
}

/** Estado en tarjeta: live si hay WS; si no, manual de BD. */
export function resolveSucursalEstado(
  installationId: string,
  manual: SucursalEstado | undefined,
  live: CoceLiveContextValue,
): SucursalEstado {
  if (live.connected) {
    const s = live.getLiveStatus(installationId);
    if (s) return s;
    return 'apagado';
  }
  return manual ?? 'operativo';
}
