/**
 * Configuración por defecto de tablets en el panel web (espejo del backend).
 */
import { useEffect, useState } from "react";

export const DEFAULT_TABLET_PANEL_CONFIG = {
  doors: [
    {
      enabled: true,
      name: "Calle (P1)",
      ipExterior: "192.168.1.200",
      ipInterior: "",
      intercom: {
        name: "Intercomunicador Calle (P1)",
        cameraIP: "192.168.1.200",
        httpPort: 80,
        httpsPort: 443,
        onvifUsername: "ceroideas",
        onvifPassword: "Cero21264712-",
        rtspPort: 554,
        sdkPort: 9008,
        sdkUsername: "admin",
        sdkPassword: "Santander@01",
        voiceChannel: -1,
        intercomMode: "bridge",
        bridgeUrl: "ws://192.168.1.155:8765",
        videoProfile: "MainStream",
        snapshotPath: "ISAPI/Streaming/channels/101/picture",
        doorControlUsername: "Scati2023",
        doorControlPassword: "Scati2023",
        doorControlPCB: 2,
        doorControlSwitch: 7,
        doorControlAction: "set_output",
        doorControlRuleKey: "",
        doorOutputMode: "auto",
        doorControlPulseTime: 1,
        hasAudio: true,
        rtspPath: "profile1",
      },
    },
    {
      enabled: true,
      name: "Oficina (P2)",
      ipExterior: "192.168.1.210",
      ipInterior: "",
      intercom: {
        name: "Intercomunicador Oficina (P2)",
        cameraIP: "192.168.1.210",
        httpPort: 80,
        httpsPort: 443,
        onvifUsername: "ceroideas",
        onvifPassword: "Cero21264712-",
        rtspPort: 554,
        sdkPort: 9008,
        sdkUsername: "admin",
        sdkPassword: "Santander@01.",
        voiceChannel: -1,
        intercomMode: "bridge",
        bridgeUrl: "ws://192.168.1.155:8765",
        videoProfile: "MainStream",
        doorControlUsername: "Scati2023",
        doorControlPassword: "Scati2023",
        doorControlPCB: 3,
        doorControlSwitch: 7,
        doorControlAction: "set_output",
        doorOutputMode: "auto",
        hasAudio: true,
      },
    },
    { enabled: false, name: "Puerta 3", ipExterior: "", ipInterior: "", intercom: { name: "P3", cameraIP: "" } },
    { enabled: false, name: "Puerta 4", ipExterior: "", ipInterior: "", intercom: { name: "P4", cameraIP: "" } },
    { enabled: false, name: "Puerta 5", ipExterior: "", ipInterior: "", intercom: { name: "P5", cameraIP: "" } },
  ],
  network: { consoleIP: "192.168.1.155", netmask: "255.255.255.0", gateway: "0.0.0.0" },
  api: {
    port: 8000,
    username: "ceroideas",
    password: "12345678",
    urlToken: "/api/v1/auth/token",
    urlGet: "/api/v1/get_mode",
    urlPost: "/api/v1/set_mode",
    urlModes: "/api/v1/modes",
  },
  schedules: {
    comercial: { ini1: "08:00", ini2: "14:00" },
    extendido: { ini1: "07:00", ini2: "22:00" },
    autoservicio: { ini1: "00:00", ini2: "23:59" },
    cerrado: { ini1: "22:00", ini2: "08:00" },
  },
  officeWithATM: false,
  emergency: {
    enabled: true,
    rule_key: "senal_de_incendio_activada",
    action: "set_rule",
    output_code: "",
    output_on: true,
  },
  modes: {
    automatico: { rule_key: "horario_automatico", action: "set_rule", enabled: true, output_code: "", output_on: true },
    esclusa: { rule_key: "horario_esclusa", action: "set_rule", enabled: true, output_code: "", output_on: true },
    extendido: { rule_key: "horario_extendido", action: "set_rule", enabled: true, output_code: "", output_on: true },
    autoservicio: { rule_key: "horario_autoservicio", action: "set_rule", enabled: true, output_code: "", output_on: true },
    oficinaCerrada: { rule_key: "horario_cerrado", action: "set_rule", enabled: true, output_code: "", output_on: true },
    cargaCajero: { rule_key: "horario_carga_cajero", action: "set_rule", enabled: true, output_code: "", output_on: true },
    manual: { rule_key: "horario_manual", action: "set_rule", enabled: true, output_code: "", output_on: true },
  },
  tabletCall: {
    enabled: true,
    timeoutSeconds: 30,
    modes: "horario_manual,horario_carga_cajero,horario_extendido",
    pulsadores: "p1",
  },
};

const MODE_LABELS = {
  automatico: "Automático",
  esclusa: "Esclusa",
  extendido: "Extendido",
  autoservicio: "Autoservicio",
  oficinaCerrada: "Oficina cerrada",
  cargaCajero: "Carga cajero",
  manual: "Manual",
};

const SUB_TABS = [
  { id: "red", label: "Red / API" },
  { id: "puertas", label: "Puertas / Intercom" },
  { id: "modos", label: "Modos" },
  { id: "emergencia", label: "Emergencia" },
  { id: "llamadas", label: "Llamadas tablet" },
  { id: "oficina", label: "Tipo oficina" },
];

function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function ensureDoors(config) {
  const doors = Array.isArray(config.doors) ? [...config.doors] : [];
  while (doors.length < 5) {
    doors.push({
      enabled: false,
      name: `Puerta ${doors.length + 1}`,
      ipExterior: "",
      ipInterior: "",
      intercom: { name: "", cameraIP: "" },
    });
  }
  return { ...config, doors: doors.slice(0, 5) };
}

function Field({ label, children }) {
  return (
    <label style={{ display: "grid", gap: 4 }}>
      <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600 }}>{label}</span>
      {children}
    </label>
  );
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

export default function TabletConfigPanel({ apiFetch, onNotify }) {
  const [subTab, setSubTab] = useState("red");
  const [draft, setDraft] = useState(() => deepClone(DEFAULT_TABLET_PANEL_CONFIG));
  const [revision, setRevision] = useState("builtin");
  const [updatedAt, setUpdatedAt] = useState(null);
  const [doorIndex, setDoorIndex] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/api/config/tablet");
      const cfg = ensureDoors({ ...deepClone(DEFAULT_TABLET_PANEL_CONFIG), ...(data?.config || {}) });
      setDraft(cfg);
      setRevision(data?.revision || "builtin");
      setUpdatedAt(data?.updated_at || null);
    } catch (e) {
      onNotify?.("Error", "No se pudo cargar configuración tablet: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const patch = (path, value) => {
    setDraft((prev) => {
      const next = deepClone(prev);
      let ref = next;
      const keys = path.split(".");
      for (let i = 0; i < keys.length - 1; i += 1) {
        const k = keys[i];
        if (ref[k] == null || typeof ref[k] !== "object") ref[k] = {};
        ref = ref[k];
      }
      ref[keys[keys.length - 1]] = value;
      return ensureDoors(next);
    });
  };

  const patchDoor = (index, field, value) => {
    setDraft((prev) => {
      const next = ensureDoors(deepClone(prev));
      next.doors[index] = { ...next.doors[index], [field]: value };
      return next;
    });
  };

  const patchDoorIntercom = (index, field, value) => {
    setDraft((prev) => {
      const next = ensureDoors(deepClone(prev));
      const door = next.doors[index];
      door.intercom = { ...(door.intercom || {}), [field]: value };
      return next;
    });
  };

  const patchMode = (key, field, value) => {
    setDraft((prev) => {
      const next = deepClone(prev);
      next.modes = next.modes || {};
      next.modes[key] = { ...(next.modes[key] || {}), [field]: value };
      return next;
    });
  };

  const save = async () => {
    try {
      const res = await apiFetch("/api/config/tablet", {
        method: "PUT",
        body: JSON.stringify(draft),
      });
      setRevision(res?.revision || revision);
      setUpdatedAt(res?.updated_at || new Date().toISOString());
      onNotify?.("OK", "Configuración tablet guardada (defaults de sucursal)");
    } catch (e) {
      onNotify?.("Error", "No se pudo guardar: " + e.message);
    }
  };

  const resetBuiltin = () => {
    setDraft(deepClone(DEFAULT_TABLET_PANEL_CONFIG));
    onNotify?.("INFO", "Borrador restaurado a valores de fábrica (guarda para aplicar)");
  };

  const door = draft.doors?.[doorIndex] || draft.doors[0];
  const intercom = door?.intercom || {};

  if (loading) {
    return <div style={{ padding: 24, color: "#6b7280" }}>Cargando configuración tablet…</div>;
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>Configuración tablet (defaults sucursal)</div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>
            Revisión: {revision}
            {updatedAt ? ` · Actualizado: ${updatedAt}` : " · Sin guardar en panel aún"}
          </div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
            Las tablets importan estos valores con «Restaurar datos por defecto». Los horarios (schedules) se configurarán después desde el panel.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" onClick={resetBuiltin} style={btnSecondary}>
            Restaurar fábrica
          </button>
          <button type="button" onClick={() => void load()} style={btnSecondary}>
            Recargar
          </button>
          <button type="button" onClick={() => void save()} style={btnPrimary}>
            Guardar defaults
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {SUB_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setSubTab(t.id)}
            style={{
              ...btnSecondary,
              background: subTab === t.id ? "#1e3a5f" : "#fff",
              color: subTab === t.id ? "#fff" : "#111",
              borderColor: subTab === t.id ? "#1e3a5f" : "#d1d5db",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div
        style={{
          background: "#fff",
          border: "1px solid #e5e7eb",
          borderRadius: 12,
          padding: 16,
          display: "grid",
          gap: 14,
        }}
      >
        {subTab === "red" && (
          <>
            <div style={grid2}>
              <Field label="IP consola (consoleIP)">
                <input style={inputStyle()} value={draft.network?.consoleIP || ""} onChange={(e) => patch("network.consoleIP", e.target.value)} />
              </Field>
              <Field label="Puerto API">
                <input style={inputStyle()} type="number" value={draft.api?.port ?? 8000} onChange={(e) => patch("api.port", Number(e.target.value))} />
              </Field>
              <Field label="Usuario API">
                <input style={inputStyle()} value={draft.api?.username || ""} onChange={(e) => patch("api.username", e.target.value)} />
              </Field>
              <Field label="Contraseña API">
                <input style={inputStyle()} type="password" value={draft.api?.password || ""} onChange={(e) => patch("api.password", e.target.value)} />
              </Field>
              <Field label="URL token">
                <input style={inputStyle()} value={draft.api?.urlToken || ""} onChange={(e) => patch("api.urlToken", e.target.value)} />
              </Field>
              <Field label="URL get_mode">
                <input style={inputStyle()} value={draft.api?.urlGet || ""} onChange={(e) => patch("api.urlGet", e.target.value)} />
              </Field>
              <Field label="URL set_mode">
                <input style={inputStyle()} value={draft.api?.urlPost || ""} onChange={(e) => patch("api.urlPost", e.target.value)} />
              </Field>
              <Field label="URL modes (legacy)">
                <input style={inputStyle()} value={draft.api?.urlModes || ""} onChange={(e) => patch("api.urlModes", e.target.value)} />
              </Field>
            </div>
          </>
        )}

        {subTab === "puertas" && (
          <>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {draft.doors.map((d, i) => (
                <button key={i} type="button" onClick={() => setDoorIndex(i)} style={{ ...btnSecondary, fontWeight: doorIndex === i ? 700 : 400 }}>
                  P{i + 1}: {d.name || `Puerta ${i + 1}`}
                </button>
              ))}
            </div>
            <div style={grid2}>
              <Field label="Nombre">
                <input style={inputStyle()} value={door.name || ""} onChange={(e) => patchDoor(doorIndex, "name", e.target.value)} />
              </Field>
              <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 20 }}>
                <input type="checkbox" checked={!!door.enabled} onChange={(e) => patchDoor(doorIndex, "enabled", e.target.checked)} />
                <span>Habilitada</span>
              </label>
              <Field label="IP exterior">
                <input style={inputStyle()} value={door.ipExterior || ""} onChange={(e) => patchDoor(doorIndex, "ipExterior", e.target.value)} />
              </Field>
              <Field label="IP interior">
                <input style={inputStyle()} value={door.ipInterior || ""} onChange={(e) => patchDoor(doorIndex, "ipInterior", e.target.value)} />
              </Field>
              <Field label="Intercom — nombre">
                <input style={inputStyle()} value={intercom.name || ""} onChange={(e) => patchDoorIntercom(doorIndex, "name", e.target.value)} />
              </Field>
              <Field label="Cámara IP">
                <input style={inputStyle()} value={intercom.cameraIP || ""} onChange={(e) => patchDoorIntercom(doorIndex, "cameraIP", e.target.value)} />
              </Field>
              <Field label="Bridge URL (WebSocket)">
                <input style={inputStyle()} value={intercom.bridgeUrl || ""} onChange={(e) => patchDoorIntercom(doorIndex, "bridgeUrl", e.target.value)} />
              </Field>
              <Field label="Modo intercom">
                <select style={inputStyle()} value={intercom.intercomMode || "bridge"} onChange={(e) => patchDoorIntercom(doorIndex, "intercomMode", e.target.value)}>
                  <option value="bridge">bridge</option>
                  <option value="sdk">sdk</option>
                  <option value="sip">sip</option>
                </select>
              </Field>
              <Field label="Usuario ONVIF">
                <input style={inputStyle()} value={intercom.onvifUsername || ""} onChange={(e) => patchDoorIntercom(doorIndex, "onvifUsername", e.target.value)} />
              </Field>
              <Field label="Contraseña ONVIF">
                <input style={inputStyle()} type="password" value={intercom.onvifPassword || ""} onChange={(e) => patchDoorIntercom(doorIndex, "onvifPassword", e.target.value)} />
              </Field>
              <Field label="Usuario control puertas">
                <input style={inputStyle()} value={intercom.doorControlUsername || ""} onChange={(e) => patchDoorIntercom(doorIndex, "doorControlUsername", e.target.value)} />
              </Field>
              <Field label="Contraseña control puertas">
                <input style={inputStyle()} type="password" value={intercom.doorControlPassword || ""} onChange={(e) => patchDoorIntercom(doorIndex, "doorControlPassword", e.target.value)} />
              </Field>
              <Field label="Acción apertura">
                <select
                  style={inputStyle()}
                  value={intercom.doorControlAction || "set_output"}
                  onChange={(e) => patchDoorIntercom(doorIndex, "doorControlAction", e.target.value)}
                >
                  <option value="set_output">set_output (OUT)</option>
                  <option value="set_rule">set_rule (regla panel)</option>
                  <option value="door_endpoint">Endpoint pulsadores</option>
                </select>
              </Field>
              {(intercom.doorControlAction || "set_output") === "set_rule" && (
                <Field label="Rule key">
                  <input
                    style={inputStyle()}
                    value={intercom.doorControlRuleKey || ""}
                    onChange={(e) => patchDoorIntercom(doorIndex, "doorControlRuleKey", e.target.value)}
                    placeholder="interfono_puerta_calle_interior"
                  />
                </Field>
              )}
              {(intercom.doorControlAction || "set_output") === "door_endpoint" && (
                <Field label="Endpoint pulsadores (POST)">
                  <input
                    style={inputStyle()}
                    value={intercom.doorControlEndpoint || ""}
                    onChange={(e) => patchDoorIntercom(doorIndex, "doorControlEndpoint", e.target.value)}
                    placeholder={`/api/v1/door/open/p${doorIndex + 1}`}
                  />
                </Field>
              )}
              {(intercom.doorControlAction || "set_output") === "set_output" && (
                <>
                  <Field label="PCB">
                    <input style={inputStyle()} type="number" value={intercom.doorControlPCB ?? 1} onChange={(e) => patchDoorIntercom(doorIndex, "doorControlPCB", Number(e.target.value))} />
                  </Field>
                  <Field label="Switch">
                    <input style={inputStyle()} type="number" value={intercom.doorControlSwitch ?? 1} onChange={(e) => patchDoorIntercom(doorIndex, "doorControlSwitch", Number(e.target.value))} />
                  </Field>
                  <Field label="Modo OUT">
                    <select
                      style={inputStyle()}
                      value={intercom.doorOutputMode || "auto"}
                      onChange={(e) => patchDoorIntercom(doorIndex, "doorOutputMode", e.target.value)}
                    >
                      <option value="auto">Auto (pulso)</option>
                      <option value="manual">Manual</option>
                    </select>
                  </Field>
                </>
              )}
            </div>
          </>
        )}

        {subTab === "modos" && (
          <div style={{ display: "grid", gap: 12 }}>
            {Object.entries(MODE_LABELS).map(([key, label]) => {
              const m = draft.modes?.[key] || {};
              return (
                <div key={key} style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, display: "grid", gap: 8 }}>
                  <div style={{ fontWeight: 700 }}>{label}</div>
                  <div style={grid2}>
                    <Field label="rule_key">
                      <input style={inputStyle()} value={m.rule_key || ""} onChange={(e) => patchMode(key, "rule_key", e.target.value)} />
                    </Field>
                    <Field label="action">
                      <select style={inputStyle()} value={m.action || "set_rule"} onChange={(e) => patchMode(key, "action", e.target.value)}>
                        <option value="set_rule">set_rule</option>
                        <option value="set_output">set_output</option>
                      </select>
                    </Field>
                    <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <input type="checkbox" checked={m.enabled !== false} onChange={(e) => patchMode(key, "enabled", e.target.checked)} />
                      <span>Habilitado en tablet</span>
                    </label>
                    {m.action === "set_output" && (
                      <>
                        <Field label="output_code">
                          <input style={inputStyle()} value={m.output_code || ""} onChange={(e) => patchMode(key, "output_code", e.target.value)} />
                        </Field>
                        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <input type="checkbox" checked={!!m.output_on} onChange={(e) => patchMode(key, "output_on", e.target.checked)} />
                          <span>output_on</span>
                        </label>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {subTab === "emergencia" && (
          <div style={grid2}>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={draft.emergency?.enabled !== false} onChange={(e) => patch("emergency.enabled", e.target.checked)} />
              <span>Emergencia habilitada</span>
            </label>
            <Field label="rule_key">
              <input style={inputStyle()} value={draft.emergency?.rule_key || ""} onChange={(e) => patch("emergency.rule_key", e.target.value)} />
            </Field>
            <Field label="action">
              <select style={inputStyle()} value={draft.emergency?.action || "set_rule"} onChange={(e) => patch("emergency.action", e.target.value)}>
                <option value="set_rule">set_rule</option>
                <option value="set_output">set_output</option>
              </select>
            </Field>
          </div>
        )}

        {subTab === "llamadas" && (
          <div style={grid2}>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={draft.tabletCall?.enabled !== false} onChange={(e) => patch("tabletCall.enabled", e.target.checked)} />
              <span>Llamadas P1 → tablets activas</span>
            </label>
            <Field label="Timeout (segundos)">
              <input style={inputStyle()} type="number" value={draft.tabletCall?.timeoutSeconds ?? 30} onChange={(e) => patch("tabletCall.timeoutSeconds", Number(e.target.value))} />
            </Field>
            <Field label="Modos (rule_key, coma-separados)">
              <input style={inputStyle()} value={draft.tabletCall?.modes || ""} onChange={(e) => patch("tabletCall.modes", e.target.value)} />
            </Field>
            <Field label="Pulsadores (coma-separados)">
              <input style={inputStyle()} value={draft.tabletCall?.pulsadores || "p1"} onChange={(e) => patch("tabletCall.pulsadores", e.target.value)} />
            </Field>
          </div>
        )}

        {subTab === "oficina" && (
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={!!draft.officeWithATM} onChange={(e) => patch("officeWithATM", e.target.checked)} />
            <span>Oficina con cajero (muestra modo «Carga de cajero»)</span>
          </label>
        )}
      </div>
    </div>
  );
}

const grid2 = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
  gap: 12,
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
