import { useEffect, useMemo, useState } from "react";
import { resolveRuleColor, ruleKeyToLabel } from "../../utils/ruleModeColors";

const WEEKDAYS = [
  { key: "monday", label: "Lunes" },
  { key: "tuesday", label: "Martes" },
  { key: "wednesday", label: "Miércoles" },
  { key: "thursday", label: "Jueves" },
  { key: "friday", label: "Viernes" },
  { key: "saturday", label: "Sábado" },
  { key: "sunday", label: "Domingo" },
];

const RULE_OPTIONS_FALLBACK = [
  { value: "horario_automatico", label: "Automático" },
  { value: "horario_esclusa", label: "Esclusa" },
  { value: "horario_extendido", label: "Extendido" },
  { value: "horario_autoservicio", label: "Autoservicio" },
  { value: "horario_cerrado", label: "Oficina cerrada" },
  { value: "horario_carga_cajero", label: "Carga cajero" },
  { value: "horario_manual", label: "Manual" },
];

const DEFAULT_MONDAY = [
  {
    start: "08:00",
    end: "15:00",
    rule_key: "horario_automatico",
    active: true,
  },
  {
    start: "15:00",
    end: "16:00",
    rule_key: "horario_autoservicio",
    active: true,
  },
  {
    start: "16:00",
    end: "18:00",
    rule_key: "horario_carga_cajero",
    active: true,
  },
  { start: "18:00", end: "08:00", rule_key: "horario_cerrado", active: true },
  { start: "20:00", end: "22:00", rule_key: "horario_esclusa", active: false },
];

export const DEFAULT_LOCATION = {
  address: "",
  latitude: null,
  longitude: null,
  captured_at: null,
};

export const DEFAULT_SCHEDULES_CONFIG = {
  enabled: false,
  days: Object.fromEntries(
    WEEKDAYS.map((d) => [d.key, DEFAULT_MONDAY.map((s) => ({ ...s }))]),
  ),
  location: { ...DEFAULT_LOCATION },
};

function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function parseMinutes(hhmm) {
  const [h, m] = String(hhmm || "00:00")
    .split(":")
    .map(Number);
  return (Number.isFinite(h) ? h : 0) * 60 + (Number.isFinite(m) ? m : 0);
}

function formatMinutes(totalMinutes) {
  const day = 24 * 60;
  const mm = ((totalMinutes % day) + day) % day;
  const h = Math.floor(mm / 60);
  const m = mm % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** Inicio visual de la línea: Automático, o la franja más temprana. */
function timelineStartMinutes(slots) {
  if (!Array.isArray(slots) || slots.length === 0) return 0;
  const auto = slots.find((s) => s.rule_key === "horario_automatico");
  if (auto) return parseMinutes(auto.start);
  let earliest = null;
  for (const slot of slots) {
    const m = parseMinutes(slot.start);
    if (earliest === null || m < earliest) earliest = m;
  }
  return earliest ?? 0;
}

function slotStyle(slot, rules, rangeStart = 0) {
  const day = 24 * 60;
  const windowStart = rangeStart;
  const windowEnd = rangeStart + day;
  let start = parseMinutes(slot.start);
  let end = parseMinutes(slot.end);
  if (end <= start) end += day;

  if (end <= windowStart) {
    start += day;
    end += day;
  }
  if (start >= windowEnd) {
    start -= day;
    end -= day;
  }

  const leftMin = Math.max(start, windowStart);
  const rightMin = Math.min(end, windowEnd);
  if (rightMin <= leftMin) {
    return { display: "none" };
  }

  const left = ((leftMin - windowStart) / day) * 100;
  const width = Math.max(0.8, ((rightMin - leftMin) / day) * 100);
  const active = slot.active !== false;
  const modeColor = resolveRuleColor(slot.rule_key, rules);
  return {
    left: `${left}%`,
    width: `${Math.min(width, 100 - left)}%`,
    background: active ? modeColor : "#9ca3af",
    opacity: active ? 1 : 0.55,
  };
}

function buildRuleOptions(rules) {
  const keys = Object.keys(rules || {}).sort();
  if (!keys.length) return RULE_OPTIONS_FALLBACK;
  return keys.map((value) => ({
    value,
    label: ruleKeyToLabel(value),
    color: resolveRuleColor(value, rules),
  }));
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
  const [rules, setRules] = useState({});
  const [dayTab, setDayTab] = useState("monday");
  const [loading, setLoading] = useState(true);
  const [geoBusy, setGeoBusy] = useState(false);
  const [locationSaving, setLocationSaving] = useState(false);
  const [savedLocation, setSavedLocation] = useState(() => ({
    ...DEFAULT_LOCATION,
  }));
  const [nowPreview, setNowPreview] = useState(() => new Date());

  const ruleOptions = useMemo(() => buildRuleOptions(rules), [rules]);

  useEffect(() => {
    const t = setInterval(() => setNowPreview(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [data, rulesData] = await Promise.all([
        apiFetch("/api/config/schedules"),
        apiFetch("/rules").catch(() => ({ rules: {} })),
      ]);
      setRules(rulesData?.rules || {});
      const mergedLocation = {
        ...DEFAULT_LOCATION,
        ...(data?.location || {}),
      };
      setDraft({
        ...deepClone(DEFAULT_SCHEDULES_CONFIG),
        ...data,
        days: {
          ...DEFAULT_SCHEDULES_CONFIG.days,
          ...(data?.days || {}),
        },
        location: mergedLocation,
      });
      setSavedLocation(deepClone(mergedLocation));
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
  const location = draft.location || { ...DEFAULT_LOCATION };
  const timelineStart = useMemo(
    () => timelineStartMinutes(daySlots),
    [daySlots],
  );
  const timelineLabels = useMemo(() => {
    return [0, 6, 12, 18, 24].map((h) => formatMinutes(timelineStart + h * 60));
  }, [timelineStart]);

  const locationDirty = useMemo(() => {
    return JSON.stringify(location) !== JSON.stringify(savedLocation);
  }, [location, savedLocation]);

  const validateLocation = () => {
    const { latitude: lat, longitude: lng } = location;
    if (lat != null && (Number.isNaN(lat) || lat < -90 || lat > 90)) {
      onNotify?.("Error", "La latitud debe estar entre -90 y 90");
      return false;
    }
    if (lng != null && (Number.isNaN(lng) || lng < -180 || lng > 180)) {
      onNotify?.("Error", "La longitud debe estar entre -180 y 180");
      return false;
    }
    return true;
  };

  const updateLocation = (field, value) => {
    setDraft((prev) => ({
      ...prev,
      location: { ...(prev.location || DEFAULT_LOCATION), [field]: value },
    }));
  };

  const captureGeolocation = () => {
    if (!navigator.geolocation) {
      onNotify?.("Error", "Este navegador no soporta geolocalización");
      return;
    }
    setGeoBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        setDraft((prev) => ({
          ...prev,
          location: {
            ...(prev.location || DEFAULT_LOCATION),
            latitude: Math.round(lat * 1e6) / 1e6,
            longitude: Math.round(lng * 1e6) / 1e6,
            captured_at: new Date().toISOString(),
          },
        }));
        setGeoBusy(false);
        onNotify?.(
          "OK",
          `Ubicación capturada (${lat.toFixed(5)}, ${lng.toFixed(5)})`,
        );
      },
      (err) => {
        setGeoBusy(false);
        const msg =
          err.code === 1
            ? "Permiso de ubicación denegado"
            : err.code === 2
              ? "Ubicación no disponible"
              : err.code === 3
                ? "Tiempo de espera agotado al obtener ubicación"
                : err.message || "No se pudo obtener la ubicación";
        onNotify?.("Error", msg);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  };

  const saveLocation = async () => {
    if (!validateLocation()) return;
    setLocationSaving(true);
    try {
      const current = await apiFetch("/api/config/schedules");
      const payload = {
        ...current,
        location: deepClone(location),
      };
      await apiFetch("/api/config/schedules", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setSavedLocation(deepClone(location));
      setDraft((prev) => ({ ...prev, location: deepClone(location) }));
      onNotify?.("OK", "Ubicación guardada correctamente");
    } catch (e) {
      onNotify?.("Error", "No se pudo guardar la ubicación: " + e.message);
    } finally {
      setLocationSaving(false);
    }
  };

  const nowLinePercent = useMemo(() => {
    const day = 24 * 60;
    const m = nowPreview.getHours() * 60 + nowPreview.getMinutes();
    const rel = (((m - timelineStart) % day) + day) % day;
    return (rel / day) * 100;
  }, [nowPreview, timelineStart]);

  const updateSlot = (index, field, value) => {
    setDraft((prev) => {
      const next = deepClone(prev);
      next.days[dayTab][index] = {
        ...next.days[dayTab][index],
        [field]: value,
      };
      return next;
    });
  };

  const addSlot = () => {
    setDraft((prev) => {
      const next = deepClone(prev);
      next.days[dayTab] = [
        ...(next.days[dayTab] || []),
        {
          start: "09:00",
          end: "10:00",
          rule_key: "horario_automatico",
          active: true,
        },
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
    if (!validateLocation()) return;
    try {
      await apiFetch("/api/config/schedules", {
        method: "PUT",
        body: JSON.stringify(draft),
      });
      setSavedLocation(deepClone(location));
      onNotify?.("OK", "Horarios guardados");
    } catch (e) {
      onNotify?.("Error", "No se pudieron guardar horarios: " + e.message);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 24, color: "#6b7280" }}>Cargando horarios…</div>
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
            Horarios automáticos
          </div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>
            El servidor activa el modo según la hora local. Si no hay franja
            activa, se mantiene el modo actual.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" onClick={copyMondayToAll} style={btnSecondary}>
            Copiar lunes → todos
          </button>
          <button
            type="button"
            onClick={() => void load()}
            style={btnSecondary}
          >
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
          onChange={(e) =>
            setDraft((p) => ({ ...p, enabled: e.target.checked }))
          }
        />
        <span style={{ fontWeight: 600 }}>Detección de horarios activa</span>
        <span style={{ fontSize: 12, color: "#6b7280" }}>
          (si está desactivada, no se cambia el modo por hora)
        </span>
      </label>

      <section
        style={{
          background: "#fff",
          border: `1px solid ${locationDirty ? "#fcd34d" : "#e5e7eb"}`,
          borderRadius: 12,
          padding: 16,
          display: "grid",
          gap: 14,
          boxShadow: locationDirty ? "0 0 0 1px #fef3c7" : "none",
        }}
      >
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 12,
            justifyContent: "space-between",
            alignItems: "flex-start",
          }}
        >
          <div>
            <div style={{ fontSize: 15, fontWeight: 700 }}>
              Ubicación de la sucursal
            </div>
            <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>
              Coordenadas para el mapa del COCE. La dirección es solo referencia
              en consola.
            </div>
            {locationDirty ? (
              <div
                style={{
                  fontSize: 11,
                  color: "#b45309",
                  marginTop: 6,
                  fontWeight: 600,
                }}
              >
                Hay cambios sin guardar en la ubicación
              </div>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => void saveLocation()}
            disabled={locationSaving || !locationDirty}
            style={{
              ...btnPrimary,
              background: locationDirty ? "#16a34a" : "#9ca3af",
              borderColor: locationDirty ? "#15803d" : "#9ca3af",
              opacity: locationSaving ? 0.75 : 1,
              cursor:
                locationSaving || !locationDirty ? "not-allowed" : "pointer",
              minWidth: 160,
            }}
          >
            {locationSaving ? "Guardando…" : "Guardar ubicación"}
          </button>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 10,
          }}
        >
          <label style={{ display: "grid", gap: 4 }}>
            <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600 }}>
              Latitud
            </span>
            <input
              style={inputStyle()}
              type="number"
              step="any"
              placeholder="40.416775"
              value={location.latitude ?? ""}
              onChange={(e) => {
                const v = e.target.value.trim();
                updateLocation("latitude", v === "" ? null : Number(v));
              }}
            />
          </label>
          <label style={{ display: "grid", gap: 4 }}>
            <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600 }}>
              Longitud
            </span>
            <input
              style={inputStyle()}
              type="number"
              step="any"
              placeholder="-3.703790"
              value={location.longitude ?? ""}
              onChange={(e) => {
                const v = e.target.value.trim();
                updateLocation("longitude", v === "" ? null : Number(v));
              }}
            />
          </label>
        </div>

        <button
          type="button"
          onClick={captureGeolocation}
          disabled={geoBusy}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            width: "100%",
            padding: "12px 16px",
            borderRadius: 10,
            border: "1px solid #93c5fd",
            background: geoBusy
              ? "linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%)"
              : "linear-gradient(180deg, #f8fbff 0%, #eff6ff 100%)",
            color: "#1d4ed8",
            fontFamily: "inherit",
            fontSize: 14,
            fontWeight: 700,
            cursor: geoBusy ? "wait" : "pointer",
            opacity: geoBusy ? 0.85 : 1,
            transition: "background 0.15s ease, box-shadow 0.15s ease",
            boxShadow: geoBusy ? "none" : "0 1px 2px rgba(29, 78, 216, 0.08)",
          }}
        >
          {geoBusy ? (
            <>
              <span
                style={{
                  width: 18,
                  height: 18,
                  border: "2px solid #93c5fd",
                  borderTopColor: "#1d4ed8",
                  borderRadius: "50%",
                  display: "inline-block",
                  animation: "schedules-geo-spin 0.8s linear infinite",
                }}
              />
              Obteniendo coordenadas GPS…
            </>
          ) : (
            <>
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"
                  fill="#1d4ed8"
                  opacity="0.15"
                />
                <path
                  d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 110-5 2.5 2.5 0 010 5z"
                  fill="#1d4ed8"
                />
              </svg>
              Usar mi ubicación actual (GPS)
            </>
          )}
        </button>

        {location.latitude != null && location.longitude != null ? (
          <div
            style={{
              fontSize: 12,
              color: "#1e40af",
              background: "#eff6ff",
              border: "1px solid #bfdbfe",
              borderRadius: 8,
              padding: "8px 12px",
            }}
          >
            Coordenadas actuales: {Number(location.latitude).toFixed(6)},{" "}
            {Number(location.longitude).toFixed(6)}
          </div>
        ) : null}

        <label style={{ display: "grid", gap: 4 }}>
          <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600 }}>
            Dirección (manual)
          </span>
          <textarea
            style={{
              ...inputStyle(),
              minHeight: 72,
              resize: "vertical",
              fontFamily: "inherit",
            }}
            placeholder="Calle, número, ciudad, código postal…"
            value={location.address || ""}
            onChange={(e) => updateLocation("address", e.target.value)}
          />
        </label>

        {location.captured_at ? (
          <div style={{ fontSize: 11, color: "#6b7280" }}>
            Última captura GPS:{" "}
            {new Date(location.captured_at).toLocaleString("es-ES")}
          </div>
        ) : null}
      </section>

      <style>{`
        @keyframes schedules-geo-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>

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

      <div
        style={{
          background: "#fff",
          border: "1px solid #e5e7eb",
          borderRadius: 12,
          padding: 16,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
          Línea de tiempo — {WEEKDAYS.find((d) => d.key === dayTab)?.label}
          <span style={{ fontWeight: 500, color: "#6b7280", marginLeft: 8 }}>
            (desde {timelineLabels[0]})
          </span>
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
              title={`${slot.start}–${slot.end} ${ruleKeyToLabel(slot.rule_key)}`}
              style={{
                position: "absolute",
                top: 10,
                height: 36,
                borderRadius: 6,
                ...slotStyle(slot, rules, timelineStart),
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
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: 10,
            color: "#9ca3af",
            marginTop: 4,
          }}
        >
          {timelineLabels.map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        {daySlots.map((slot, index) => (
          <div
            key={index}
            style={{
              display: "grid",
              gridTemplateColumns:
                "minmax(120px, 0.9fr) minmax(120px, 0.9fr) minmax(220px, 1.6fr) auto auto",
              gap: 10,
              alignItems: "end",
              padding: 12,
              border: "1px solid #e5e7eb",
              borderRadius: 10,
              background: slot.active === false ? "#f9fafb" : "#fff",
            }}
          >
            <label style={{ display: "grid", gap: 4 }}>
              <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600 }}>
                Desde
              </span>
              <input
                style={inputStyle()}
                value={slot.start}
                onChange={(e) => updateSlot(index, "start", e.target.value)}
                placeholder="08:00"
              />
            </label>
            <label style={{ display: "grid", gap: 4 }}>
              <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600 }}>
                Hasta
              </span>
              <input
                style={inputStyle()}
                value={slot.end}
                onChange={(e) => updateSlot(index, "end", e.target.value)}
                placeholder="15:00"
              />
            </label>
            <label style={{ display: "grid", gap: 4 }}>
              <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600 }}>
                Modo
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span
                  title={resolveRuleColor(slot.rule_key, rules)}
                  style={{
                    width: 20,
                    height: 20,
                    borderRadius: 5,
                    flexShrink: 0,
                    border: "1px solid #d1d5db",
                    background: resolveRuleColor(slot.rule_key, rules),
                  }}
                />
                <select
                  style={{
                    ...inputStyle(),
                    flex: 1,
                    minHeight: 44,
                    fontSize: 15,
                    fontWeight: 600,
                    padding: "10px 12px",
                  }}
                  value={slot.rule_key}
                  onChange={(e) =>
                    updateSlot(index, "rule_key", e.target.value)
                  }
                >
                  {ruleOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </label>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                minHeight: 40,
              }}
            >
              <input
                type="checkbox"
                checked={slot.active !== false}
                onChange={(e) => updateSlot(index, "active", e.target.checked)}
              />
              <span style={{ fontSize: 13 }}>Activo</span>
            </label>
            <button
              type="button"
              onClick={() => removeSlot(index)}
              style={{
                ...btnSecondary,
                color: "#dc2626",
                borderColor: "#fecaca",
              }}
            >
              Eliminar
            </button>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={addSlot}
        style={{ ...btnSecondary, justifySelf: "start" }}
      >
        + Añadir franja
      </button>

      {ruleOptions.length > 0 && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 10,
            padding: 12,
            background: "#f9fafb",
            border: "1px solid #e5e7eb",
            borderRadius: 10,
            fontSize: 12,
          }}
        >
          <span style={{ fontWeight: 600, color: "#374151", width: "100%" }}>
            Leyenda de modos
          </span>
          {ruleOptions.map((o) => (
            <span
              key={o.value}
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
            >
              <span
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: 3,
                  background: o.color || resolveRuleColor(o.value, rules),
                  border: "1px solid #d1d5db",
                }}
              />
              {o.label}
            </span>
          ))}
        </div>
      )}
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
