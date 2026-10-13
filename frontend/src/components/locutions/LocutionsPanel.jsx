import { useEffect, useState } from "react";

const EVENT_OPTIONS = [
  { value: "mode_entered", label: "Al entrar en el modo" },
  { value: "door_opened", label: "Al abrirse la puerta" },
];

const DOOR_OPTIONS = [
  { value: "any", label: "Cualquiera" },
  { value: "p1", label: "P1 (calle)" },
  { value: "p2", label: "P2 (oficina)" },
];

function newTrigger(outputs) {
  return {
    id: `t${Date.now().toString(36)}`,
    enabled: true,
    label: "",
    event: "door_opened",
    mode: "horario_extendido",
    door: "p1",
    output: outputs[0]?.code || "OUT_01_02",
    pulse_seconds: 1,
    cooldown_seconds: 10,
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

function Field({ label, children }) {
  return (
    <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#374151" }}>
      <span style={{ fontWeight: 600 }}>{label}</span>
      {children}
    </label>
  );
}

export default function LocutionsPanel({ apiFetch, onNotify }) {
  const [triggers, setTriggers] = useState([]);
  const [outputs, setOutputs] = useState([]);
  const [modes, setModes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/locutions");
      setTriggers(Array.isArray(data?.triggers) ? data.triggers : []);
      setOutputs(Array.isArray(data?.outputs) ? data.outputs : []);
      setModes(Array.isArray(data?.modes) ? data.modes : []);
    } catch (e) {
      onNotify?.("Error", "No se pudieron cargar las locuciones: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const update = (index, field, value) => {
    setTriggers((prev) =>
      prev.map((t, i) => {
        if (i !== index) return t;
        const next = { ...t, [field]: value };
        if (next.event === "mode_entered" && next.mode === "any") {
          next.mode = modes[0]?.key || "horario_extendido";
        }
        return next;
      }),
    );
  };

  const save = async () => {
    setSaving(true);
    try {
      const data = await apiFetch("/locutions", {
        method: "PUT",
        body: JSON.stringify({ triggers }),
      });
      setTriggers(data?.triggers || triggers);
      onNotify?.("OK", "Locuciones guardadas");
    } catch (e) {
      onNotify?.("Error", "No se pudieron guardar: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  const test = async (output, seconds) => {
    setTesting(output);
    try {
      await apiFetch("/locutions/test", {
        method: "POST",
        body: JSON.stringify({ output, pulse_seconds: Number(seconds) || 1 }),
      });
      onNotify?.("OK", "Locución enviada al reproductor");
    } catch (e) {
      onNotify?.("Error", "No se pudo reproducir: " + e.message);
    } finally {
      setTesting(null);
    }
  };

  if (loading) {
    return <div style={{ padding: 24, color: "#6b7280" }}>Cargando locuciones…</div>;
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>Locuciones</div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>
            Cada disparo pulsa un relé del reproductor de audio (placa 1, OUT2–OUT4) cuando ocurre el evento.
            La pista que suena es la grabada en el reproductor para ese relé.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" onClick={() => void load()} style={btnSecondary}>
            Recargar
          </button>
          <button
            type="button"
            onClick={() => setTriggers((prev) => [...prev, newTrigger(outputs)])}
            style={btnSecondary}
          >
            Añadir disparo
          </button>
          <button type="button" onClick={() => void save()} style={btnPrimary} disabled={saving}>
            {saving ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>

      <section style={card}>
        <div style={{ fontWeight: 700, marginBottom: 10 }}>Probar relés</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {outputs.map((o) => (
            <button
              key={o.code}
              type="button"
              style={btnSecondary}
              disabled={testing === o.code}
              onClick={() => void test(o.code, 1)}
            >
              ▶ {o.label} ({o.code})
            </button>
          ))}
        </div>
      </section>

      {triggers.length === 0 ? (
        <div style={{ ...card, color: "#6b7280" }}>No hay disparos configurados.</div>
      ) : null}

      {triggers.map((t, index) => (
        <section key={t.id} style={{ ...card, opacity: t.enabled ? 1 : 0.7 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700 }}>
              <input type="checkbox" checked={!!t.enabled} onChange={(e) => update(index, "enabled", e.target.checked)} />
              {t.enabled ? "Activo" : "Desactivado"}
            </label>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                style={btnSecondary}
                disabled={testing === t.output}
                onClick={() => void test(t.output, t.pulse_seconds)}
              >
                Probar
              </button>
              <button
                type="button"
                style={{ ...btnSecondary, color: "#b91c1c", borderColor: "#fecaca" }}
                onClick={() => setTriggers((prev) => prev.filter((_, i) => i !== index))}
              >
                Eliminar
              </button>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
            <Field label="Nombre">
              <input
                style={inputStyle()}
                value={t.label || ""}
                placeholder="Bienvenido (horario extendido)"
                onChange={(e) => update(index, "label", e.target.value)}
              />
            </Field>
            <Field label="Evento">
              <select style={inputStyle()} value={t.event} onChange={(e) => update(index, "event", e.target.value)}>
                {EVENT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Modo">
              <select style={inputStyle()} value={t.mode} onChange={(e) => update(index, "mode", e.target.value)}>
                {t.event === "door_opened" ? <option value="any">Cualquier modo</option> : null}
                {modes.map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.label}
                  </option>
                ))}
              </select>
            </Field>
            {t.event === "door_opened" ? (
              <Field label="Puerta">
                <select style={inputStyle()} value={t.door} onChange={(e) => update(index, "door", e.target.value)}>
                  {DOOR_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </Field>
            ) : null}
            <Field label="Relé de locución">
              <select style={inputStyle()} value={t.output} onChange={(e) => update(index, "output", e.target.value)}>
                {outputs.map((o) => (
                  <option key={o.code} value={o.code}>
                    {o.label} ({o.code})
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Pulso (s)">
              <input
                type="number"
                min={0.3}
                max={30}
                step={0.1}
                style={inputStyle()}
                value={t.pulse_seconds}
                onChange={(e) => update(index, "pulse_seconds", e.target.value)}
              />
            </Field>
            <Field label="Espera mínima entre repeticiones (s)">
              <input
                type="number"
                min={0}
                max={600}
                step={1}
                style={inputStyle()}
                value={t.cooldown_seconds}
                onChange={(e) => update(index, "cooldown_seconds", e.target.value)}
              />
            </Field>
          </div>
        </section>
      ))}
    </div>
  );
}

const card = {
  background: "#fff",
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  padding: 16,
};

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
