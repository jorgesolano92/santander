import { useEffect, useMemo, useState } from "react";

const WEEKDAYS = [
  { key: "monday", label: "Lunes" },
  { key: "tuesday", label: "Martes" },
  { key: "wednesday", label: "Miércoles" },
  { key: "thursday", label: "Jueves" },
  { key: "friday", label: "Viernes" },
  { key: "saturday", label: "Sábado" },
  { key: "sunday", label: "Domingo" },
];

const RULE_OPTIONS = [
  { value: "horario_automatico", label: "Automático" },
  { value: "horario_esclusa", label: "Esclusa" },
  { value: "horario_extendido", label: "Extendido" },
  { value: "horario_autoservicio", label: "Autoservicio" },
  { value: "horario_cerrado", label: "Oficina cerrada" },
  { value: "horario_carga_cajero", label: "Carga cajero" },
  { value: "horario_manual", label: "Manual" },
];

const DEFAULT_MONDAY = [
  { start: "08:00", end: "15:00", rule_key: "horario_automatico", active: true },
  { start: "15:00", end: "16:00", rule_key: "horario_autoservicio", active: true },
  { start: "16:00", end: "18:00", rule_key: "horario_carga_cajero", active: true },
  { start: "18:00", end: "08:00", rule_key: "horario_cerrado", active: true },
  { start: "20:00", end: "22:00", rule_key: "horario_esclusa", active: false },
];

export const DEFAULT_SCHEDULES_CONFIG = {
  enabled: false,
  days: Object.fromEntries(WEEKDAYS.map((d) => [d.key, DEFAULT_MONDAY.map((s) => ({ ...s }))])),
};

function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function parseMinutes(hhmm) {
  const [h, m] = String(hhmm || "00:00").split(":").map(Number);
  return h * 60 + m;
}

function slotStyle(slot) {
  const start = parseMinutes(slot.start);
  let end = parseMinutes(slot.end);
  if (end <= start) end += 24 * 60;
  const left = (start / (24 * 60)) * 100;
  const width = Math.max(0.8, ((end - start) / (24 * 60)) * 100);
  const active = slot.active !== false;
  return {
    left: `${left}%`,
    width: `${Math.min(width, 100 - left)}%`,
    background: active ? "#16a34a" : "#9ca3af",
    opacity: active ? 1 : 0.55,
  };
}

function inputStyle() {
  return {
    width: "100%",
    padding: "8px 10px",
    border: "1px solid #d1d5db",
    borderRadius: 8,
    fontSize: 13,
    fontFamily: "inherit",
  };
}

export default function SchedulesPanel({ apiFetch, onNotify }) {
  const [draft, setDraft] = useState(() => deepClone(DEFAULT_SCHEDULES_CONFIG));
  const [dayTab, setDayTab] = useState("monday");
  const [loading, setLoading] = useState(true);
  const [nowPreview, setNowPreview] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNowPreview(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/api/config/schedules");
      setDraft({
        ...deepClone(DEFAULT_SCHEDULES_CONFIG),
        ...data,
        days: {
          ...DEFAULT_SCHEDULES_CONFIG.days,
          ...(data?.days || {}),
        },
      });
    } catch (e) {
      onNotify?.("Error", "No se pudieron cargar horarios: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const daySlots = draft.days?.[dayTab] || [];

  const nowLinePercent = useMemo(() => {
    const m = nowPreview.getHours() * 60 + nowPreview.getMinutes();
    return (m / (24 * 60)) * 100;
  }, [nowPreview]);

  const updateSlot = (index, field, value) => {
    setDraft((prev) => {
      const next = deepClone(prev);
      next.days[dayTab][index] = { ...next.days[dayTab][index], [field]: value };
      return next;
    });
  };

  const addSlot = () => {
    setDraft((prev) => {
      const next = deepClone(prev);
      next.days[dayTab] = [
        ...(next.days[dayTab] || []),
        { start: "09:00", end: "10:00", rule_key: "horario_automatico", active: true },
      ];
      return next;
    });
  };

  const removeSlot = (index) => {
    setDraft((prev) => {
      const next = deepClone(prev);
      next.days[dayTab] = next.days[dayTab].filter((_, i) => i !== index);
      return next;
    });
  };

  const copyMondayToAll = () => {
    setDraft((prev) => {
      const next = deepClone(prev);
      const mon = deepClone(next.days.monday || []);
      WEEKDAYS.forEach(({ key }) => {
        next.days[key] = deepClone(mon);
      });
      return next;
    });
    onNotify?.("INFO", "Horario del lunes copiado a todos los días");
  };

  const save = async () => {
    try {
      await apiFetch("/api/config/schedules", {
        method: "PUT",
        body: JSON.stringify(draft),
      });
      onNotify?.("OK", "Horarios guardados");
    } catch (e) {
      onNotify?.("Error", "No se pudieron guardar horarios: " + e.message);
    }
  };

  if (loading) {
    return <div style={{ padding: 24, color: "#6b7280" }}>Cargando horarios…</div>;
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>Horarios automáticos</div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>
            El servidor activa el modo según la hora local. Si no hay franja activa, se mantiene el modo actual.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" onClick={copyMondayToAll} style={btnSecondary}>
            Copiar lunes → todos
          </button>
          <button type="button" onClick={() => void load()} style={btnSecondary}>
            Recargar
          </button>
          <button type="button" onClick={() => void save()} style={btnPrimary}>
            Guardar horarios
          </button>
        </div>
      </div>

      <label
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: 12,
          background: "#f0fdf4",
          border: "1px solid #bbf7d0",
          borderRadius: 10,
        }}
      >
        <input
          type="checkbox"
          checked={!!draft.enabled}
          onChange={(e) => setDraft((p) => ({ ...p, enabled: e.target.checked }))}
        />
        <span style={{ fontWeight: 600 }}>Detección de horarios activa</span>
        <span style={{ fontSize: 12, color: "#6b7280" }}>
          (si está desactivada, no se cambia el modo por hora)
        </span>
      </label>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {WEEKDAYS.map((d) => (
          <button
            key={d.key}
            type="button"
            onClick={() => setDayTab(d.key)}
            style={{
              ...btnSecondary,
              background: dayTab === d.key ? "#1e3a5f" : "#fff",
              color: dayTab === d.key ? "#fff" : "#111",
              borderColor: dayTab === d.key ? "#1e3a5f" : "#d1d5db",
            }}
          >
            {d.label}
          </button>
        ))}
      </div>

      <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
          Línea de tiempo — {WEEKDAYS.find((d) => d.key === dayTab)?.label}
        </div>
        <div
          style={{
            position: "relative",
            height: 56,
            background: "#f9fafb",
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            overflow: "hidden",
          }}
        >
          {daySlots.map((slot, i) => (
            <div
              key={i}
              title={`${slot.start}–${slot.end} ${slot.rule_key}`}
              style={{
                position: "absolute",
                top: 10,
                height: 36,
                borderRadius: 6,
                ...slotStyle(slot),
              }}
            />
          ))}
          <div
            style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              left: `${nowLinePercent}%`,
              width: 2,
              background: "#dc2626",
              zIndex: 2,
            }}
          />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#9ca3af", marginTop: 4 }}>
          <span>00:00</span>
          <span>06:00</span>
          <span>12:00</span>
          <span>18:00</span>
          <span>24:00</span>
        </div>
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        {daySlots.map((slot, index) => (
          <div
            key={index}
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
              gap: 10,
              alignItems: "end",
              padding: 12,
              border: "1px solid #e5e7eb",
              borderRadius: 10,
              background: slot.active === false ? "#f9fafb" : "#fff",
            }}
          >
            <label style={{ display: "grid", gap: 4 }}>
              <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600 }}>Desde</span>
              <input style={inputStyle()} value={slot.start} onChange={(e) => updateSlot(index, "start", e.target.value)} placeholder="08:00" />
            </label>
            <label style={{ display: "grid", gap: 4 }}>
              <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600 }}>Hasta</span>
              <input style={inputStyle()} value={slot.end} onChange={(e) => updateSlot(index, "end", e.target.value)} placeholder="15:00" />
            </label>
            <label style={{ display: "grid", gap: 4 }}>
              <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600 }}>Modo (rule_key)</span>
              <select style={inputStyle()} value={slot.rule_key} onChange={(e) => updateSlot(index, "rule_key", e.target.value)}>
                {RULE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 40 }}>
              <input type="checkbox" checked={slot.active !== false} onChange={(e) => updateSlot(index, "active", e.target.checked)} />
              <span style={{ fontSize: 13 }}>Activo</span>
            </label>
            <button type="button" onClick={() => removeSlot(index)} style={{ ...btnSecondary, color: "#dc2626", borderColor: "#fecaca" }}>
              Eliminar
            </button>
          </div>
        ))}
      </div>

      <button type="button" onClick={addSlot} style={{ ...btnSecondary, justifySelf: "start" }}>
        + Añadir franja
      </button>
    </div>
  );
}

const btnPrimary = {
  fontFamily: "inherit",
  fontSize: 13,
  fontWeight: 600,
  padding: "9px 16px",
  borderRadius: 8,
  cursor: "pointer",
  background: "#16a34a",
  color: "#fff",
  border: "1px solid #15803d",
};

const btnSecondary = {
  fontFamily: "inherit",
  fontSize: 13,
  fontWeight: 600,
  padding: "9px 14px",
  borderRadius: 8,
  cursor: "pointer",
  background: "#fff",
  color: "#111",
  border: "1px solid #d1d5db",
};
