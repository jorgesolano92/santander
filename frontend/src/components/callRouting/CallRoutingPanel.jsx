import { useEffect, useMemo, useState } from "react";

const ACTION_OPTIONS = [
  { value: "call", label: "Llamar tablet" },
  { value: "open", label: "Abrir" },
  { value: "ignore", label: "Ignorar" },
];

const PULSADOR_LABELS = {
  p1: "P1",
  p2: "P2",
  p3: "P3",
  p4: "P4",
};

const card = {
  background: "#fff",
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  padding: 16,
};

const btnPrimary = {
  padding: "8px 14px",
  borderRadius: 8,
  border: "none",
  background: "#1d4ed8",
  color: "#fff",
  fontWeight: 600,
  cursor: "pointer",
  fontSize: 13,
};

const btnSecondary = {
  padding: "8px 14px",
  borderRadius: 8,
  border: "1px solid #d1d5db",
  background: "#fff",
  color: "#374151",
  fontWeight: 600,
  cursor: "pointer",
  fontSize: 13,
};

function modeLabel(key) {
  return String(key || "")
    .replace(/^horario_/, "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function cloneOverrides(raw) {
  const out = {};
  if (!raw || typeof raw !== "object") return out;
  for (const [mode, mapping] of Object.entries(raw)) {
    if (!mapping || typeof mapping !== "object") continue;
    out[mode] = { ...mapping };
  }
  return out;
}

export default function CallRoutingPanel({ apiFetch, onNotify }) {
  const [defaults, setDefaults] = useState({});
  const [overrides, setOverrides] = useState({});
  const [pulsadores, setPulsadores] = useState(["p1", "p2", "p3", "p4"]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const modes = useMemo(() => {
    const keys = new Set([
      ...Object.keys(defaults || {}),
      ...Object.keys(overrides || {}),
    ]);
    return Array.from(keys).sort();
  }, [defaults, overrides]);

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/call-routing");
      setDefaults(data?.defaults || {});
      setOverrides(cloneOverrides(data?.overrides));
      if (Array.isArray(data?.pulsadores) && data.pulsadores.length) {
        setPulsadores(data.pulsadores);
      }
    } catch (e) {
      onNotify?.("Error", "No se pudo cargar el enrutado: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const effectiveAction = (mode, pulsador) => {
    const ov = overrides?.[mode]?.[pulsador];
    if (ov) return ov;
    return defaults?.[mode]?.[pulsador] || "open";
  };

  const isOverridden = (mode, pulsador) =>
    Boolean(overrides?.[mode]?.[pulsador]);

  const setCell = (mode, pulsador, value) => {
    setOverrides((prev) => {
      const next = cloneOverrides(prev);
      const def = defaults?.[mode]?.[pulsador] || "open";
      if (!value || value === "__default__" || value === def) {
        if (next[mode]) {
          delete next[mode][pulsador];
          if (Object.keys(next[mode]).length === 0) delete next[mode];
        }
        return next;
      }
      next[mode] = { ...(next[mode] || {}), [pulsador]: value };
      return next;
    });
  };

  const restoreMode = (mode) => {
    setOverrides((prev) => {
      const next = cloneOverrides(prev);
      delete next[mode];
      return next;
    });
  };

  const restoreAll = () => setOverrides({});

  const save = async () => {
    setSaving(true);
    try {
      const data = await apiFetch("/call-routing", {
        method: "PUT",
        body: JSON.stringify({ overrides }),
      });
      setDefaults(data?.defaults || defaults);
      setOverrides(cloneOverrides(data?.overrides));
      onNotify?.("OK", "Enrutado de pulsaciones guardado");
    } catch (e) {
      onNotify?.("Error", "No se pudo guardar: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 24, color: "#6b7280" }}>Cargando enrutado…</div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 12,
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>
            Enrutado de pulsaciones
          </div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>
            Por defecto se usa el comportamiento histórico de la sucursal. Solo
            se guardan los valores personalizados (override) por modo y
            pulsador.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" onClick={() => void load()} style={btnSecondary}>
            Recargar
          </button>
          <button type="button" onClick={restoreAll} style={btnSecondary}>
            Restaurar todos
          </button>
          <button
            type="button"
            onClick={() => void save()}
            style={btnPrimary}
            disabled={saving}
          >
            {saving ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>

      <div
        style={{
          ...card,
          background: "#eff6ff",
          border: "1px solid #bfdbfe",
          color: "#1e3a8a",
          fontSize: 13,
        }}
      >
        <strong>Llamar tablet</strong> inicia videollamada. <strong>Abrir</strong>{" "}
        sigue la apertura Modbus/interlock del modo. <strong>Ignorar</strong>{" "}
        descarta la pulsación. Las celdas en azul son personalizadas; el resto
        usan el default.
      </div>

      <section style={{ ...card, overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: 13,
            minWidth: 560,
          }}
        >
          <thead>
            <tr>
              <th
                style={{
                  textAlign: "left",
                  padding: "10px 8px",
                  borderBottom: "1px solid #e5e7eb",
                  color: "#6b7280",
                  fontWeight: 600,
                }}
              >
                Modo
              </th>
              {pulsadores.map((p) => (
                <th
                  key={p}
                  style={{
                    textAlign: "center",
                    padding: "10px 8px",
                    borderBottom: "1px solid #e5e7eb",
                    color: "#6b7280",
                    fontWeight: 600,
                  }}
                >
                  {PULSADOR_LABELS[p] || p.toUpperCase()}
                </th>
              ))}
              <th
                style={{
                  textAlign: "right",
                  padding: "10px 8px",
                  borderBottom: "1px solid #e5e7eb",
                  color: "#6b7280",
                  fontWeight: 600,
                }}
              >
                Acciones
              </th>
            </tr>
          </thead>
          <tbody>
            {modes.map((mode) => (
              <tr key={mode}>
                <td
                  style={{
                    padding: "10px 8px",
                    borderBottom: "1px solid #f3f4f6",
                    fontWeight: 600,
                    whiteSpace: "nowrap",
                  }}
                >
                  {modeLabel(mode)}
                </td>
                {pulsadores.map((p) => {
                  const overridden = isOverridden(mode, p);
                  const value = effectiveAction(mode, p);
                  const def = defaults?.[mode]?.[p] || "open";
                  return (
                    <td
                      key={`${mode}-${p}`}
                      style={{
                        padding: "8px",
                        borderBottom: "1px solid #f3f4f6",
                        textAlign: "center",
                        background: overridden ? "#eff6ff" : "transparent",
                      }}
                    >
                      <select
                        value={value}
                        onChange={(e) => setCell(mode, p, e.target.value)}
                        title={
                          overridden
                            ? `Personalizado (default: ${def})`
                            : `Default: ${def}`
                        }
                        style={{
                          width: "100%",
                          maxWidth: 140,
                          padding: "6px 8px",
                          borderRadius: 8,
                          border: overridden
                            ? "1px solid #93c5fd"
                            : "1px solid #d1d5db",
                          background: overridden ? "#dbeafe" : "#fff",
                          fontSize: 12,
                          fontFamily: "inherit",
                        }}
                      >
                        {ACTION_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                            {opt.value === def ? " · def" : ""}
                          </option>
                        ))}
                        {overridden ? (
                          <option value="__default__">Usar default ({def})</option>
                        ) : null}
                      </select>
                    </td>
                  );
                })}
                <td
                  style={{
                    padding: "8px",
                    borderBottom: "1px solid #f3f4f6",
                    textAlign: "right",
                  }}
                >
                  <button
                    type="button"
                    style={{ ...btnSecondary, padding: "6px 10px", fontSize: 12 }}
                    onClick={() => restoreMode(mode)}
                    disabled={!overrides?.[mode]}
                  >
                    Restaurar modo
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
