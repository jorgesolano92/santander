/**
 * Gestión de tablets autorizadas por Android ID.
 */
import { useEffect, useState } from "react";

const btnPrimary = {
  padding: "8px 14px",
  borderRadius: 8,
  border: "1px solid #1e3a5f",
  background: "#1e3a5f",
  color: "#fff",
  cursor: "pointer",
  fontFamily: "inherit",
  fontSize: 13,
};

const btnSecondary = {
  padding: "8px 14px",
  borderRadius: 8,
  border: "1px solid #d1d5db",
  background: "#fff",
  color: "#111",
  cursor: "pointer",
  fontFamily: "inherit",
  fontSize: 13,
};

const inputStyle = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 8,
  border: "1px solid #d1d5db",
  fontFamily: "inherit",
  fontSize: 13,
  boxSizing: "border-box",
};

function formatWhen(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function AuthorizedTabletsSection({ apiFetch, onNotify }) {
      const [items, setItems] = useState([]);
  const [enforcement, setEnforcement] = useState(false);
  const [loading, setLoading] = useState(true);
  const [androidId, setAndroidId] = useState("");
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/api/config/authorized-tablets");
      setItems(Array.isArray(data?.items) ? data.items : []);
      setEnforcement(!!data?.settings?.enforcement_enabled);
    } catch (e) {
      onNotify?.("Error", "No se pudo cargar tablets autorizadas: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const toggleEnforcement = async (next) => {
    try {
      const res = await apiFetch("/api/config/authorized-tablets/settings", {
        method: "PUT",
        body: JSON.stringify({ enforcement_enabled: next }),
      });
      setEnforcement(!!res?.enforcement_enabled);
      onNotify?.(
        "OK",
        next
          ? "Solo las tablets de la lista podrán usarse"
          : "Autorización desactivada: cualquier tablet puede usarse"
      );
    } catch (e) {
      onNotify?.("Error", e.message);
    }
  };

  const add = async () => {
    const id = androidId.trim();
    if (!id) {
      onNotify?.("Error", "Indica el Android ID de la tablet");
      return;
    }
    setSaving(true);
    try {
      await apiFetch("/api/config/authorized-tablets", {
        method: "POST",
        body: JSON.stringify({ android_id: id, label: label.trim() }),
      });
      setAndroidId("");
      setLabel("");
      onNotify?.("OK", "Tablet autorizada");
      await load();
    } catch (e) {
      onNotify?.("Error", e.message);
    } finally {
      setSaving(false);
    }
  };

  const setEnabled = async (id, enabled) => {
    try {
      await apiFetch(`/api/config/authorized-tablets/${id}`, {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      });
      await load();
    } catch (e) {
      onNotify?.("Error", e.message);
    }
  };

  const rename = async (id, currentLabel) => {
    const next = window.prompt("Nombre / ubicación de la tablet", currentLabel || "");
    if (next == null) return;
    try {
      await apiFetch(`/api/config/authorized-tablets/${id}`, {
        method: "PUT",
        body: JSON.stringify({ label: next }),
      });
      await load();
    } catch (e) {
      onNotify?.("Error", e.message);
    }
  };

  const remove = async (id, aid) => {
    if (!window.confirm(`¿Quitar autorización de ${aid}?`)) return;
    try {
      await apiFetch(`/api/config/authorized-tablets/${id}`, { method: "DELETE" });
      onNotify?.("OK", "Tablet eliminada de la lista");
      await load();
    } catch (e) {
      onNotify?.("Error", e.message);
    }
  };

  if (loading) {
    return <div style={{ color: "#6b7280" }}>Cargando tablets autorizadas…</div>;
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <p style={{ margin: 0, color: "#64748b", fontSize: 13, lineHeight: 1.45 }}>
        Autoriza tablets por <strong>Android ID</strong> (no por MAC: Android ya no la expone).
        La tablet muestra su ID abajo; cópialo aquí para autorizarla. Sin autorización no podrá
        usar la app.
      </p>

      <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14 }}>
        <input
          type="checkbox"
          checked={enforcement}
          onChange={(e) => void toggleEnforcement(e.target.checked)}
        />
        <span>Exigir autorización (solo tablets de esta lista)</span>
      </label>

      {!enforcement && (
        <div
          style={{
            background: "#fff7ed",
            border: "1px solid #fdba74",
            borderRadius: 8,
            padding: "10px 12px",
            fontSize: 13,
            color: "#9a3412",
          }}
        >
          La exigencia está desactivada: cualquier tablet con la app podrá usarse.
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(180px, 1.2fr) minmax(140px, 1fr) auto",
          gap: 8,
          alignItems: "end",
        }}
      >
        <div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Android ID</div>
          <input
            style={inputStyle}
            placeholder="ej. 9f3c1b83d54ae28d"
            value={androidId}
            onChange={(e) => setAndroidId(e.target.value)}
            spellCheck={false}
          />
        </div>
        <div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Nombre (opcional)</div>
          <input
            style={inputStyle}
            placeholder="Caja 1 / Recepción"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </div>
        <button type="button" style={btnPrimary} disabled={saving} onClick={() => void add()}>
          Autorizar
        </button>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>
          {items.length} tablet{items.length === 1 ? "" : "s"} en la lista
        </div>
        <button type="button" style={btnSecondary} onClick={() => void load()}>
          Recargar
        </button>
      </div>

      {items.length === 0 ? (
        <div style={{ color: "#6b7280", fontSize: 13 }}>
          Ninguna tablet registrada. Abre la app en el dispositivo, copia el ID de la parte inferior
          y autorízalo aquí.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb", color: "#6b7280" }}>
                <th style={{ padding: "8px 6px" }}>Nombre</th>
                <th style={{ padding: "8px 6px" }}>Android ID</th>
                <th style={{ padding: "8px 6px" }}>Estado</th>
                <th style={{ padding: "8px 6px" }}>Último visto</th>
                <th style={{ padding: "8px 6px" }} />
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                  <td style={{ padding: "10px 6px" }}>
                    <button
                      type="button"
                      onClick={() => void rename(t.id, t.label)}
                      style={{
                        background: "none",
                        border: "none",
                        padding: 0,
                        cursor: "pointer",
                        fontFamily: "inherit",
                        fontSize: 13,
                        color: "#1e3a5f",
                        textDecoration: "underline",
                      }}
                    >
                      {t.label || "(sin nombre)"}
                    </button>
                  </td>
                  <td style={{ padding: "10px 6px", fontFamily: "ui-monospace, monospace" }}>
                    {t.android_id}
                  </td>
                  <td style={{ padding: "10px 6px" }}>
                    <span
                      style={{
                        color: t.enabled ? "#166534" : "#991b1b",
                        fontWeight: 600,
                      }}
                    >
                      {t.enabled ? "Activa" : "Desactivada"}
                    </span>
                  </td>
                  <td style={{ padding: "10px 6px", color: "#6b7280" }}>
                    {formatWhen(t.last_seen_at)}
                  </td>
                  <td style={{ padding: "10px 6px", whiteSpace: "nowrap" }}>
                    <button
                      type="button"
                      style={{ ...btnSecondary, marginRight: 6 }}
                      onClick={() => void setEnabled(t.id, !t.enabled)}
                    >
                      {t.enabled ? "Desactivar" : "Activar"}
                    </button>
                    <button type="button" style={btnSecondary} onClick={() => void remove(t.id, t.android_id)}>
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
