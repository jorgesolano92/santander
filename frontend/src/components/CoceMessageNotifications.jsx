import { useCallback, useEffect, useState } from "react";
import { faBell, faTriangleExclamation, faXmark } from "@fortawesome/free-solid-svg-icons";
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

  const unread = messages.filter((m) => !m.seenAt).length;

  function openHistory() {
    setOpen(true);
    setToast(null);
    setMessages((prev) =>
      prev.map((m) => (m.seenAt ? m : { ...m, seenAt: new Date().toISOString() })),
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={openHistory}
        title="Mensajes COCE"
        style={{
          position: "relative",
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          border: "1px solid rgba(255,255,255,0.35)",
          background: "rgba(255,255,255,0.12)",
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
            {toast.urgent ? (
              <FontAwesomeIcon icon={faTriangleExclamation} style={{ color: "#B91C1C", marginTop: 2 }} />
            ) : null}
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

      {open ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15,23,42,0.45)",
            zIndex: 2100,
            display: "grid",
            placeItems: "center",
            padding: 20,
          }}
          onClick={() => setOpen(false)}
        >
          <div
            style={{
              width: "min(720px, 100%)",
              maxHeight: "85vh",
              overflow: "auto",
              background: "#fff",
              borderRadius: 14,
              padding: 18,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 20 }}>Mensajes del COCE</h2>
                <p style={{ margin: "4px 0 0", color: "#64748B", fontSize: 13 }}>
                  Solo lectura · no se puede responder
                </p>
              </div>
              <button type="button" onClick={() => setOpen(false)} style={{ border: "none", background: "transparent", cursor: "pointer" }}>
                <FontAwesomeIcon icon={faXmark} size="lg" />
              </button>
            </div>
            <div style={{ display: "grid", gap: 10, marginTop: 16 }}>
              {messages.length === 0 ? (
                <p style={{ color: "#64748B", textAlign: "center", padding: "24px 0" }}>
                  No hay mensajes recibidos.
                </p>
              ) : (
                messages.map((msg) => (
                  <article
                    key={msg.id}
                    style={{
                      border: msg.urgent ? "1px solid #DC2626" : "1px solid #E2E8F0",
                      background: msg.urgent ? "#FEF2F2" : "#F8FAFC",
                      borderRadius: 10,
                      padding: 12,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {msg.urgent ? (
                        <FontAwesomeIcon icon={faTriangleExclamation} style={{ color: "#B91C1C" }} />
                      ) : null}
                      <strong style={{ color: msg.urgent ? "#991B1B" : "#0F172A" }}>{msg.title}</strong>
                    </div>
                    <p style={{ margin: "8px 0 0", color: "#334155", whiteSpace: "pre-wrap" }}>{msg.body}</p>
                    <small style={{ color: "#64748B" }}>{formatWhen(msg.receivedAt)}</small>
                  </article>
                ))
              )}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
