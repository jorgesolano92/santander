/** Token JWT del panel (sistema), distinto de la API tablet. */
export const PANEL_TOKEN_KEY = "panel_access_token";

export function getPanelToken() {
  return localStorage.getItem(PANEL_TOKEN_KEY);
}

export function setPanelToken(token) {
  localStorage.setItem(PANEL_TOKEN_KEY, token);
}

export function clearPanelToken() {
  localStorage.removeItem(PANEL_TOKEN_KEY);
}

/** URL WebSocket panel en vivo (misma base que /api/panel). */
export function getPanelWsLiveUrl() {
  const token = getPanelToken();
  if (!token) return null;
  const proxy = import.meta.env.VITE_API_PROXY_TARGET?.trim();
  let host = window.location.host;
  let proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  if (import.meta.env.DEV && proxy) {
    try {
      const u = new URL(proxy);
      host = u.host;
      proto = u.protocol === "https:" ? "wss:" : "ws:";
    } catch {
      /* usar host del navegador + proxy Vite */
    }
  }
  return `${proto}//${host}/api/panel/ws/live?token=${encodeURIComponent(token)}`;
}
