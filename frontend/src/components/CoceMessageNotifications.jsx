import { useCallback, useEffect, useRef, useState } from "react";
import {
  faBell,
  faEnvelope,
  faTriangleExclamation,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";

function formatWhen(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function normalizeMessage(raw) {
  if (!raw?.id || !raw?.title) return null;
  return {
    id: String(raw.id),
    title: String(raw.title),
    body: String(raw.body || ""),
    urgent: Boolean(raw.urgent),
    receivedAt: String(raw.received_at || raw.receivedAt || new Date().toISOString()),
    seenAt: raw.seenAt || null,
  };
}

export function CoceMessageNotifications({ apiFetch, wsEvent }) {
  const [messages, setMessages] = useState([]);
  const [toast, setToast] = useState(null);
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  const mergeMessage = useCallback((incoming) => {
    const msg = normalizeMessage(incoming);
    if (!msg) return;
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === msg.id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = { ...msg, seenAt: next[idx].seenAt };
        return next;
      }
      return [msg, ...prev].slice(0, 200);
    });
    setToast(msg);
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const data = await apiFetch("/coce-messages?limit=100");
      const rows = Array.isArray(data?.messages) ? data.messages : [];
      setMessages((prev) => {
        const seen = new Map(prev.map((m) => [m.id, m.seenAt]));
        return rows
          .map((row) =>
            normalizeMessage({
              ...row,
              seenAt: seen.get(row.id) || null,
            }),
          )
          .filter(Boolean);
      });
    } catch {
      /* ignore */
    }
  }, [apiFetch]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (!wsEvent?.id) return;
    mergeMessage(wsEvent);
  }, [wsEvent, mergeMessage]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 12000);
    return () => window.clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event) => {
      if (rootRef.current?.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const unread = messages.filter((m) => !m.seenAt).length;

  function togglePanel() {
    setOpen((wasOpen) => {
      const next = !wasOpen;
      if (next) {
        setToast(null);
        setMessages((prev) =>
          prev.map((m) => (m.seenAt ? m : { ...m, seenAt: new Date().toISOString() })),
        );
      }
      return next;
    });
  }

  return (
    <>
      <div ref={rootRef} style={{ position: "relative" }}>
        <button
          type="button"
          onClick={togglePanel}
          title="Mensajes COCE"
          aria-expanded={open}
          aria-haspopup="true"
          style={{
            position: "relative",
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            border: "1px solid rgba(255,255,255,0.35)",
            background: open ? "rgba(255,255,255,0.22)" : "rgba(255,255,255,0.12)",
            color: "#fff",
            borderRadius: 8,
            padding: "8px 12px",
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          <FontAwesomeIcon icon={faBell} />
          Mensajes COCE
          {unread > 0 ? (
            <span
              style={{
                minWidth: 20,
                height: 20,
                borderRadius: 999,
                background: "#fff",
                color: "#B20710",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 11,
                fontWeight: 700,
                padding: "0 6px",
              }}
            >
              {unread > 99 ? "99+" : unread}
            </span>
          ) : null}
        </button>

        {open ? (
          <div
            role="dialog"
            aria-label="Notificaciones COCE"
            style={{
              position: "absolute",
              top: "calc(100% + 8px)",
              right: 0,
              width: 350,
              height: 350,
              zIndex: 2100,
              background: "#fff",
              color: "#0F172A",
              borderRadius: 16,
              border: "1px solid #E2E8F0",
              boxShadow: "0 12px 32px rgba(15,23,42,0.18)",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                flexShrink: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
                padding: "12px 14px",
                borderBottom: "1px solid #E2E8F0",
                background: "#F8FAFC",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                <span
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: 8,
                    background: "#DBEAFE",
                    color: "#1D4ED8",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  <FontAwesomeIcon icon={faBell} />
                </span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, lineHeight: 1.2 }}>
                    Notificaciones
                  </div>
                  <div style={{ fontSize: 11, color: "#64748B" }}>Solo lectura</div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                title="Cerrar"
                style={{
                  border: "none",
                  background: "transparent",
                  cursor: "pointer",
                  color: "#64748B",
                  padding: 4,
                }}
              >
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>

            <div
              style={{
                flex: 1,
                minHeight: 0,
                overflowY: "auto",
                padding: 10,
              }}
            >
              {messages.length === 0 ? (
                <div
                  style={{
                    height: "100%",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 8,
                    color: "#64748B",
                    textAlign: "center",
                    padding: 16,
                  }}
                >
                  <FontAwesomeIcon icon={faBell} style={{ fontSize: 28, opacity: 0.35 }} />
                  <p style={{ margin: 0, fontSize: 13 }}>No hay mensajes recibidos.</p>
                </div>
              ) : (
                <div style={{ display: "grid", gap: 8 }}>
                  {messages.map((msg) => {
                    const icon = msg.urgent ? faTriangleExclamation : faEnvelope;
                    const iconBg = msg.urgent ? "#FEE2E2" : "#DBEAFE";
                    const iconColor = msg.urgent ? "#B91C1C" : "#1D4ED8";
                    return (
                      <article
                        key={msg.id}
                        style={{
                          border: msg.urgent ? "1px solid #FECACA" : "1px solid #E2E8F0",
                          background: msg.urgent ? "#FEF2F2" : "#FFFFFF",
                          borderRadius: 10,
                          padding: 10,
                        }}
                      >
                        <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                          <span
                            style={{
                              width: 30,
                              height: 30,
                              borderRadius: 8,
                              background: iconBg,
                              color: iconColor,
                              display: "inline-flex",
                              alignItems: "center",
                              justifyContent: "center",
                              flexShrink: 0,
                              marginTop: 1,
                            }}
                          >
                            <FontAwesomeIcon icon={icon} />
                          </span>
                          <div style={{ minWidth: 0, flex: 1 }}>
                            <strong
                              style={{
                                display: "block",
                                fontSize: 13,
                                color: msg.urgent ? "#991B1B" : "#0F172A",
                                lineHeight: 1.3,
                              }}
                            >
                              {msg.title}
                            </strong>
                            {msg.body ? (
                              <p
                                style={{
                                  margin: "4px 0 0",
                                  color: "#334155",
                                  fontSize: 12,
                                  lineHeight: 1.4,
                                  whiteSpace: "pre-wrap",
                                  wordBreak: "break-word",
                                }}
                              >
                                {msg.body}
                              </p>
                            ) : null}
                            <small style={{ color: "#64748B", fontSize: 10 }}>
                              {formatWhen(msg.receivedAt)}
                            </small>
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>

      {toast ? (
        <div
          role="alert"
          style={{
            position: "fixed",
            right: 20,
            bottom: 24,
            width: 360,
            maxWidth: "92vw",
            zIndex: 2000,
            borderRadius: 12,
            border: toast.urgent ? "2px solid #DC2626" : "2px solid #CBD5E1",
            background: toast.urgent ? "#FEF2F2" : "#FFFFFF",
            boxShadow: "0 8px 24px rgba(15,23,42,0.18)",
            padding: 14,
          }}
        >
          <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
            <span
              style={{
                width: 28,
                height: 28,
                borderRadius: 8,
                background: toast.urgent ? "#FEE2E2" : "#DBEAFE",
                color: toast.urgent ? "#B91C1C" : "#1D4ED8",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <FontAwesomeIcon
                icon={toast.urgent ? faTriangleExclamation : faEnvelope}
              />
            </span>
            <div style={{ flex: 1 }}>
              <strong style={{ color: toast.urgent ? "#991B1B" : "#0F172A", display: "block" }}>
                {toast.title}
              </strong>
              <p style={{ margin: "6px 0 0", color: "#334155", fontSize: 13, lineHeight: 1.45 }}>
                {toast.body}
              </p>
              {toast.urgent ? (
                <small style={{ color: "#B91C1C", fontWeight: 700 }}>Mensaje urgente del COCE</small>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => setToast(null)}
              style={{ border: "none", background: "transparent", cursor: "pointer", color: "#64748B" }}
            >
              <FontAwesomeIcon icon={faXmark} />
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
