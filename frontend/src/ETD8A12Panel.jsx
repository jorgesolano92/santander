import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { clearPanelToken, getPanelToken, getPanelWsLiveUrl } from "./panelAuth";
import { TopNavbar } from "./components/TopNavbar";
import { GlobalLoader } from "./components/GlobalLoader";
import ZaguanEsp32Panel from "./components/zaguan/ZaguanEsp32Panel";
import { HomeZaguanSimulation } from "./components/zaguan/HomeZaguanSimulation";
import TabletConfigPanel from "./components/tablet/TabletConfigPanel";
import SchedulesPanel from "./components/schedules/SchedulesPanel";
import { CoceMessageNotifications } from "./components/CoceMessageNotifications";
import { SoftwareUpdateBanner } from "./components/SoftwareUpdateBanner";
import {
  DEFAULT_MODE_COLORS,
  normalizeRuleColor,
} from "./utils/ruleModeColors";
import { ZAGUAN_LLAVE_ECHADA } from "./components/zaguan/zaguanConstants";
import { ruleBlockersActive } from "./utils/panelRuleBlockers";
import {
  faBolt,
  faBookOpen,
  faCircleCheck,
  faCircleInfo,
  faCircleXmark,
  faClock,
  faCode,
  faCubes,
  faFileImport,
  faFileLines,
  faFloppyDisk,
  faLock,
  faLink,
  faRotateLeft,
  faPenToSquare,
  faPowerOff,
  faSliders,
  faToggleOff,
  faToggleOn,
  faTriangleExclamation,
} from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
const C = {
  red: "var(--template-primary)",
  redDark: "var(--template-primary-dark)",
  redFaint: "var(--template-primary-faint)",
  redBorder: "var(--template-primary-border)",
  white: "#FFFFFF",
  offWhite: "#FAFAFA",
  surface: "#F5F5F5",
  surfaceAlt: "#EEEEEE",
  border: "#E0E0E0",
  borderMid: "#CCCCCC",
  muted: "#999999",
  subtle: "#BBBBBB",
  text: "#1A1A1A",
  textSub: "#555555",
  textMid: "#333333",
  green: "#00873D",
  greenLight: "#E8F5EE",
  greenBorder: "#99DDBB",
  amber: "#C87A00",
  amberLight: "#FFF8E8",
  amberBorder: "#FFCC66",
  blue: "#0066CC",
  blueLight: "#E8F0FF",
};

export const colors = {
  brand: "var(--template-primary)",
  brandDark: "var(--template-primary-dark)",
  brandLight: "var(--template-primary-faint)",
  bg: "#F5F5F5",
  white: "#FFFFFF",
  border: "#E0E0E0",
  text: "#111827",
  textSecondary: "#6B7280",
  success: "#22C55E",
  warning: "#F59E0B",
  danger: "#DC2626",
};

const API = "/api/panel";
const RULES_JSON_STORAGE_KEY = "panel_rules_json_draft";
/** Preset 1: Invia (diseño actual — azul corporativo). */
const DEFAULT_TEMPLATE_CONFIG_1 = {
  mainLogo: "/assets/invia-logo.png",
  boardLogo: "/assets/invia-board-logo.png",
  primaryColor: "#2D309A",
};

/** Preset 2: Santander (rojo corporativo). */
const DEFAULT_TEMPLATE_CONFIG_2 = {
  mainLogo: "/assets/logo.png",
  boardLogo: "/assets/santander-logo.png",
  primaryColor: "#E50914",
};

const DEFAULT_TEMPLATE_CONFIG = DEFAULT_TEMPLATE_CONFIG_1;

/** Enclavamientos interruptor (verde, cierres, apertura remota COCE…), no horarios ni incendio. */
function isToggleEnclavamiento(ruleKey, rule) {
  if (!rule || rule.type !== "enclavamiento") return false;
  if (ruleKey.startsWith("horario_")) return false;
  if (ruleKey === "senal_de_incendio_activada") return false;
  return true;
}

/** Modos operativos globales (horarios + señal de incendio), no interruptores. */
function isOperativePanelMode(ruleKey) {
  return (
    typeof ruleKey === "string" &&
    (ruleKey.startsWith("horario_") || ruleKey === "senal_de_incendio_activada")
  );
}

function applyAutoRulesPanelFeedback(res, addUI, setActiveToggleRules) {
  if (Array.isArray(res?.active_toggle_rules) && setActiveToggleRules) {
    setActiveToggleRules(res.active_toggle_rules);
  }
  const linkedOn = res?.also_execute_results;
  if (Array.isArray(linkedOn) && setActiveToggleRules) {
    setActiveToggleRules((prev) => {
      const s = new Set(prev);
      for (const item of linkedOn) {
        if (!item.rule) continue;
        if (
          item.executed &&
          (item.toggle_active || item.toggle_action === "on")
        ) {
          s.add(item.rule);
        }
      }
      return [...s];
    });
  }
  if (Array.isArray(linkedOn)) {
    for (const item of linkedOn) {
      const rk = item.rule || "?";
      const label = rk.replaceAll("_", " ");
      if (item.executed) {
        addUI("OK", `Vinculada activada: ${label}`);
      } else if (item.reason || item.error) {
        addUI(
          "WARN",
          `Vinculada ${label} no ejecutada: ${item.reason || item.error}`,
        );
      }
    }
  }
  const linkedOff = res?.also_deactivate_results;
  if (Array.isArray(linkedOff) && setActiveToggleRules) {
    setActiveToggleRules((prev) => {
      const s = new Set(prev);
      for (const item of linkedOff) {
        if (item.rule && item.executed) s.delete(item.rule);
      }
      return [...s];
    });
  }
  if (Array.isArray(linkedOff)) {
    for (const item of linkedOff) {
      if (!item.executed) continue;
      const rk = item.rule || "?";
      addUI("INFO", `Vinculada desactivada: ${rk.replaceAll("_", " ")}`);
    }
  }
  const blocked = res?.auto_rules?.blocked_rules;
  if (!Array.isArray(blocked)) return;
  for (const b of blocked) {
    const reason = String(b.reason || "");
    if (!reason.includes("Bloqueado")) continue;
    const ins = (b.blocked_inputs || []).join(", ");
    const rk = b.rule_key || "regla";
    addUI("WARN", `${rk} bloqueado por ${ins}`);
  }
}
/** Unit ID Modbus 0-255; no usar `n || 1` (0 válido; NaN no debe volverse 1). */
function normalizeSlaveId(raw, fallback = 1) {
  const s = parseInt(String(raw).trim(), 10);
  return Number.isFinite(s) && s >= 0 && s <= 255 ? s : fallback;
}
const TABS = [
  "Panel",
  "Placas I/O",
  "Histórico",
  "Configuración Modos",
  "Definición placas",
  "Configuración pulsadores",
  "Configuración template",
  "Configuración tablet",
  "Horarios",
];
const HISTORICO_TAB_INDEX = TABS.indexOf("Histórico");

function histDateToFromIso(dateStr) {
  if (!dateStr) return null;
  const d = new Date(`${dateStr}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

function histDateToToIso(dateStr) {
  if (!dateStr) return null;
  const d = new Date(`${dateStr}T23:59:59.999`);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

function buildHistoricoQueryParams({
  dateFrom,
  dateTo,
  typeFilter,
  limit = 500,
}) {
  const params = new URLSearchParams({ limit: String(limit) });
  const fromIso = histDateToFromIso(dateFrom);
  const toIso = histDateToToIso(dateTo);
  if (fromIso) params.set("from_date", fromIso);
  if (toIso) params.set("to_date", toIso);
  if (typeFilter && typeFilter !== "ALL") params.set("type", typeFilter);
  return params;
}

function normalizeHexColor(
  raw,
  fallback = DEFAULT_TEMPLATE_CONFIG.primaryColor,
) {
  const value = String(raw || "").trim();
  if (/^#[0-9a-f]{6}$/i.test(value)) return value;
  return fallback;
}

function hexToRgb(hex) {
  const normalized = normalizeHexColor(hex).slice(1);
  return {
    r: parseInt(normalized.slice(0, 2), 16),
    g: parseInt(normalized.slice(2, 4), 16),
    b: parseInt(normalized.slice(4, 6), 16),
  };
}

function mixHex(hex, target, amount) {
  const a = hexToRgb(hex);
  const b = hexToRgb(target);
  const mix = (x, y) => Math.round(x + (y - x) * amount);
  return `#${[mix(a.r, b.r), mix(a.g, b.g), mix(a.b, b.b)]
    .map((n) => n.toString(16).padStart(2, "0"))
    .join("")}`;
}

function templateColors(config) {
  const primary = normalizeHexColor(
    config.primaryColor || DEFAULT_TEMPLATE_CONFIG.primaryColor,
  );
  return {
    primary,
    primaryDark: mixHex(primary, "#000000", 0.25),
    primaryFaint: mixHex(primary, "#ffffff", 0.9),
    primaryBorder: mixHex(primary, "#ffffff", 0.65),
  };
}

function readImageAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    if (!file) {
      resolve("");
      return;
    }
    if (!file.type.startsWith("image/")) {
      reject(new Error("El archivo debe ser una imagen"));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("No se pudo leer la imagen"));
    reader.readAsDataURL(file);
  });
}

function displayLogoValue(value, fallback) {
  if (!value) return fallback;
  if (String(value).startsWith("data:image/"))
    return "Imagen subida localmente";
  return value;
}

const IN_PLACEHOLDERS = Array.from(
  { length: 12 },
  (_, i) => `0x${(0x0080 + i).toString(16).toUpperCase().padStart(4, "0")}`,
);
const OUT_PLACEHOLDERS = Array.from(
  { length: 12 },
  (_, i) => `0x${(0x0000 + i).toString(16).toUpperCase().padStart(4, "0")}`,
);

const Dot = ({ active, color, size = 8 }) => (
  <div
    style={{
      width: size,
      height: size,
      borderRadius: "50%",
      background: active ? color : C.surfaceAlt,
      border: `1.5px solid ${active ? color : C.border}`,
    }}
  />
);
const Card = ({ children, style }) => (
  <div
    style={{
      background: C.white,
      border: `1px solid ${C.border}`,
      borderRadius: 20,
      padding: 18,
      ...style,
    }}
  >
    {children}
  </div>
);
const SecLabel = ({ children }) => (
  <div
    style={{
      fontSize: 13,
      fontWeight: 700,
      padding: "10px 10px",
      letterSpacing: 1.5,
      textTransform: "uppercase",
      marginBottom: 12,
      borderBottom: `2px solid ${C.border}`,
      background: `linear-gradient(90deg, ${C.red} 0%, ${C.redDark} 100%)`,
      WebkitBackgroundClip: "text",
      WebkitTextFillColor: "transparent",
      backgroundClip: "text",
      color: "transparent",
    }}
  >
    {children}
  </div>
);
const Btn = ({
  children,
  onClick,
  disabled,
  small,
  variant = "ghost",
  full,
}) => {
  const s = {
    primary: {
      background: C.red,
      color: C.white,
      border: `1px solid ${C.redDark}`,
    },
    ghost: {
      background: C.white,
      color: C.textMid,
      border: `1px solid ${C.border}`,
    },
    danger: {
      background: C.redFaint,
      color: C.red,
      border: `1px solid ${C.redBorder}`,
    },
    success: {
      background: C.greenLight,
      color: C.green,
      border: `1px solid ${C.greenBorder}`,
    },
  }[variant];
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        ...s,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        fontFamily: "inherit",
        fontSize: small ? 11 : 13,
        fontWeight: 600,
        padding: small ? "4px 10px" : "9px 16px",
        borderRadius: 8,
        boxShadow:
          variant === "primary" ? "0 1px 3px rgba(0,0,0,0.12)" : undefined,
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
        width: full ? "100%" : undefined,
      }}
    >
      {children}
    </button>
  );
};

function ImageFilePicker({ onSelect, label = "Seleccionar imagen" }) {
  const inputRef = useRef(null);
  return (
    <div style={{ marginTop: 8 }}>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        aria-hidden
        tabIndex={-1}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onSelect(file);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
          fontFamily: "inherit",
          fontSize: 13,
          fontWeight: 600,
          padding: "9px 16px",
          borderRadius: 8,
          cursor: "pointer",
          background: C.red,
          color: C.white,
          border: `1px solid ${C.redDark}`,
          boxShadow: "0 1px 3px rgba(0,0,0,0.12)",
        }}
      >
        <FontAwesomeIcon icon={faFileImport} aria-hidden />
        {label}
      </button>
    </div>
  );
}

function TemplateConfigPanel({
  draft,
  colors: themeColors,
  onChange,
  onUploadMainLogo,
  onUploadBoardLogo,
  onSave,
  onReset1,
  onReset2,
}) {
  const fieldStyle = {
    width: "100%",
    padding: "8px 10px",
    border: `1px solid ${C.border}`,
    borderRadius: 8,
    fontSize: 13,
  };
  const labelStyle = {
    fontSize: 11,
    color: C.muted,
    marginBottom: 5,
    fontWeight: 600,
  };

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(320px, 0.95fr) minmax(360px, 1.05fr)",
        gap: 12,
        alignItems: "start",
      }}
    >
      <Card>
        <SecLabel>Configuración de template</SecLabel>
        <div style={{ display: "grid", gap: 14 }}>
          <div>
            <div style={labelStyle}>Logo principal (ruta en assets)</div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 12,
                padding: 16,
                border: `1px solid ${C.border}`,
                borderRadius: 12,
                background: C.white,
                boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
                marginBottom: 12,
              }}
            >
              <div
                style={{
                  width: "40%",
                  height: 180,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: C.surfaceAlt,
                  borderRadius: 8,
                  border: `1px dashed ${C.borderMid}`,
                }}
              >
                <img
                  src={draft.mainLogo || DEFAULT_TEMPLATE_CONFIG.mainLogo}
                  alt="Vista previa logo principal"
                  style={{
                    maxWidth: "100%",
                    maxHeight: "100%",
                    objectFit: "contain",
                  }}
                  onError={(e) => {
                    e.currentTarget.src = DEFAULT_TEMPLATE_CONFIG.mainLogo;
                  }}
                />
              </div>
              <div style={{ fontSize: 12, color: C.textSub, fontWeight: 600 }}>
                {displayLogoValue(
                  draft.mainLogo,
                  DEFAULT_TEMPLATE_CONFIG.mainLogo,
                )}
              </div>
            </div>
            <input
              value={
                String(draft.mainLogo || "").startsWith("data:image/")
                  ? ""
                  : draft.mainLogo
              }
              onChange={(e) => onChange({ mainLogo: e.target.value })}
              placeholder="/assets/invia-logo.png"
              style={fieldStyle}
            />
            <ImageFilePicker
              label="Seleccionar imagen"
              onSelect={onUploadMainLogo}
            />
            <div style={{ fontSize: 11, color: C.muted, marginTop: 5 }}>
              Guarda el archivo en <code>frontend/public/assets</code> y usa una
              ruta como <code>/assets/logo-cliente.png</code>, o súbelo desde
              este campo para guardarlo localmente.
            </div>
          </div>

          <div>
            <div style={labelStyle}>Logo pequeño de placas</div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: 10,
                border: `1px solid ${C.border}`,
                borderRadius: 10,
                background: C.offWhite,
                marginBottom: 8,
              }}
            >
              <img
                src={draft.boardLogo || DEFAULT_TEMPLATE_CONFIG.boardLogo}
                alt="Vista previa logo placa"
                style={{ width: 80, height: 80, objectFit: "contain" }}
                onError={(e) => {
                  e.currentTarget.src = DEFAULT_TEMPLATE_CONFIG.boardLogo;
                }}
              />
              <span style={{ fontSize: 12, color: C.textSub }}>
                {displayLogoValue(
                  draft.boardLogo,
                  DEFAULT_TEMPLATE_CONFIG.boardLogo,
                )}
              </span>
            </div>
            <input
              value={
                String(draft.boardLogo || "").startsWith("data:image/")
                  ? ""
                  : draft.boardLogo
              }
              onChange={(e) => onChange({ boardLogo: e.target.value })}
              placeholder="/assets/santander-logo.png"
              style={fieldStyle}
            />
            <ImageFilePicker
              label="Seleccionar imagen"
              onSelect={onUploadBoardLogo}
            />
          </div>

          <div>
            <div style={labelStyle}>Color principal</div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="color"
                value={normalizeHexColor(draft.primaryColor)}
                onChange={(e) => onChange({ primaryColor: e.target.value })}
                style={{
                  width: 54,
                  height: 38,
                  border: `1px solid ${C.border}`,
                  borderRadius: 8,
                  padding: 2,
                  background: C.white,
                }}
              />
              <input
                value={draft.primaryColor}
                onChange={(e) => onChange({ primaryColor: e.target.value })}
                placeholder="#E50914"
                style={fieldStyle}
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Btn variant="primary" onClick={onSave}>
              <FontAwesomeIcon icon={faFloppyDisk} aria-hidden />
              Guardar template
            </Btn>
            <Btn onClick={onReset1}>
              <FontAwesomeIcon icon={faRotateLeft} aria-hidden />
              Restaurar Invia (por defecto 1)
            </Btn>
            <Btn onClick={onReset2}>
              <FontAwesomeIcon icon={faRotateLeft} aria-hidden />
              Restaurar Santander (por defecto 2)
            </Btn>
          </div>
        </div>
      </Card>

      <Card>
        <SecLabel>Vista previa</SecLabel>
        <div
          style={{
            border: `1px solid ${C.border}`,
            borderRadius: 14,
            overflow: "hidden",
            background: C.white,
          }}
        >
          <div
            style={{
              minHeight: 58,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 16,
              padding: "10px 16px",
              color: C.white,
              background: `linear-gradient(90deg, ${themeColors.primary} 0%, ${themeColors.primaryDark} 100%)`,
            }}
          >
            <img
              src={draft.mainLogo || DEFAULT_TEMPLATE_CONFIG.mainLogo}
              alt="Logo principal"
              style={{ width: 120, height: 36, objectFit: "contain" }}
              onError={(e) => {
                e.currentTarget.src = DEFAULT_TEMPLATE_CONFIG.mainLogo;
              }}
            />
            <span style={{ fontWeight: 700 }}>Control de Accesos</span>
          </div>

          <div style={{ padding: 16 }}>
            <div
              style={{
                border: `1px solid ${C.border}`,
                borderLeft: `4px solid ${themeColors.primary}`,
                borderRadius: 10,
                padding: 12,
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <img
                src={draft.boardLogo || DEFAULT_TEMPLATE_CONFIG.boardLogo}
                alt="Logo placa"
                style={{ width: 28, height: 28, objectFit: "contain" }}
                onError={(e) => {
                  e.currentTarget.src = DEFAULT_TEMPLATE_CONFIG.boardLogo;
                }}
              />
              <div>
                <div style={{ fontWeight: 700, color: C.textMid }}>
                  Placa 1 - Central
                </div>
                <div style={{ color: C.muted, fontSize: 12 }}>
                  Ejemplo de tarjeta de placa
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}

async function apiFetch(path, opts = {}) {
  const { timeoutMs, ...fetchOpts } = opts;
  const useTimeout =
    typeof timeoutMs === "number" && timeoutMs > 0 && !fetchOpts.signal;
  const controller = useTimeout ? new AbortController() : null;
  const timer = useTimeout
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;
  const token = getPanelToken();
  const headers = {
    "Content-Type": "application/json",
    ...(fetchOpts.headers || {}),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  try {
    const url = path.startsWith("/api") ? path : `${API}${path}`;
    const res = await fetch(url, {
      ...fetchOpts,
      headers,
      ...(useTimeout ? { signal: controller.signal } : {}),
    });
    if (res.status === 401) {
      clearPanelToken();
      window.location.assign("/login");
      throw new Error("Sesión caducada o no autorizado");
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Error");
    }
    return res.json();
  } catch (e) {
    if (e?.name === "AbortError") {
      throw new Error(
        "Tiempo de espera agotado (el servidor o Modbus tardaron demasiado)",
      );
    }
    throw e;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function apiFetchZaguan(path, opts = {}) {
  const token = getPanelToken();
  const headers = {
    "Content-Type": "application/json",
    ...(opts.headers || {}),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(path, {
    ...opts,
    headers,
  });
  if (res.status === 401) {
    clearPanelToken();
    window.location.assign("/login");
    throw new Error("Sesión caducada o no autorizado");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Error");
  }
  return res.json();
}

function parseAddrStr(s) {
  const t = String(s).trim();
  if (!t) return NaN;
  return /^0x/i.test(t) ? parseInt(t, 16) : parseInt(t, 10);
}

function fmtHex(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `0x${Number(n).toString(16).toUpperCase()}`;
}

function moduleEditorKey(mod) {
  const ik = (mod.inputs || []).map((c) => c.id).join("-");
  const ok = (mod.outputs || []).map((c) => c.id).join("-");
  return `${mod.id}|${ik}|${ok}`;
}

/** Clave JSON: minúsculas, sin acentos, espacios → guión bajo (p. ej. "Horario Automático" → horario_automatico). */
function slugRuleKey(displayName) {
  const s = String(displayName || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
  const slug = s.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return slug || "regla_sin_nombre";
}

function inputChannelState(board, index) {
  const forced = board.input_overrides?.[index];
  const isForced = forced !== null && forced !== undefined;
  const raw = board.inputs_raw?.[index] ?? board.inputs?.[index] ?? false;
  const effective = isForced ? forced : (board.inputs?.[index] ?? raw);
  return {
    effective: Boolean(effective),
    raw: Boolean(raw),
    isForced,
    forcedOn: forced === true,
    forcedOff: forced === false,
    activeByOverride: isForced && effective === true,
  };
}

function formatEventDateTime(e) {
  const raw = e?.date || e?.created_at;
  if (raw) {
    const d = new Date(raw);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleString("es-ES", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
    }
  }
  return e?.ts || "";
}

function formatIoSlot(kind, index, { padded = false } = {}) {
  const n = index + 1;
  const prefix = kind === "input" ? "IN" : "OUT";
  return padded ? `${prefix}${String(n).padStart(2, "0")}` : `${prefix}${n}`;
}

function formatBoardLabel(mod) {
  return (mod.name || `Placa ${mod.id}`).replace(/\s*[—–]\s*/g, " - ");
}

function buildIoOptionLabel(mod, ch, kind, index) {
  const board = formatBoardLabel(mod);
  const name = (ch.channel_name || "").trim();
  const slot = formatIoSlot(kind, index, { padded: Boolean(name) });
  if (name) return `${board} - ${name} - ${slot}`;
  return `${board} - ${slot}`;
}

function channelIoTitle(kind, index, channel, opts = {}) {
  const name = (channel?.channel_name || "").trim();
  let base = name
    ? `${formatIoSlot(kind, index, { padded: true })}: ${name}`
    : formatIoSlot(kind, index, { padded: false });
  if (opts.activeByOverride) base += " (override)";
  return base;
}

function buildIoOptions(moduleList) {
  const ins = [];
  const outs = [];
  for (const mod of moduleList || []) {
    const yy = String(mod.id).padStart(2, "0");
    (mod.inputs || []).forEach((ch, idx) => {
      const zz = String(idx + 1).padStart(2, "0");
      ins.push({
        code: `IN_${yy}_${zz}`,
        label: buildIoOptionLabel(mod, ch, "input", idx),
      });
    });
    (mod.outputs || []).forEach((ch, idx) => {
      const zz = String(idx + 1).padStart(2, "0");
      outs.push({
        code: `OUT_${yy}_${zz}`,
        label: buildIoOptionLabel(mod, ch, "output", idx),
      });
    });
  }
  return { ins, outs };
}

function ChipList({ items, onRemove, C, labelByCode }) {
  if (!items.length)
    return (
      <span
        style={{
          fontSize: 12,
          color: C.muted,
          fontStyle: "italic",
        }}
      >
        Ninguno
      </span>
    );
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {items.map((code) => (
        <span
          key={code}
          style={{
            fontSize: 11,
            padding: "6px 10px",
            borderRadius: 8,
            background: C.white,
            border: `1px solid ${C.border}`,
            fontFamily: labelByCode?.[code] ? "inherit" : "Consolas, monospace",
            color: C.textMid,
            boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
          }}
        >
          {labelByCode?.[code] || code}
          <button
            type="button"
            onClick={() => onRemove(code)}
            style={{
              marginLeft: 8,
              border: "none",
              background: "none",
              cursor: "pointer",
              color: C.red,
              fontWeight: 700,
              fontSize: 14,
              lineHeight: 1,
              verticalAlign: "middle",
            }}
          >
            ×
          </button>
        </span>
      ))}
    </div>
  );
}

function RulesFormAssistant({
  moduleList,
  rulesJson,
  setRulesJson,
  rulesMap,
  setRulesMap,
  addUI,
  setSelectedMode,
}) {
  const { ins, outs } = useMemo(() => buildIoOptions(moduleList), [moduleList]);
  const ioLabelByCode = useMemo(() => {
    const m = {};
    for (const o of [...ins, ...outs]) m[o.code] = o.label;
    return m;
  }, [ins, outs]);
  const [wfName, setWfName] = useState("");
  const [wfTrigger, setWfTrigger] = useState("");
  const [wfBlocked, setWfBlocked] = useState([]);
  const [wfDeactivate, setWfDeactivate] = useState([]);
  const [wfAlsoTriggers, setWfAlsoTriggers] = useState([]);
  const [wfAlsoExecuteRules, setWfAlsoExecuteRules] = useState([]);
  const [wfActOut, setWfActOut] = useState([]);
  const [wfDeactOut, setWfDeactOut] = useState([]);
  /** Si true → JSON `deactivate_outputs_temporary`: al soltar la regla, restaura OUT que estaban ON. */
  const [wfDeactTemporary, setWfDeactTemporary] = useState(false);
  const [wfEnabled, setWfEnabled] = useState(true);
  const [wfAuto, setWfAuto] = useState(true);
  const [wfColor, setWfColor] = useState("#22c55e");
  const [wfType, setWfType] = useState("enclavamiento");
  /** 0 = seguir nivel IN; >0 = pulso temporizado (s). Omisión en JSON = 0 en backend (detección). */
  const [wfPulseSeconds, setWfPulseSeconds] = useState(0);
  const [loadKey, setLoadKey] = useState("");
  const [pickBl, setPickBl] = useState("");
  const [pickDeact, setPickDeact] = useState("");
  const [pickAlsoTrigger, setPickAlsoTrigger] = useState("");
  const [pickAlsoRule, setPickAlsoRule] = useState("");
  const [pickOutOn, setPickOutOn] = useState("");
  const [pickOutOff, setPickOutOff] = useState("");

  const assistIcon = (icon, color = C.textSub) => (
    <FontAwesomeIcon icon={icon} style={{ color, width: 14 }} />
  );

  const slugPreview = useMemo(() => slugRuleKey(wfName), [wfName]);

  useEffect(() => {
    if (!ins.length) return;
    if (!wfTrigger || !ins.some((o) => o.code === wfTrigger)) {
      setWfTrigger(ins[0].code);
    }
  }, [ins, wfTrigger]);

  const mergeToJson = () => {
    if (!wfName.trim()) {
      addUI(
        "ERR",
        "Indica un nombre para el modo (se usará para la clave JSON).",
      );
      return;
    }
    if (ins.length && !wfTrigger) {
      addUI("ERR", "Elige un disparador IN.");
      return;
    }
    const key = slugPreview;
    const rule = {
      enabled: wfEnabled,
      auto_execute: wfAuto,
      color: normalizeRuleColor(wfColor, key),
      type: wfType,
      trigger: wfTrigger,
      blocked_if_active: [...wfBlocked],
      deactivate_modes: [...wfDeactivate],
      activate_outputs: [...wfActOut],
      deactivate_outputs: [...wfDeactOut],
    };
    if (wfAlsoTriggers.length) {
      rule.also_triggers = [...wfAlsoTriggers];
    }
    if (wfAlsoExecuteRules.length) {
      rule.also_execute_rules = [...wfAlsoExecuteRules];
    }
    if (wfDeactTemporary) {
      rule.deactivate_outputs_temporary = true;
    }
    if (wfType === "pulso_5_sg") {
      const n = parseInt(String(wfPulseSeconds).trim(), 10);
      rule.pulse_seconds = Number.isFinite(n)
        ? Math.min(300, Math.max(0, n))
        : 0;
    }
    let parsed = {};
    try {
      parsed = JSON.parse(rulesJson || "{}");
    } catch {
      addUI(
        "ERR",
        "El JSON del editor no es válido; corrígelo antes de fusionar.",
      );
      return;
    }
    parsed[key] = rule;
    setRulesMap(parsed);
    setRulesJson(JSON.stringify(parsed, null, 2));
    setSelectedMode(key);
    addUI(
      "OK",
      `Regla «${key}» generada y fusionada al editor (guarda en servidor cuando quieras).`,
    );
  };

  const loadFromKey = () => {
    const r = rulesMap[loadKey];
    if (!r || typeof r !== "object") {
      addUI("ERR", "Elige una regla existente");
      return;
    }
    setWfName(loadKey.replace(/_/g, " "));
    setWfTrigger(
      typeof r.trigger === "string" ? r.trigger : ins[0]?.code || "",
    );
    setWfBlocked(
      Array.isArray(r.blocked_if_active) ? [...r.blocked_if_active] : [],
    );
    setWfDeactivate(
      Array.isArray(r.deactivate_modes) ? [...r.deactivate_modes] : [],
    );
    setWfAlsoTriggers(
      Array.isArray(r.also_triggers) ? [...r.also_triggers] : [],
    );
    setWfAlsoExecuteRules(
      Array.isArray(r.also_execute_rules) ? [...r.also_execute_rules] : [],
    );
    setWfActOut(
      Array.isArray(r.activate_outputs) ? [...r.activate_outputs] : [],
    );
    setWfDeactOut(
      Array.isArray(r.deactivate_outputs) ? [...r.deactivate_outputs] : [],
    );
    setWfDeactTemporary(Boolean(r.deactivate_outputs_temporary));
    setWfEnabled(r.enabled !== false);
    setWfAuto(r.auto_execute !== false);
    setWfColor(normalizeRuleColor(r.color, loadKey));
    setWfType(typeof r.type === "string" ? r.type : "enclavamiento");
    const ps = r.pulse_seconds;
    if (ps !== undefined && ps !== null && ps !== "") {
      const n = parseInt(String(ps), 10);
      setWfPulseSeconds(Number.isFinite(n) ? Math.min(300, Math.max(0, n)) : 0);
    } else {
      setWfPulseSeconds(0);
    }
    addUI("INFO", `Formulario cargado desde «${loadKey}»`);
  };

  const ruleKeys = Object.keys(rulesMap || {});

  const assistLbl = {
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 0.5,
    textTransform: "uppercase",
    color: C.textSub,
    marginBottom: 6,
  };
  const assistSection = {
    marginBottom: 14,
    padding: "14px 16px",
    background: C.white,
    border: `1px solid ${C.border}`,
    borderRadius: 10,
    boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
  };
  const assistIntro = {
    fontSize: 12,
    color: C.textSub,
    lineHeight: 1.55,
    marginBottom: 16,
    padding: "12px 14px",
    background: C.offWhite,
    border: `1px solid ${C.border}`,
    borderRadius: 10,
  };
  const assistOptionsBar = {
    display: "flex",
    gap: 16,
    flexWrap: "wrap",
    alignItems: "center",
    marginBottom: 14,
    padding: "12px 14px",
    background: C.surface,
    border: `1px solid ${C.border}`,
    borderRadius: 10,
  };
  const assistChk = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 13,
    fontWeight: 600,
    color: C.textMid,
    cursor: "pointer",
  };

  return (
    <Card style={{ flex: "1 1 100%", marginBottom: 12 }}>
      <SecLabel>Crear modo (JSON de reglas)</SecLabel>
      <div style={assistIntro}>
        El nombre del script se convierte en clave JSON (ej.{" "}
        <strong style={{ color: C.textMid }}>Horario Automático</strong> →{" "}
        <code
          style={{
            fontSize: 11,
            padding: "2px 6px",
            borderRadius: 4,
            background: C.white,
            border: `1px solid ${C.border}`,
            color: C.red,
          }}
        >
          horario_automatico
        </code>
        ). Los códigos siguen el mapa de tus placas (
        <span style={{ fontFamily: "monospace", fontSize: 11 }}>IN_YY_ZZ</span>{" "}
        /{" "}
        <span style={{ fontFamily: "monospace", fontSize: 11 }}>OUT_YY_ZZ</span>
        ).
      </div>
      {ruleKeys.length > 0 && (
        <div
          style={{
            ...assistSection,
            display: "flex",
            gap: 12,
            flexWrap: "wrap",
            alignItems: "flex-end",
          }}
        >
          <div style={{ flex: "1 1 220px" }}>
            <div
              style={{
                ...assistLbl,
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              {assistIcon(faBookOpen)}
              Cargar regla existente
            </div>
            <select
              className="rules-assist-control"
              value={loadKey}
              onChange={(e) => setLoadKey(e.target.value)}
              style={{ width: "100%", minWidth: 200 }}
            >
              <option value="">—</option>
              {ruleKeys.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </div>
          <Btn small onClick={loadFromKey} disabled={!loadKey}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <FontAwesomeIcon icon={faFileImport} />
              Rellenar formulario
            </span>
          </Btn>
        </div>
      )}
      <div
        style={{
          ...assistSection,
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,
        }}
      >
        <div>
          <div
            style={{
              ...assistLbl,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            {assistIcon(faFileLines)}
            Nombre del modo
          </div>
          <input
            className="rules-assist-control"
            value={wfName}
            onChange={(e) => setWfName(e.target.value)}
            placeholder="Ej. exclusa, horario cerrado…"
            style={{ width: "100%" }}
          />
          <div style={{ fontSize: 11, color: C.muted, marginTop: 8 }}>
            Clave JSON:{" "}
            <code
              style={{
                fontSize: 11,
                padding: "2px 6px",
                borderRadius: 4,
                background: C.surfaceAlt,
                color: C.textMid,
              }}
            >
              {wfName.trim() ? slugPreview : "— (nombre pendiente)"}
            </code>
          </div>
        </div>
        <div>
          <div
            style={{
              ...assistLbl,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            {assistIcon(faBolt, C.red)}
            Disparador (trigger IN)
          </div>
          <select
            className="rules-assist-control"
            value={wfTrigger}
            onChange={(e) => setWfTrigger(e.target.value)}
            style={{ width: "100%" }}
          >
            {ins.map((o) => (
              <option key={o.code} value={o.code}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div style={assistOptionsBar}>
        <label style={assistChk}>
          <FontAwesomeIcon icon={faCircleCheck} style={{ color: C.green }} />
          <input
            type="checkbox"
            checked={wfEnabled}
            onChange={(e) => setWfEnabled(e.target.checked)}
          />
          Habilitada
        </label>
        <label style={assistChk}>
          <FontAwesomeIcon icon={faClock} style={{ color: C.amber }} />
          <input
            type="checkbox"
            checked={wfAuto}
            onChange={(e) => setWfAuto(e.target.checked)}
          />
          Auto-ejecutar (polling)
        </label>
        <label
          style={{
            ...assistChk,
            gap: 10,
          }}
          title="Color en la línea de tiempo de horarios"
        >
          <span style={{ fontSize: 10, fontWeight: 700, color: C.textSub }}>
            COLOR
          </span>
          <input
            type="color"
            value={normalizeHexColor(
              wfColor,
              DEFAULT_MODE_COLORS.horario_automatico,
            )}
            onChange={(e) => setWfColor(e.target.value)}
            style={{
              width: 44,
              height: 32,
              border: `1px solid ${C.border}`,
              borderRadius: 8,
              padding: 2,
              background: C.white,
              cursor: "pointer",
            }}
          />
          <input
            className="rules-assist-control"
            value={wfColor}
            onChange={(e) => setWfColor(e.target.value)}
            placeholder="#22c55e"
            style={{ width: 88, fontFamily: "monospace", fontSize: 12 }}
          />
        </label>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginLeft: "auto",
          }}
        >
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: C.textSub,
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <FontAwesomeIcon icon={faSliders} />
            TIPO
          </span>
          <select
            className="rules-assist-control"
            value={wfType}
            onChange={(e) => setWfType(e.target.value)}
            style={{ minWidth: 160 }}
          >
            <option value="enclavamiento">enclavamiento</option>
            <option value="manual">manual</option>
            <option value="pulso_5_sg">
              radar / pulso (0=detectar, N s=pulso)
            </option>
          </select>
        </div>
      </div>

      {wfType === "pulso_5_sg" && (
        <div style={{ ...assistSection, marginTop: -6, marginBottom: 8 }}>
          <div style={{ fontSize: 11, color: C.textSub, marginBottom: 6 }}>
            <code>pulse_seconds</code>: <strong>0</strong> = salida sigue al IN
            mientras detecte (y bloqueos); <strong>1–300</strong> = pulso en
            segundos tras flanco de subida (sin clave en JSON el backend usa 0 =
            detección).
          </div>
          <label
            style={{
              fontSize: 12,
              color: C.textMid,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            Segundos (0 = detectar)
            <input
              type="number"
              min={0}
              max={300}
              className="rules-assist-control"
              value={wfPulseSeconds}
              onChange={(e) => setWfPulseSeconds(Number(e.target.value))}
              style={{ width: 80 }}
            />
          </label>
        </div>
      )}

      <div style={assistSection}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 10,
            paddingLeft: 10,
            borderLeft: `3px solid ${C.amber}`,
          }}
        >
          <FontAwesomeIcon
            icon={faLink}
            style={{ color: C.amber, fontSize: 14 }}
          />
          <span
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: C.textMid,
              lineHeight: 1.35,
            }}
          >
            Vínculos (activar IN o reglas adicionales a la vez)
          </span>
        </div>
        <p
          style={{
            fontSize: 11,
            color: C.textSub,
            lineHeight: 1.5,
            margin: "0 0 12px",
          }}
        >
          <strong>IN vinculados</strong> (<code>also_triggers</code>): al
          ejecutar esta regla, los pulsadores indicados quedan activos junto con
          el disparador principal (p. ej. IN6 placa 2 + IN6 placa 3 en
          emergencia). <strong>Reglas vinculadas</strong> (
          <code>also_execute_rules</code>): ejecuta otra actuación completa en
          el mismo momento.
        </p>
        <div style={{ ...assistLbl, marginBottom: 6 }}>IN vinculados</div>
        <div style={{ marginBottom: 10, minHeight: 28 }}>
          <ChipList
            items={wfAlsoTriggers}
            onRemove={(c) =>
              setWfAlsoTriggers(wfAlsoTriggers.filter((x) => x !== c))
            }
            C={C}
            labelByCode={ioLabelByCode}
          />
        </div>
        <select
          className="rules-assist-control"
          value={pickAlsoTrigger}
          onChange={(e) => {
            const v = e.target.value;
            if (!v) return;
            setWfAlsoTriggers((prev) =>
              prev.includes(v) ? prev : [...prev, v],
            );
            setPickAlsoTrigger("");
          }}
          style={{ width: "100%", minWidth: 200, marginBottom: 14 }}
        >
          <option value="">Añadir IN vinculado…</option>
          {ins
            .filter(
              (o) => o.code !== wfTrigger && !wfAlsoTriggers.includes(o.code),
            )
            .map((o) => (
              <option key={o.code} value={o.code}>
                {o.label}
              </option>
            ))}
        </select>
        <div style={{ ...assistLbl, marginBottom: 6 }}>Reglas vinculadas</div>
        <div style={{ marginBottom: 10, minHeight: 28 }}>
          <ChipList
            items={wfAlsoExecuteRules}
            onRemove={(c) =>
              setWfAlsoExecuteRules(wfAlsoExecuteRules.filter((x) => x !== c))
            }
            C={C}
            labelByCode={(k) => k.replace(/_/g, " ")}
          />
        </div>
        <select
          className="rules-assist-control"
          value={pickAlsoRule}
          onChange={(e) => {
            const v = e.target.value;
            if (!v) return;
            setWfAlsoExecuteRules((prev) =>
              prev.includes(v) ? prev : [...prev, v],
            );
            setPickAlsoRule("");
          }}
          style={{ width: "100%", minWidth: 200 }}
        >
          <option value="">Añadir regla vinculada…</option>
          {ruleKeys
            .filter((k) => k !== slugPreview && !wfAlsoExecuteRules.includes(k))
            .map((k) => (
              <option key={k} value={k}>
                {k.replace(/_/g, " ")}
              </option>
            ))}
        </select>
      </div>

      <div style={assistSection}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 10,
            paddingLeft: 10,
            borderLeft: `3px solid ${C.red}`,
          }}
        >
          <FontAwesomeIcon
            icon={faLock}
            style={{ color: C.red, fontSize: 14 }}
          />
          <span
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: C.textMid,
              lineHeight: 1.35,
            }}
          >
            Bloqueos (si estas IN están activas, no se ejecuta)
          </span>
        </div>
        <div style={{ marginBottom: 10, minHeight: 28 }}>
          <ChipList
            items={wfBlocked}
            onRemove={(c) => setWfBlocked(wfBlocked.filter((x) => x !== c))}
            C={C}
            labelByCode={ioLabelByCode}
          />
        </div>
        <select
          className="rules-assist-control"
          value={pickBl}
          onChange={(e) => {
            const v = e.target.value;
            if (!v) return;
            setWfBlocked((prev) => (prev.includes(v) ? prev : [...prev, v]));
            setPickBl("");
          }}
          style={{ width: "100%", minWidth: 200 }}
        >
          <option value="">Seleccionar IN de bloqueo…</option>
          {ins
            .filter((o) => o.code !== wfTrigger)
            .map((o) => (
              <option key={o.code} value={o.code}>
                {o.label}
              </option>
            ))}
        </select>
      </div>

      <div style={assistSection}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 10,
            paddingLeft: 10,
            borderLeft: `3px solid ${C.red}`,
          }}
        >
          <FontAwesomeIcon
            icon={faPowerOff}
            style={{ color: C.red, fontSize: 14 }}
          />
          <span
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: C.textMid,
              lineHeight: 1.35,
            }}
          >
            Desactivar modos (IN → override OFF al ejecutar)
          </span>
        </div>
        <div style={{ marginBottom: 10, minHeight: 28 }}>
          <ChipList
            items={wfDeactivate}
            onRemove={(c) =>
              setWfDeactivate(wfDeactivate.filter((x) => x !== c))
            }
            C={C}
            labelByCode={ioLabelByCode}
          />
        </div>
        <select
          className="rules-assist-control"
          value={pickDeact}
          onChange={(e) => {
            const v = e.target.value;
            if (!v) return;
            setWfDeactivate((prev) => (prev.includes(v) ? prev : [...prev, v]));
            setPickDeact("");
          }}
          style={{ width: "100%", minWidth: 200 }}
        >
          <option value="">Seleccionar IN a desactivar…</option>
          {ins.map((o) => (
            <option key={o.code} value={o.code}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div style={assistSection}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 10,
            paddingLeft: 10,
            borderLeft: `3px solid ${C.red}`,
          }}
        >
          <FontAwesomeIcon
            icon={faToggleOn}
            style={{ color: C.green, fontSize: 14 }}
          />
          <span
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: C.textMid,
              lineHeight: 1.35,
            }}
          >
            Activar salidas (OUT → ON)
          </span>
        </div>
        <div style={{ marginBottom: 10, minHeight: 28 }}>
          <ChipList
            items={wfActOut}
            onRemove={(c) => setWfActOut(wfActOut.filter((x) => x !== c))}
            C={C}
            labelByCode={ioLabelByCode}
          />
        </div>
        <select
          className="rules-assist-control"
          value={pickOutOn}
          onChange={(e) => {
            const v = e.target.value;
            if (!v) return;
            setWfActOut((prev) => (prev.includes(v) ? prev : [...prev, v]));
            setPickOutOn("");
          }}
          style={{ width: "100%", minWidth: 200 }}
        >
          <option value="">Seleccionar OUT para activar…</option>
          {outs.map((o) => (
            <option key={o.code} value={o.code}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div style={assistSection}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 10,
            paddingLeft: 10,
            borderLeft: `3px solid ${C.red}`,
          }}
        >
          <FontAwesomeIcon
            icon={faToggleOff}
            style={{ color: C.textSub, fontSize: 14 }}
          />
          <span
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: C.textMid,
              lineHeight: 1.35,
            }}
          >
            Desactivar salidas (OUT → OFF)
          </span>
          <label
            style={{
              marginLeft: "auto",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11,
              fontWeight: 600,
              color: C.textSub,
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
            title="Al soltar el trigger o desactivar la regla, vuelve a ON solo los OUT que ya estaban encendidos (p. ej. interfono)."
          >
            <input
              type="checkbox"
              checked={wfDeactTemporary}
              onChange={(e) => setWfDeactTemporary(e.target.checked)}
            />
            Desactivar temporalmente
          </label>
        </div>
        <div style={{ marginBottom: 10, minHeight: 28 }}>
          <ChipList
            items={wfDeactOut}
            onRemove={(c) => setWfDeactOut(wfDeactOut.filter((x) => x !== c))}
            C={C}
            labelByCode={ioLabelByCode}
          />
        </div>
        <select
          className="rules-assist-control"
          value={pickOutOff}
          onChange={(e) => {
            const v = e.target.value;
            if (!v) return;
            setWfDeactOut((prev) => (prev.includes(v) ? prev : [...prev, v]));
            setPickOutOff("");
          }}
          style={{ width: "100%", minWidth: 200 }}
        >
          <option value="">Seleccionar OUT para desactivar…</option>
          {outs.map((o) => (
            <option key={o.code} value={o.code}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 10,
        }}
      >
        <Btn variant="primary" onClick={mergeToJson} disabled={!ins.length}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <FontAwesomeIcon icon={faCode} />
            Generar y fusionar en el JSON del editor
          </span>
        </Btn>
        {!ins.length && (
          <span style={{ fontSize: 12, color: C.amber, fontWeight: 600 }}>
            Define placas e IN en «Definición placas» para ver opciones.
          </span>
        )}
      </div>
    </Card>
  );
}

function formatPulseMaintenance(count, limit) {
  const n = Number(count) || 0;
  const lim =
    limit != null && limit !== "" && Number(limit) > 0 ? Number(limit) : null;
  if (!lim) {
    return {
      level: "none",
      text: `${n.toLocaleString("es-ES")}`,
      pct: null,
    };
  }
  const pct = n / lim;
  let level = "ok";
  if (pct >= 1) level = "critical";
  else if (pct >= 0.8) level = "warning";
  return {
    level,
    text: `${n.toLocaleString("es-ES")} / ${lim.toLocaleString("es-ES")}`,
    pct: Math.min(pct * 100, 100),
  };
}

const PULSE_LEVEL_STYLE = {
  none: { bg: C.surfaceAlt, color: C.textSub, border: C.border },
  ok: { bg: C.greenLight, color: C.green, border: C.greenBorder },
  warning: { bg: C.amberLight, color: C.amber, border: C.amberBorder },
  critical: { bg: C.redFaint, color: C.red, border: C.redBorder },
};

function ModuleChannelRow({
  mod,
  channel,
  index,
  onDelete,
  onRefresh,
  addUI,
  showCmdCols,
  showPulseMaintenance = false,
}) {
  const [channelName, setChannelName] = useState(channel.channel_name ?? "");
  const [pulseLimitDraft, setPulseLimitDraft] = useState(
    channel.pulse_limit != null ? String(channel.pulse_limit) : "",
  );

  useEffect(() => {
    setChannelName(channel.channel_name ?? "");
  }, [channel.id, channel.channel_name]);

  useEffect(() => {
    setPulseLimitDraft(
      channel.pulse_limit != null ? String(channel.pulse_limit) : "",
    );
  }, [channel.id, channel.pulse_limit]);

  const pulseInfo = formatPulseMaintenance(
    channel.pulse_count,
    channel.pulse_limit,
  );
  const pulseStyle = PULSE_LEVEL_STYLE[pulseInfo.level];

  const saveChannelName = async () => {
    const trimmed = channelName.trim();
    try {
      await apiFetch(`/modules/${mod.id}/channels/${channel.id}`, {
        method: "PUT",
        body: JSON.stringify({ channel_name: trimmed || null }),
      });
      addUI("OK", `Nombre guardado: ${trimmed || "(vacío)"}`);
      await onRefresh();
    } catch (e) {
      addUI("ERR", e.message);
    }
  };

  const savePulseLimit = async () => {
    const trimmed = pulseLimitDraft.trim();
    let pulse_limit = null;
    if (trimmed !== "") {
      const parsed = Number.parseInt(trimmed, 10);
      if (!Number.isFinite(parsed) || parsed < 1) {
        addUI("ERR", "El límite debe ser un entero >= 1 o vacío");
        return;
      }
      pulse_limit = parsed;
    }
    try {
      await apiFetch(`/modules/${mod.id}/channels/${channel.id}`, {
        method: "PUT",
        body: JSON.stringify({ pulse_limit }),
      });
      addUI(
        "OK",
        pulse_limit ? `Límite: ${pulse_limit}` : "Sin límite de pulsaciones",
      );
      await onRefresh();
    } catch (e) {
      addUI("ERR", e.message);
    }
  };

  const resetPulseCount = async () => {
    if (
      !window.confirm(
        `¿Reiniciar el contador de pulsaciones de IN${index + 1}? (tras mantenimiento o cambio de sensor)`,
      )
    ) {
      return;
    }
    try {
      await apiFetch(`/modules/${mod.id}/channels/${channel.id}/reset-pulses`, {
        method: "POST",
      });
      addUI("OK", `Contador IN${index + 1} reiniciado`);
      await onRefresh();
    } catch (e) {
      addUI("ERR", e.message);
    }
  };

  return (
    <tr style={{ borderBottom: `1px solid ${C.border}` }}>
      <td style={{ padding: 4, whiteSpace: "nowrap" }}>#{index + 1}</td>
      <td style={{ padding: 4, fontFamily: "monospace" }}>
        {fmtHex(channel.address)}
      </td>
      {showCmdCols ? (
        <td style={{ padding: 4, fontFamily: "monospace", color: C.muted }}>
          {channel.open_cmd != null ? fmtHex(channel.open_cmd) : "def"} /{" "}
          {channel.close_cmd != null ? fmtHex(channel.close_cmd) : "def"}
        </td>
      ) : null}
      <td style={{ padding: 4 }}>
        <div style={{ display: "grid", gap: 8 }}>
          <div
            style={{
              display: "flex",
              gap: 6,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <input
              value={channelName}
              onChange={(e) => setChannelName(e.target.value)}
              placeholder="Nombre del canal"
              title={channel.smcse_code || channel.io_code || ""}
              style={{
                flex: "1 1 120px",
                minWidth: 100,
                maxWidth: 200,
                padding: "4px 6px",
                fontSize: 11,
                border: `1px solid ${C.border}`,
                borderRadius: 6,
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") saveChannelName();
              }}
            />
            <Btn small variant="primary" onClick={saveChannelName}>
              Guardar
            </Btn>
            <Btn small variant="danger" onClick={onDelete}>
              Quitar
            </Btn>
          </div>
          {showPulseMaintenance ? (
            <div
              style={{
                display: "flex",
                gap: 6,
                alignItems: "center",
                flexWrap: "wrap",
                padding: "6px 8px",
                borderRadius: 8,
                background: C.offWhite,
                border: `1px solid ${C.border}`,
              }}
            >
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  padding: "3px 8px",
                  borderRadius: 999,
                  background: pulseStyle.bg,
                  color: pulseStyle.color,
                  border: `1px solid ${pulseStyle.border}`,
                  whiteSpace: "nowrap",
                }}
                title="Pulsaciones físicas (OFF→ON). No cuenta override."
              >
                Pulsaciones: {pulseInfo.text}
              </span>
              {pulseInfo.pct != null ? (
                <div
                  style={{
                    flex: "1 1 80px",
                    minWidth: 60,
                    maxWidth: 120,
                    height: 6,
                    borderRadius: 999,
                    background: C.border,
                    overflow: "hidden",
                  }}
                  title={`${Math.round(pulseInfo.pct)}% del límite`}
                >
                  <div
                    style={{
                      width: `${pulseInfo.pct}%`,
                      height: "100%",
                      background:
                        pulseInfo.level === "critical"
                          ? C.red
                          : pulseInfo.level === "warning"
                            ? C.amber
                            : C.green,
                    }}
                  />
                </div>
              ) : null}
              <input
                type="number"
                min={1}
                value={pulseLimitDraft}
                onChange={(e) => setPulseLimitDraft(e.target.value)}
                placeholder="Límite (opc.)"
                title="Pulsaciones máximas antes de mantenimiento (opcional)"
                style={{
                  width: 88,
                  padding: "4px 6px",
                  fontSize: 11,
                  border: `1px solid ${C.border}`,
                  borderRadius: 6,
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") savePulseLimit();
                }}
              />
              <Btn small onClick={savePulseLimit}>
                Guardar límite
              </Btn>
              <Btn small onClick={resetPulseCount}>
                Reiniciar contador
              </Btn>
            </div>
          ) : null}
        </div>
      </td>
    </tr>
  );
}

function ModuleDbEditor({ mod, addUI, onRefresh }) {
  const [name, setName] = useState(mod.name);
  const [host, setHost] = useState(mod.host);
  const [port, setPort] = useState(mod.port);
  const [slaveId, setSlaveId] = useState(mod.slave_id);
  const [bitmask, setBitmask] = useState(
    mod.bitmask_address != null ? String(mod.bitmask_address) : "",
  );
  const [relation, setRelation] = useState(
    mod.relation_register != null ? String(mod.relation_register) : "",
  );
  const [bulkOnA, setBulkOnA] = useState(
    String(mod.bulk?.all_on?.address ?? 0),
  );
  const [bulkOnV, setBulkOnV] = useState(
    String(mod.bulk?.all_on?.value ?? 0x700),
  );
  const [bulkOffA, setBulkOffA] = useState(
    String(mod.bulk?.all_off?.address ?? 0),
  );
  const [bulkOffV, setBulkOffV] = useState(
    String(mod.bulk?.all_off?.value ?? 0x800),
  );
  const [inAddr, setInAddr] = useState("");
  const [outAddr, setOutAddr] = useState("");
  const [outOpen, setOutOpen] = useState("");
  const [outClose, setOutClose] = useState("");

  const saveMeta = async () => {
    try {
      const body = {
        name,
        host,
        port: (() => {
          const p = parseInt(String(port).trim(), 10);
          return Number.isFinite(p) && p > 0 ? p : 502;
        })(),
        slave_id: normalizeSlaveId(slaveId),
      };
      const bm = parseAddrStr(bitmask);
      if (!Number.isNaN(bm)) body.bitmask_address = bm;
      else if (bitmask.trim() === "") body.bitmask_address = null;
      const rel = parseAddrStr(relation);
      if (!Number.isNaN(rel)) body.relation_register = rel;
      else if (relation.trim() === "") body.relation_register = null;
      await apiFetch(`/modules/${mod.id}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      addUI("OK", `Placa ${mod.id}: datos guardados`);
      await onRefresh();
    } catch (e) {
      addUI("ERR", e.message);
    }
  };

  const saveBulk = async () => {
    try {
      const aoa = parseAddrStr(bulkOnA);
      const aov = parseAddrStr(bulkOnV);
      const ofa = parseAddrStr(bulkOffA);
      const ofv = parseAddrStr(bulkOffV);
      const body = {};
      if (!Number.isNaN(aoa) && !Number.isNaN(aov))
        body.all_on = { address: aoa, value: aov };
      if (!Number.isNaN(ofa) && !Number.isNaN(ofv))
        body.all_off = { address: ofa, value: ofv };
      if (!body.all_on && !body.all_off) {
        addUI("ERR", "Indica dirección y valor para all_on y/o all_off");
        return;
      }
      await apiFetch(`/modules/${mod.id}/bulk`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      addUI("OK", "Comandos masivos guardados");
      await onRefresh();
    } catch (e) {
      addUI("ERR", e.message);
    }
  };

  const addCh = async (kind) => {
    const raw = kind === "input" ? inAddr : outAddr;
    const addr = parseAddrStr(raw);
    if (Number.isNaN(addr)) {
      addUI("ERR", "Dirección inválida (usa 128 o 0x80)");
      return;
    }
    try {
      const payload = { kind, address: addr };
      if (kind === "output") {
        const o = parseAddrStr(outOpen);
        const c = parseAddrStr(outClose);
        if (!Number.isNaN(o)) payload.open_cmd = o;
        if (!Number.isNaN(c)) payload.close_cmd = c;
      }
      await apiFetch(`/modules/${mod.id}/channels`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (kind === "input") setInAddr("");
      else {
        setOutAddr("");
        setOutOpen("");
        setOutClose("");
      }
      addUI("OK", `Canal ${kind} añadido`);
      await onRefresh();
    } catch (e) {
      addUI("ERR", e.message);
    }
  };

  const delCh = async (cid) => {
    try {
      await apiFetch(`/modules/${mod.id}/channels/${cid}`, {
        method: "DELETE",
      });
      addUI("OK", "Canal eliminado");
      await onRefresh();
    } catch (e) {
      addUI("ERR", e.message);
    }
  };

  const delMod = async () => {
    if (
      !window.confirm(
        `¿Eliminar placa «${mod.name}» (id ${mod.id}) y todos sus canales?`,
      )
    )
      return;
    try {
      await apiFetch(`/modules/${mod.id}`, { method: "DELETE" });
      addUI("WARN", `Placa ${mod.id} eliminada`);
      await onRefresh();
    } catch (e) {
      addUI("ERR", e.message);
    }
  };

  const inp = mod.inputs || [];
  const out = mod.outputs || [];

  return (
    <Card style={{ width: "100%", maxWidth: 560, margin: "0 auto" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 8,
        }}
      >
        <SecLabel>Placa #{mod.id}</SecLabel>
        <Btn small variant="danger" onClick={delMod}>
          Eliminar placa
        </Btn>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <div>
          <div style={{ fontSize: 11, color: C.muted }}>Nombre</div>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{
              width: "100%",
              padding: 6,
              border: `1px solid ${C.border}`,
              borderRadius: 6,
            }}
          />
        </div>
        <div>
          <div style={{ fontSize: 11, color: C.muted }}>IP</div>
          <input
            value={host}
            placeholder="192.168.1.101"
            onChange={(e) => setHost(e.target.value)}
            style={{
              width: "100%",
              padding: 6,
              border: `1px solid ${C.border}`,
              borderRadius: 6,
            }}
          />
        </div>
        <div>
          <div style={{ fontSize: 11, color: C.muted }}>Puerto</div>
          <input
            type="number"
            value={port}
            placeholder="5000"
            onChange={(e) => setPort(e.target.value)}
            style={{
              width: "100%",
              padding: 6,
              border: `1px solid ${C.border}`,
              borderRadius: 6,
            }}
          />
        </div>
        <div>
          <div style={{ fontSize: 11, color: C.muted }}>Slave</div>
          <input
            type="number"
            value={slaveId}
            placeholder="1"
            onChange={(e) => setSlaveId(e.target.value)}
            style={{
              width: "100%",
              padding: 6,
              border: `1px solid ${C.border}`,
              borderRadius: 6,
            }}
          />
        </div>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 8,
          marginTop: 8,
        }}
      >
        <div>
          <div style={{ fontSize: 11, color: C.muted }}>
            Bitmask reg. (opc., p.ej. 0x70)
          </div>
          <input
            value={bitmask}
            onChange={(e) => setBitmask(e.target.value)}
            placeholder="vacío = sin bitmask"
            style={{
              width: "100%",
              padding: 6,
              border: `1px solid ${C.border}`,
              borderRadius: 6,
            }}
          />
        </div>
        <div>
          <div style={{ fontSize: 11, color: C.muted }}>
            Reg. relación IN/OUT (opc.)
          </div>
          <input
            value={relation}
            onChange={(e) => setRelation(e.target.value)}
            placeholder="0xFA o vacío"
            style={{
              width: "100%",
              padding: 6,
              border: `1px solid ${C.border}`,
              borderRadius: 6,
            }}
          />
        </div>
      </div>
      <div style={{ marginTop: 8 }}>
        <Btn small variant="primary" onClick={saveMeta}>
          Guardar placa (IP, nombre, …)
        </Btn>
      </div>

      <div
        style={{
          marginTop: 14,
          fontSize: 11,
          fontWeight: 700,
          color: C.textMid,
        }}
      >
        All ON / All OFF (holding register)
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
          gap: 8,
          marginTop: 6,
        }}
      >
        <input
          title="all_on address"
          placeholder="0x0000"
          value={bulkOnA}
          onChange={(e) => setBulkOnA(e.target.value)}
          style={{
            width: "100%",
            minWidth: 0,
            padding: 6,
            border: `1px solid ${C.border}`,
            borderRadius: 6,
          }}
        />
        <input
          title="all_on value"
          placeholder="0x0700"
          value={bulkOnV}
          onChange={(e) => setBulkOnV(e.target.value)}
          style={{
            width: "100%",
            minWidth: 0,
            padding: 6,
            border: `1px solid ${C.border}`,
            borderRadius: 6,
          }}
        />
        <input
          title="all_off address"
          placeholder="0x0000"
          value={bulkOffA}
          onChange={(e) => setBulkOffA(e.target.value)}
          style={{
            width: "100%",
            minWidth: 0,
            padding: 6,
            border: `1px solid ${C.border}`,
            borderRadius: 6,
          }}
        />
        <input
          title="all_off value"
          placeholder="0x0800"
          value={bulkOffV}
          onChange={(e) => setBulkOffV(e.target.value)}
          style={{
            width: "100%",
            minWidth: 0,
            padding: 6,
            border: `1px solid ${C.border}`,
            borderRadius: 6,
          }}
        />
      </div>
      <div style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>
        Columnas: all_on addr · all_on valor · all_off addr · all_off valor
        (decimal o 0x…)
      </div>
      <div style={{ marginTop: 6 }}>
        <Btn small onClick={saveBulk}>
          Guardar all on/off
        </Btn>
      </div>

      <div
        style={{
          marginTop: 14,
          fontSize: 11,
          fontWeight: 700,
          color: C.textMid,
        }}
      >
        Entradas ({inp.length})
      </div>
      <div style={{ fontSize: 10, color: C.muted, marginBottom: 4 }}>
        Códigos reglas: IN_{String(mod.id).padStart(2, "0")}_&lt;índice&gt; ·
        Pulsaciones = activaciones físicas OFF→ON (no cuenta override)
      </div>
      <table
        style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}
      >
        <tbody>
          {inp.map((c, i) => (
            <ModuleChannelRow
              key={c.id}
              mod={mod}
              channel={c}
              index={i}
              showCmdCols={false}
              showPulseMaintenance
              addUI={addUI}
              onRefresh={onRefresh}
              onDelete={() => delCh(c.id)}
            />
          ))}
        </tbody>
      </table>
      <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
        <input
          value={inAddr}
          onChange={(e) => setInAddr(e.target.value)}
          placeholder={IN_PLACEHOLDERS[(inp.length || 0) % 12]}
          style={{
            flex: 1,
            minWidth: 120,
            padding: 6,
            border: `1px solid ${C.border}`,
            borderRadius: 6,
          }}
        />
        <Btn small onClick={() => addCh("input")}>
          Añadir IN
        </Btn>
      </div>
      <div style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>
        Referencia IN (12): {IN_PLACEHOLDERS.join(", ")}
      </div>

      <div
        style={{
          marginTop: 14,
          fontSize: 11,
          fontWeight: 700,
          color: C.textMid,
        }}
      >
        Salidas ({out.length})
      </div>
      <table
        style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}
      >
        <tbody>
          {out.map((c, i) => (
            <ModuleChannelRow
              key={c.id}
              mod={mod}
              channel={c}
              index={i}
              showCmdCols
              addUI={addUI}
              onRefresh={onRefresh}
              onDelete={() => delCh(c.id)}
            />
          ))}
        </tbody>
      </table>
      <div
        style={{
          display: "flex",
          gap: 6,
          marginTop: 6,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <input
          value={outAddr}
          onChange={(e) => setOutAddr(e.target.value)}
          placeholder={OUT_PLACEHOLDERS[(out.length || 0) % 12]}
          style={{
            flex: 1,
            minWidth: 100,
            padding: 6,
            border: `1px solid ${C.border}`,
            borderRadius: 6,
          }}
        />
        <input
          value={outOpen}
          onChange={(e) => setOutOpen(e.target.value)}
          placeholder="ON 0x100 (opc.)"
          style={{
            width: 100,
            padding: 6,
            border: `1px solid ${C.border}`,
            borderRadius: 6,
          }}
        />
        <input
          value={outClose}
          onChange={(e) => setOutClose(e.target.value)}
          placeholder="OFF 0x200 (opc.)"
          style={{
            width: 100,
            padding: 6,
            border: `1px solid ${C.border}`,
            borderRadius: 6,
          }}
        />
        <Btn small onClick={() => addCh("output")}>
          Añadir OUT
        </Btn>
      </div>
      <div style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>
        Referencia OUT (12): {OUT_PLACEHOLDERS.join(", ")}
      </div>
    </Card>
  );
}

export default function ETD8A12Panel() {
  const [tab, setTab] = useState(0);
  const [coceMessageWsEvent, setCoceMessageWsEvent] = useState(null);
  const [templateConfig, setTemplateConfig] = useState(DEFAULT_TEMPLATE_CONFIG);
  const [templateDraft, setTemplateDraft] = useState(DEFAULT_TEMPLATE_CONFIG);

  useEffect(() => {
    apiFetch("/api/config/template")
      .then((data) => {
        if (data && Object.keys(data).length > 0) {
          const parsed = {
            ...DEFAULT_TEMPLATE_CONFIG,
            ...data,
            primaryColor: normalizeHexColor(
              data.primaryColor || DEFAULT_TEMPLATE_CONFIG.primaryColor,
            ),
          };
          setTemplateConfig(parsed);
          setTemplateDraft(parsed);
        }
      })
      .catch((err) => console.warn("Error cargando template", err));
  }, []);
  const [serverOnline, setServer] = useState(false);
  const [boards, setBoards] = useState({});
  const [boardConfigs, setConfigs] = useState({});
  const [moduleList, setModuleList] = useState([]);
  const [draftNewMod, setDraftNewMod] = useState({
    name: "",
    host: "",
    port: "",
    slave_id: "",
  });
  const [events, setEvents] = useState([]);
  const [uiLog, setUiLog] = useState([]);
  const [pending, setPending] = useState({});
  const [histFilter, setHistFilter] = useState("ALL");
  const [histDateFrom, setHistDateFrom] = useState("");
  const [histDateTo, setHistDateTo] = useState("");
  const [rulesJson, setRulesJson] = useState("");
  const [rulesMap, setRulesMap] = useState({});
  const [selectedMode, setSelectedMode] = useState(null);
  const [pendingManualEnclavamientoMode, setPendingManualEnclavamientoMode] =
    useState(null);
  const [zaguanLedPushKey, setZaguanLedPushKey] = useState(0);
  const [activatingQueuedMode, setActivatingQueuedMode] = useState(null);
  const [activeToggleRules, setActiveToggleRules] = useState([]);
  const [globalLoadingCount, setGlobalLoadingCount] = useState(0);
  const [initialStatusLoaded, setInitialStatusLoaded] = useState(false);
  const [initialRulesLoaded, setInitialRulesLoaded] = useState(false);
  const logScrollRef = useRef(null);
  const histScrollRef = useRef(null);
  const uiLogLenRef = useRef(0);
  const histLenRef = useRef(0);
  const prevTabRef = useRef(0);
  const statusPollInFlightRef = useRef(false);
  const mergeStatusRef = useRef(null);
  const panelWsRef = useRef(null);
  const activeTemplateColors = useMemo(
    () => templateColors(templateConfig),
    [templateConfig],
  );
  const rulesMapRef = useRef(rulesMap);
  rulesMapRef.current = rulesMap;
  const boardsRef = useRef(boards);
  boardsRef.current = boards;

  const orderedModuleIds = useMemo(() => {
    if (moduleList.length) {
      return [...moduleList]
        .sort(
          (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id,
        )
        .map((m) => m.id);
    }
    return Object.keys(boards)
      .map(Number)
      .sort((a, b) => a - b);
  }, [moduleList, boards]);

  const metaFor = useCallback(
    (id) => {
      const m = moduleList.find((x) => x.id === id);
      const b = boards[id];
      const nIn = b?.inputs?.length ?? 0;
      const nOut = b?.outputs?.length ?? 0;
      return {
        id,
        name: m?.name ?? `Placa ${id}`,
        sub: m
          ? `${m.inputs?.length ?? nIn} IN / ${m.outputs?.length ?? nOut} OUT`
          : `${nIn} IN / ${nOut} OUT`,
      };
    },
    [moduleList, boards],
  );

  const addUI = useCallback(
    (type, msg) =>
      setUiLog((p) => [
        ...p.slice(-199),
        {
          ts: new Date().toLocaleTimeString("es-ES", { hour12: false }),
          type,
          msg,
        },
      ]),
    [],
  );

  const beginGlobalLoading = useCallback(
    () => setGlobalLoadingCount((c) => c + 1),
    [],
  );
  const endGlobalLoading = useCallback(
    () => setGlobalLoadingCount((c) => Math.max(0, c - 1)),
    [],
  );
  const withGlobalLoader = useCallback(
    async (task) => {
      beginGlobalLoading();
      try {
        return await task();
      } finally {
        endGlobalLoading();
      }
    },
    [beginGlobalLoading, endGlobalLoading],
  );

  const updateTemplateDraft = useCallback((patch) => {
    setTemplateDraft((prev) => ({ ...prev, ...patch }));
  }, []);

  const uploadTemplateLogo = useCallback(
    async (file, key) => {
      if (!file) return;
      try {
        const dataUrl = await readImageAsDataUrl(file);
        setTemplateDraft((prev) => ({ ...prev, [key]: dataUrl }));
        addUI("INFO", "Logo cargado en la configuración local");
      } catch (e) {
        addUI("ERR", e.message);
      }
    },
    [addUI],
  );

  const saveTemplateDraft = useCallback(async () => {
    const next = {
      mainLogo:
        templateDraft.mainLogo?.trim() || DEFAULT_TEMPLATE_CONFIG.mainLogo,
      boardLogo:
        templateDraft.boardLogo?.trim() || DEFAULT_TEMPLATE_CONFIG.boardLogo,
      primaryColor: normalizeHexColor(templateDraft.primaryColor),
    };
    try {
      await apiFetch("/api/config/template", {
        method: "PUT",
        body: JSON.stringify(next),
      });
      setTemplateConfig(next);
      setTemplateDraft(next);
      addUI("OK", "Template guardado");
    } catch (e) {
      addUI("Error", "No se pudo guardar la plantilla: " + e.message);
    }
  }, [addUI, templateDraft]);

  const applyTemplatePreset = useCallback(
    async (preset, label) => {
      try {
        await apiFetch("/api/config/template", {
          method: "PUT",
          body: JSON.stringify(preset),
        });
        setTemplateConfig(preset);
        setTemplateDraft(preset);
        addUI("INFO", `Template restaurado: ${label}`);
      } catch (e) {
        addUI("Error", "No se pudo restaurar la plantilla: " + e.message);
      }
    },
    [addUI],
  );

  const resetTemplateConfig1 = useCallback(
    () =>
      applyTemplatePreset(DEFAULT_TEMPLATE_CONFIG_1, "Invia (por defecto 1)"),
    [applyTemplatePreset],
  );

  const resetTemplateConfig2 = useCallback(
    () =>
      applyTemplatePreset(
        DEFAULT_TEMPLATE_CONFIG_2,
        "Santander (por defecto 2)",
      ),
    [applyTemplatePreset],
  );

  const scrollContainerToBottom = useCallback(
    (containerRef, { smooth = true } = {}) => {
      const box = containerRef.current;
      if (!box) return;
      const run = () => {
        box.scrollTo({
          top: box.scrollHeight,
          behavior: smooth ? "smooth" : "auto",
        });
      };
      requestAnimationFrame(() => {
        run();
        requestAnimationFrame(run);
      });
    },
    [],
  );

  const scrollContainerToTop = useCallback(
    (containerRef, { smooth = true } = {}) => {
      const box = containerRef.current;
      if (!box) return;
      const run = () => {
        box.scrollTo({ top: 0, behavior: smooth ? "smooth" : "auto" });
      };
      requestAnimationFrame(() => {
        run();
        requestAnimationFrame(run);
      });
    },
    [],
  );

  useEffect(() => {
    const mergeStatusPayload = (d) => {
      if (Array.isArray(d.modules_config)) setModuleList(d.modules_config);
      const next = {};
      for (const [id, b] of Object.entries(d.boards || {})) {
        const inputs = [...(b.inputs || [])];
        const inputs_raw = [...(b.inputs_raw || b.inputs || [])];
        const outputs = [...(b.outputs || [])];
        const nIn = Math.max(inputs.length, inputs_raw.length);
        let ov = [...(b.input_overrides || [])];
        while (ov.length < nIn) ov.push(null);
        ov = ov.slice(0, nIn);
        while (inputs.length < nIn) inputs.push(false);
        while (inputs_raw.length < nIn) inputs_raw.push(false);
        next[+id] = {
          connected: b.connected,
          inputs: inputs.slice(0, nIn),
          inputs_raw: inputs_raw.slice(0, nIn),
          outputs,
          input_overrides: ov,
          error: b.error,
          in_out_associated:
            typeof b.in_out_associated === "boolean"
              ? b.in_out_associated
              : null,
        };
        if (b.config) {
          setConfigs((p) => ({
            ...p,
            [+id]: {
              host: b.config.host,
              port: b.config.port,
              slave_id: b.config.slave_id,
            },
          }));
        }
      }
      setBoards((p) => ({ ...p, ...next }));
      if (d.current_mode && rulesMapRef.current[d.current_mode]) {
        setSelectedMode(d.current_mode);
      }
      if (Array.isArray(d.active_toggle_rules)) {
        setActiveToggleRules(d.active_toggle_rules);
      }
      if ("pending_manual_enclavamiento_mode" in d) {
        setPendingManualEnclavamientoMode(
          d.pending_manual_enclavamiento_mode || null,
        );
      }
    };
    mergeStatusRef.current = mergeStatusPayload;

    const poll = async (isInitial = false) => {
      if (statusPollInFlightRef.current) return;
      statusPollInFlightRef.current = true;
      try {
        if (isInitial) {
          // 1) Respuesta rápida sin Modbus: quita el bloqueo global pronto (no es “lento al enviar”).
          const d0 = await apiFetch("/status?refresh_hardware=false", {
            timeoutMs: 20000,
          });
          mergeStatusPayload(d0);
          setServer(true);
        } else {
          const refreshHw = typeof document !== "undefined" && !document.hidden;
          const statusPath = refreshHw
            ? "/status"
            : "/status?refresh_hardware=false";
          const d = await apiFetch(statusPath, { timeoutMs: 120000 });
          mergeStatusPayload(d);
          setServer(true);
        }
      } catch {
        setServer(false);
      } finally {
        statusPollInFlightRef.current = false;
        if (isInitial) setInitialStatusLoaded(true);
      }
      // 2) Tras pintar UI, refresco hardware en segundo plano (RTU puede tardar mucho).
      if (isInitial) {
        setTimeout(() => {
          void (async () => {
            if (statusPollInFlightRef.current) return;
            statusPollInFlightRef.current = true;
            try {
              const d1 = await apiFetch("/status", { timeoutMs: 120000 });
              mergeStatusPayload(d1);
              setServer(true);
            } catch {
              /* mantener último estado */
            } finally {
              statusPollInFlightRef.current = false;
            }
          })();
        }, 80);
      }
    };
    poll(true);

    let ws = null;
    let closed = false;
    const connectWs = () => {
      const url = getPanelWsLiveUrl();
      if (!url) return;
      ws = new WebSocket(url);
      panelWsRef.current = ws;
      ws.onopen = () => setServer(true);
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(String(ev.data));
          if (data.type === "panel_status" && data.payload) {
            mergeStatusPayload(data.payload);
            setServer(true);
            setInitialStatusLoaded(true);
          }
          if (data.type === "zaguan_led") {
            setZaguanLedPushKey((n) => n + 1);
          }
          if (data.type === "coce_notification") {
            setCoceMessageWsEvent({ ...data, _ts: Date.now() });
          }
          if (data.type === "software_update_available") {
            window.dispatchEvent(
              new CustomEvent("software_update_available", { detail: data }),
            );
          }
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        panelWsRef.current = null;
        if (!closed) window.setTimeout(connectWs, 3000);
      };
      ws.onerror = () => {
        panelWsRef.current = null;
        setServer(false);
      };
    };
    connectWs();

    const pingIv = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
    }, 25000);

    // Respaldo solo si el WS no está conectado (sin polling cada 5 s).
    const fallbackIv = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) return;
      void poll(false);
    }, 60000);

    return () => {
      closed = true;
      clearInterval(pingIv);
      clearInterval(fallbackIv);
      panelWsRef.current = null;
      ws?.close();
      mergeStatusRef.current = null;
    };
  }, []);

  // Cola
  useEffect(() => {
    const pending = pendingManualEnclavamientoMode;
    if (!pending) {
      setActivatingQueuedMode(null);
      return;
    }

    let cancelled = false;
    const wait = (ms) =>
      new Promise((resolve) => {
        window.setTimeout(resolve, ms);
      });

    const watchQueue = async () => {
      while (!cancelled) {
        const stillBlocked = ruleBlockersActive(
          pending,
          rulesMapRef.current,
          boardsRef.current,
        );
        if (stillBlocked) {
          setActivatingQueuedMode(null);
          try {
            const d = await apiFetch("/status", { timeoutMs: 120000 });
            if (!cancelled) {
              mergeStatusRef.current?.(d);
              setServer(true);
            }
          } catch {
            if (!cancelled) setServer(false);
          }
          await wait(2000);
          continue;
        }
        setActivatingQueuedMode(pending);
        beginGlobalLoading();
        try {
          const result = await apiFetch(
            `/rules/${encodeURIComponent(pending)}/run`,
            { method: "POST" },
          );
          if (cancelled) break;
          if (result?.queued) {
            setPendingManualEnclavamientoMode(
              result.pending_manual_mode || pending,
            );
            applyAutoRulesPanelFeedback(result, () => {}, setActiveToggleRules);
          } else if (result?.executed) {
            setPendingManualEnclavamientoMode(null);
            if (
              pending.startsWith("horario_") ||
              pending === "senal_de_incendio_activada"
            )
              setSelectedMode(pending);
          }
          const d = await apiFetch("/status?refresh_hardware=false", {
            timeoutMs: 20000,
          });
          if (!cancelled) {
            mergeStatusRef.current?.(d);
            setServer(true);
            if (!d.pending_manual_enclavamiento_mode) break;
          }
        } catch {
          if (!cancelled) setServer(false);
        } finally {
          endGlobalLoading();
          setActivatingQueuedMode(null);
        }
        await wait(2000);
      }
    };

    void watchQueue();

    return () => {
      cancelled = true;
      endGlobalLoading();
      setActivatingQueuedMode(null);
    };
  }, [pendingManualEnclavamientoMode, beginGlobalLoading, endGlobalLoading]);

  const afterPanelMutation = useCallback(async () => {
    if (!mergeStatusRef.current) return;
    try {
      const d = await apiFetch("/status?refresh_hardware=false", {
        timeoutMs: 20000,
      });
      mergeStatusRef.current(d);
      setServer(true);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    const loadRules = async () => {
      try {
        const localDraft = localStorage.getItem(RULES_JSON_STORAGE_KEY);
        if (localDraft) {
          const parsedLocal = JSON.parse(localDraft);
          if (parsedLocal && typeof parsedLocal === "object") {
            setRulesMap(parsedLocal);
            setRulesJson(JSON.stringify(parsedLocal, null, 2));
            setSelectedMode((prev) =>
              prev && parsedLocal[prev] ? prev : null,
            );
          }
        }

        const data = await apiFetch("/rules");
        const loadedRules = data.rules || {};
        // Si hay borrador local, lo respetamos; si no, usamos backend.
        if (!localDraft) {
          setRulesMap(loadedRules);
          setRulesJson(JSON.stringify(loadedRules, null, 2));
          setSelectedMode((prev) => (prev && loadedRules[prev] ? prev : null));
        }
      } catch (e) {
        addUI("ERR", `No se pudieron cargar reglas: ${e.message}`);
      } finally {
        setInitialRulesLoaded(true);
      }
    };
    loadRules();
  }, [addUI]);

  useEffect(() => {
    try {
      if (rulesJson) {
        localStorage.setItem(RULES_JSON_STORAGE_KEY, rulesJson);
      }
    } catch {
      // ignore localStorage failures
    }
  }, [rulesJson]);

  const loadHistoricoEvents = useCallback(async () => {
    try {
      const params = buildHistoricoQueryParams({
        dateFrom: histDateFrom,
        dateTo: histDateTo,
        typeFilter: histFilter,
      });
      const d = await apiFetch(`/events?${params}`);
      setEvents(d.events || []);
    } catch {
      // silent
    }
  }, [histDateFrom, histDateTo, histFilter]);

  useEffect(() => {
    if (tab !== HISTORICO_TAB_INDEX) return;
    void loadHistoricoEvents();
  }, [tab, loadHistoricoEvents]);

  // Actividad (chat): al cargar y en cada línea nueva, scroll al final del panel.
  useEffect(() => {
    if (uiLog.length === 0) return;
    const isNewLine = uiLog.length > uiLogLenRef.current;
    uiLogLenRef.current = uiLog.length;
    scrollContainerToBottom(logScrollRef, {
      smooth: isNewLine && uiLog.length > 1,
    });
  }, [uiLog, scrollContainerToBottom]);

  const doConnect = async (id) => {
    const endpoint = boards[id].connected
      ? `/boards/${id}/disconnect`
      : `/boards/${id}/connect`;
    try {
      beginGlobalLoading();
      setPending((p) => ({ ...p, [`c${id}`]: true }));
      const res = await apiFetch(endpoint, { method: "POST" });
      const connectedNow = Boolean(res?.state?.connected ?? res?.connected);
      setBoards((prev) => ({
        ...prev,
        [id]: {
          ...prev[id],
          ...(res?.state || {}),
          connected: connectedNow,
        },
      }));
      addUI(
        connectedNow ? "OK" : "WARN",
        `Placa ${id} ${connectedNow ? "conectada" : "no conectada"}`,
      );
      void afterPanelMutation();
    } catch (e) {
      addUI("ERR", `Placa ${id}: ${e.message}`);
    } finally {
      setPending((p) => ({ ...p, [`c${id}`]: false }));
      endGlobalLoading();
    }
  };

  const doToggle = async (boardId, channel, current) => {
    if (!boards[boardId].connected) return;
    try {
      setPending((p) => ({ ...p, [`${boardId}-${channel}`]: true }));
      const nextState = !current;
      await apiFetch(`/boards/${boardId}/output`, {
        method: "POST",
        body: JSON.stringify({ channel, state: nextState }),
      });
      setBoards((prev) => {
        const b = prev[boardId];
        if (!b) return prev;
        const outs = [...(b.outputs || [])];
        while (outs.length < channel) outs.push(false);
        outs[channel - 1] = nextState;
        return { ...prev, [boardId]: { ...b, outputs: outs } };
      });
      void afterPanelMutation();
      addUI("OK", `P${boardId} OUT${channel} -> ${nextState ? "ON" : "OFF"}`);
    } catch (e) {
      addUI("ERR", e.message);
    } finally {
      setPending((p) => ({ ...p, [`${boardId}-${channel}`]: false }));
    }
  };

  const doAllOn = async (id) => {
    await withGlobalLoader(async () => {
      try {
        await apiFetch(`/boards/${id}/outputs/all_on`, { method: "POST" });
        addUI("OK", `Placa ${id}: todas ON`);
        void afterPanelMutation();
      } catch (e) {
        addUI("ERR", e.message);
      }
    });
  };
  const doAllOff = async (id) => {
    await withGlobalLoader(async () => {
      try {
        await apiFetch(`/boards/${id}/outputs/all_off`, { method: "POST" });
        addUI("WARN", `Placa ${id}: todas OFF`);
        void afterPanelMutation();
      } catch (e) {
        addUI("ERR", e.message);
      }
    });
  };

  const setInOutAssociation = async (id, associated) => {
    await withGlobalLoader(async () => {
      setPending((p) => ({ ...p, [`ioa${id}`]: true }));
      try {
        await apiFetch(`/boards/${id}/input-output-association`, {
          method: "POST",
          body: JSON.stringify({ associated }),
        });
        addUI(
          "OK",
          `Placa ${id}: IN↔OUT ${associated ? "acoplado" : "desacoplado"}`,
        );
        setBoards((prev) => ({
          ...prev,
          [id]: { ...prev[id], in_out_associated: associated },
        }));
      } catch (e) {
        addUI("ERR", e.message);
      } finally {
        setPending((p) => ({ ...p, [`ioa${id}`]: false }));
      }
    });
  };
  const refreshModuleList = useCallback(async () => {
    try {
      const d = await apiFetch("/modules");
      setModuleList(d.modules || []);
    } catch (e) {
      addUI("ERR", `Placas: ${e.message}`);
    }
  }, [addUI]);

  useEffect(() => {
    if (tab === 4) refreshModuleList();
  }, [tab, refreshModuleList]);

  const createDraftModule = async () => {
    await withGlobalLoader(async () => {
      try {
        if (!draftNewMod.name.trim() || !draftNewMod.host.trim()) {
          addUI("ERR", "Nombre e IP son obligatorios");
          return;
        }
        await apiFetch("/modules", {
          method: "POST",
          body: JSON.stringify({
            name: draftNewMod.name.trim(),
            host: draftNewMod.host.trim(),
            port: Number(draftNewMod.port || 5000),
            slave_id: normalizeSlaveId(draftNewMod.slave_id),
          }),
        });
        setDraftNewMod({ name: "", host: "", port: "", slave_id: "" });
        await refreshModuleList();
        addUI("OK", "Placa creada. Añade IN/OUT y all on/off en su tarjeta.");
      } catch (e) {
        addUI("ERR", e.message);
      }
    });
  };

  const doConfig = async (id) => {
    await withGlobalLoader(async () => {
      try {
        const mod = moduleList.find((x) => x.id === id);
        const bc = boardConfigs[id] || {};
        // Preferir datos de moduleList (p. ej. tras guardar en «Definición placas») sobre boardConfigs del último poll.
        const body = {
          host: mod?.host ?? bc.host ?? "",
          port: Number(mod?.port ?? bc.port ?? 502),
          slave_id: normalizeSlaveId(mod?.slave_id ?? bc.slave_id ?? 1),
          ...(mod?.name ? { name: mod.name } : {}),
        };
        await apiFetch(`/boards/${id}/config`, {
          method: "PUT",
          body: JSON.stringify(body),
        });
        addUI("OK", `Placa ${id}: config aplicada`);
      } catch (e) {
        addUI("ERR", e.message);
      }
    });
  };
  const cycleInputOverride = async (boardId, channel) => {
    const idx = channel - 1;
    const current = boards[boardId].input_overrides?.[idx];
    const next = current === null ? true : current === true ? false : null;
    try {
      let res;
      if (next === null) {
        res = await apiFetch(
          `/inputs/override?board_id=${boardId}&channel=${channel}`,
          { method: "DELETE" },
        );
        addUI("INFO", `Override IN${channel} en P${boardId}: REAL`);
      } else {
        res = await apiFetch("/inputs/override", {
          method: "POST",
          body: JSON.stringify({ board_id: boardId, channel, state: next }),
        });
        if (res?.denied) {
          const detail = (res?.blocked_rules || [])
            .map((b) => `${b.rule_key}: ${(b.blocked_inputs || []).join(", ")}`)
            .join("; ");
          addUI(
            "WARN",
            detail
              ? `IN${channel} P${boardId}: bloqueado — ${detail} (override REAL)`
              : `IN${channel} P${boardId}: bloqueado (override revertido a REAL)`,
          );
        } else {
          addUI(
            "INFO",
            `Override IN${channel} en P${boardId}: ${next ? "FORZADA ON" : "FORZADA OFF"}`,
          );
        }
      }
      applyAutoRulesPanelFeedback(res, addUI, setActiveToggleRules);
      setBoards((prev) => {
        const b = prev[boardId];
        if (!b) return prev;
        const ov = [...(b.input_overrides || [])];
        while (ov.length < channel) ov.push(null);
        const effective =
          res?.denied === true
            ? null
            : res?.override !== undefined
              ? res.override
              : next;
        ov[idx] = effective;
        return { ...prev, [boardId]: { ...b, input_overrides: ov } };
      });
      void afterPanelMutation();
    } catch (e) {
      addUI(
        "ERR",
        `No se pudo cambiar override IN${channel} P${boardId}: ${e.message}`,
      );
    }
  };
  const toModeLabel = (key) =>
    key.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const runRuleByKey = async (ruleKey) => {
    await withGlobalLoader(async () => {
      try {
        const result = await apiFetch(
          `/rules/${encodeURIComponent(ruleKey)}/run`,
          {
            method: "POST",
          },
        );
        if (result?.queued) {
          const pendingKey = result.pending_manual_mode || ruleKey;
          setPendingManualEnclavamientoMode(pendingKey);
          const blocked = (result.blocked_inputs || []).join(", ");
          addUI(
            "WARN",
            blocked
              ? `${toModeLabel(pendingKey)} en cola: se activará cuando se liberen ${blocked}`
              : `${toModeLabel(pendingKey)} en cola hasta que se liberen las entradas de bloqueo`,
          );
          applyAutoRulesPanelFeedback(result, addUI, setActiveToggleRules);
          return;
        }
        if (result?.executed) {
          setPendingManualEnclavamientoMode(null);
          const rule = rulesMapRef.current[ruleKey];
          if (isToggleEnclavamiento(ruleKey, rule)) {
            const on =
              result.toggle_action === "on" || result.toggle_active === true;
            setActiveToggleRules((prev) => {
              const s = new Set(prev);
              if (on) s.add(ruleKey);
              else s.delete(ruleKey);
              return [...s];
            });
            addUI(
              "OK",
              on
                ? `Actuación ON: ${toModeLabel(ruleKey)}`
                : `Actuación OFF: ${toModeLabel(ruleKey)}`,
            );
          } else {
            addUI("OK", `Modo ejecutado: ${toModeLabel(ruleKey)}`);
            if (isOperativePanelMode(ruleKey)) setSelectedMode(ruleKey);
          }
          applyAutoRulesPanelFeedback(result, addUI, setActiveToggleRules);
          void afterPanelMutation();
          return;
        }
        applyAutoRulesPanelFeedback(result, addUI, setActiveToggleRules);
        const reason = result?.reason || "Regla bloqueada o no ejecutada";
        const blocked = (result?.blocked_inputs || []).join(", ");
        addUI(
          "WARN",
          blocked
            ? `${toModeLabel(ruleKey)}: ${reason}`
            : `No se pudo ejecutar ${toModeLabel(ruleKey)}: ${reason}`,
        );
      } catch (e) {
        addUI("ERR", `Error ejecutando modo ${ruleKey}: ${e.message}`);
      }
    });
  };

  const simulateZaguanPulse = async (canal) => {
    await withGlobalLoader(async () => {
      try {
        const res = await apiFetchZaguan(`/api/zaguan/pulsacion/p${canal}`, {
          method: "POST",
          body: JSON.stringify({
            canal,
            ts: Date.now(),
            estado: "libre",
          }),
        });
        if (res?.ok === false) {
          addUI("WARN", `p${canal} rechazada: ${res.reason || "sin motivo"}`);
        } else if (res?.modbus_ok === false) {
          addUI(
            "WARN",
            `p${canal}: orquestador OK pero Modbus no abrió — ${res?.modbus_detail?.reason || "revisa panel"}`,
          );
        } else {
          const extra =
            res?.modbus_detail?.direct_output != null
              ? ` (${res.modbus_detail.direct_output})`
              : "";
          addUI("OK", `Pulsación p${canal}${extra}`);
        }
      } catch (e) {
        addUI("ERR", `Simulación p${canal}: ${e.message}`);
      }
    });
  };
  const emulateLlaveEchada = async (llaveId, action) => {
    await withGlobalLoader(async () => {
      try {
        const meta = ZAGUAN_LLAVE_ECHADA.find((l) => l.id === llaveId);
        const res = await apiFetchZaguan(
          `/api/zaguan/emulate/llave-echada/${llaveId}`,
          {
            method: "POST",
            body: JSON.stringify({ action }),
          },
        );
        const actionLabel = {
          cerrar: "cerrada (ON)",
          abrir: "abierta (OFF)",
          maniobra: "maniobra ON→OFF",
          real: "lectura REAL",
        }[action];
        let msg = `${meta?.label || llaveId}: ${actionLabel}`;
        if (res?.winhose_window_active) {
          msg += ` — ventana WinHose ${Math.ceil(res.winhose_window_remaining_s || 0)}s`;
          if (res?.winhose_intermittent) {
            msg += " (libre parpadeo)";
          }
        } else if (action === "maniobra") {
          addUI(
            "ERR",
            `${meta?.label}: maniobra sin ventana WinHose — ¿modo cerrado o autoservicio activo?`,
          );
          return;
        }
        addUI(res?.winhose_window_active ? "OK" : "INFO", msg);
        void afterPanelMutation();
      } catch (e) {
        addUI("ERR", `Llave echada ${llaveId}: ${e.message}`);
      }
    });
  };
  const saveRulesJson = async () => {
    await withGlobalLoader(async () => {
      try {
        const parsed = JSON.parse(rulesJson || "{}");
        await apiFetch("/rules", {
          method: "PUT",
          body: JSON.stringify({ rules: parsed }),
        });
        setRulesMap(parsed);
        setSelectedMode((prev) => (prev && parsed[prev] ? prev : null));
        addUI("OK", "Reglas JSON guardadas");
      } catch (e) {
        addUI("ERR", `Error guardando reglas JSON: ${e.message}`);
      }
    });
  };
  const evaluateRulesNow = async () => {
    await withGlobalLoader(async () => {
      try {
        const rk =
          selectedMode && rulesMap[selectedMode] != null ? selectedMode : "";
        const q = rk ? `?rule_key=${encodeURIComponent(rk)}` : "";
        const res = await apiFetch(`/rules/evaluate${q}`, { method: "POST" });
        const key = res?.rule_key || Object.keys(res?.results || {})[0];
        const r = key ? res?.results?.[key] : null;
        if (r?.executed) addUI("OK", `Regla evaluada: ${toModeLabel(key)}`);
        else
          addUI(
            "WARN",
            `${key ? toModeLabel(key) : "Regla"}: ${r?.reason || "sin ejecución"}`,
          );
      } catch (e) {
        addUI("ERR", `Error evaluando reglas: ${e.message}`);
      }
    });
  };
  const clearHistory = async () => {
    await withGlobalLoader(async () => {
      try {
        await apiFetch("/events", { method: "DELETE" });
        setEvents([]);
        addUI("INFO", "Histórico del panel borrado");
      } catch (e) {
        addUI("ERR", `No se pudo borrar histórico: ${e.message}`);
      }
    });
  };

  const exportHistoryCsv = async () => {
    try {
      const token = getPanelToken();
      const params = buildHistoricoQueryParams({
        dateFrom: histDateFrom,
        dateTo: histDateTo,
        typeFilter: histFilter,
        limit: 50000,
      });
      const res = await fetch(`/api/events/export?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) {
        clearPanelToken();
        window.location.assign("/login");
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const fromPart = histDateFrom || "inicio";
      const toPart = histDateTo || "fin";
      a.download = `eventos_${fromPart}_${toPart}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      addUI("OK", "CSV descargado");
    } catch (e) {
      addUI("ERR", `Exportar CSV: ${e.message}`);
    }
  };

  const filtered = events;
  // Histórico: más reciente arriba; al abrir la pestaña (carga única), scroll al inicio de la lista.
  useEffect(() => {
    if (tab !== HISTORICO_TAB_INDEX || filtered.length === 0) return;
    const tabOpened = prevTabRef.current !== HISTORICO_TAB_INDEX;
    prevTabRef.current = tab;
    const grew = filtered.length > histLenRef.current;
    histLenRef.current = filtered.length;
    scrollContainerToTop(histScrollRef, {
      smooth: !tabOpened && grew && filtered.length > 1,
    });
  }, [tab, filtered, histFilter, scrollContainerToTop]);
  const totalModules = orderedModuleIds.length;
  const onlineModules = orderedModuleIds.reduce(
    (acc, mid) => acc + (boards[mid]?.connected ? 1 : 0),
    0,
  );
  const activeModeLabel = selectedMode
    ? toModeLabel(selectedMode)
    : "Sin modo seleccionado";
  const showGlobalLoader =
    globalLoadingCount > 0 || !initialStatusLoaded || !initialRulesLoaded;
  const globalLoaderMessage = activatingQueuedMode
    ? `Activando ${toModeLabel(activatingQueuedMode)}…`
    : "Procesando...";

  return (
    <div
      style={{
        "--template-primary": activeTemplateColors.primary,
        "--template-primary-dark": activeTemplateColors.primaryDark,
        "--template-primary-faint": activeTemplateColors.primaryFaint,
        "--template-primary-border": activeTemplateColors.primaryBorder,
        minHeight: "100vh",
        background: C.surface,
        fontFamily: "'Segoe UI',system-ui,sans-serif",
        color: C.text,
        fontSize: 13,
      }}
    >
      <GlobalLoader
        open={showGlobalLoader}
        message={globalLoaderMessage}
        logoSrc={templateConfig.boardLogo}
        logoFallback={DEFAULT_TEMPLATE_CONFIG.boardLogo}
      />
      <TopNavbar
        title="Control de Accesos - ETD8A12"
        tabs={TABS}
        activeTab={tab}
        onTabChange={setTab}
        logoSrc={templateConfig.mainLogo}
        primaryColor={activeTemplateColors.primary}
        primaryDarkColor={activeTemplateColors.primaryDark}
        rightSlot={
          <CoceMessageNotifications
            apiFetch={apiFetch}
            wsEvent={coceMessageWsEvent}
          />
        }
      />
      <SoftwareUpdateBanner apiFetch={apiFetch} />
      <div style={{ padding: "30px 12px" }}>
        {tab === 0 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "0.5fr 2fr 1fr",
              gap: 12,
            }}
          >
            <Card>
              <SecLabel>Modo Operativo</SecLabel>
              {pendingManualEnclavamientoMode && (
                <div
                  style={{
                    marginBottom: 10,
                    padding: "8px 10px",
                    borderRadius: 8,
                    background: "#fff7ed",
                    border: "1px solid #fdba74",
                    fontSize: 11,
                    lineHeight: 1.4,
                    color: "#9a3412",
                  }}
                >
                  <strong>En cola:</strong>{" "}
                  {toModeLabel(pendingManualEnclavamientoMode)}. Se activará
                  automáticamente cuando las entradas de bloqueo pasen a
                  inactivas.
                </div>
              )}
              {/* <div
                style={{
                  marginBottom: 10,
                  padding: "8px 10px",
                  borderRadius: 8,
                  background: C.surface,
                }}
              >
                <div style={{ fontSize: 11, color: colors.textSecondary }}>
                  Modo seleccionado
                </div>
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 700,
                    background: `linear-gradient(90deg, ${C.red} 0%, ${C.redDark} 100%)`,
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                    backgroundClip: "text",
                    color: "transparent",
                  }}
                >
                  {selectedMode
                    ? toModeLabel(selectedMode)
                    : "Sin modo seleccionado"}
                </div>
              </div> */}
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {Object.keys(rulesMap)
                  .filter(
                    (ruleKey) => rulesMap[ruleKey]?.type === "enclavamiento",
                  )
                  .map((ruleKey) => {
                    const rule = rulesMap[ruleKey];
                    const isOperativeMode = isOperativePanelMode(ruleKey);
                    const isFireMode = ruleKey === "senal_de_incendio_activada";
                    const isModeActive =
                      isOperativeMode && selectedMode === ruleKey;
                    const isToggleOn =
                      isToggleEnclavamiento(ruleKey, rule) &&
                      activeToggleRules.includes(ruleKey);
                    const isQueued =
                      isOperativeMode &&
                      pendingManualEnclavamientoMode === ruleKey;
                    const activeAccent = isFireMode ? "#E85D04" : C.red;
                    const activeAccentDark = isFireMode ? "#C2410C" : C.redDark;
                    return (
                      <button
                        key={ruleKey}
                        onClick={() => runRuleByKey(ruleKey)}
                        className="flex items-center gap-2"
                        style={{
                          textAlign: "left",
                          padding: "8px 10px",
                          borderRadius: 8,
                          border: `1px solid ${
                            isModeActive
                              ? activeAccent
                              : isQueued
                                ? "#fdba74"
                                : isToggleOn
                                  ? C.blue
                                  : C.border
                          }`,
                          background: isModeActive
                            ? `linear-gradient(90deg, ${activeAccent} 0%, ${activeAccentDark} 100%)`
                            : isQueued
                              ? "#fff7ed"
                              : isToggleOn
                                ? C.blueLight
                                : C.white,
                          color: isModeActive
                            ? C.white
                            : isToggleOn
                              ? C.blue
                              : colors.textSecondary,
                          cursor: "pointer",
                          fontSize: 12,
                          fontWeight:
                            isModeActive || isToggleOn || isQueued ? 700 : 500,
                        }}
                      >
                        <FontAwesomeIcon
                          color={
                            isModeActive ? C.white : isToggleOn ? C.blue : C.red
                          }
                          icon={faSliders}
                        />
                        {toModeLabel(ruleKey)}
                        {isQueued ? " (en cola)" : ""}
                      </button>
                    );
                  })}
              </div>
            </Card>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <Card>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr 1fr",
                    border: `1px solid ${C.border}`,
                    borderRadius: 10,
                    background: C.white,
                    overflow: "hidden",
                  }}
                >
                  <div style={{ padding: "10px 14px" }}>
                    <div
                      style={{ fontSize: 11, color: C.muted, marginBottom: 2 }}
                    >
                      <FontAwesomeIcon
                        icon={faCubes}
                        style={{ marginRight: 6, color: C.textSub }}
                      />
                      Total de placas
                    </div>
                    <div
                      style={{
                        fontSize: 30,
                        fontWeight: 700,
                        color: C.textMid,
                      }}
                    >
                      {totalModules}
                    </div>
                  </div>

                  <div
                    style={{
                      padding: "10px 14px",
                      borderLeft: `1px solid ${C.border}`,
                      borderRight: `1px solid ${C.border}`,
                    }}
                  >
                    <div
                      style={{ fontSize: 11, color: C.muted, marginBottom: 2 }}
                    >
                      <FontAwesomeIcon
                        icon={faCircleCheck}
                        style={{ marginRight: 6, color: C.green }}
                      />
                      Placas activas
                    </div>
                    <div
                      style={{ fontSize: 30, fontWeight: 700, color: C.green }}
                    >
                      {onlineModules}
                    </div>
                  </div>

                  <div style={{ padding: "10px 14px" }}>
                    <div
                      style={{ fontSize: 11, color: C.muted, marginBottom: 2 }}
                    >
                      <FontAwesomeIcon
                        icon={faSliders}
                        style={{ marginRight: 6, color: C.red }}
                      />
                      Modo activo actual
                    </div>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: selectedMode ? C.red : C.textMid,
                        marginTop: 8,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                      title={activeModeLabel}
                    >
                      {activeModeLabel}
                    </div>
                  </div>
                </div>
              </Card>
              <Card>
                <SecLabel>Estado de placas</SecLabel>
                {orderedModuleIds.map((mid) => {
                  const m = metaFor(mid);
                  const modCfg = moduleList.find((x) => x.id === mid);
                  const hasInOutAssocReg = modCfg?.relation_register != null;
                  const b = boards[mid] || {
                    connected: false,
                    inputs: [],
                    inputs_raw: [],
                    outputs: [],
                    input_overrides: [],
                    in_out_associated: null,
                  };
                  const nOut = b.outputs?.length ?? 0;
                  const nIn = b.inputs?.length ?? 0;
                  return (
                    <div
                      key={mid}
                      style={{
                        border: `1px solid ${b.connected ? C.greenBorder : C.border}`,
                        borderRadius: 8,
                        padding: 10,
                        marginBottom: 8,
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 10,
                          marginBottom: 8,
                        }}
                      >
                        <img
                          src={templateConfig.boardLogo}
                          alt="Logo placa"
                          style={{
                            width: 22,
                            height: 22,
                            objectFit: "contain",
                            alignSelf: "flex-start",
                            marginTop: 1,
                          }}
                          onError={(e) => {
                            e.currentTarget.src =
                              DEFAULT_TEMPLATE_CONFIG.boardLogo;
                          }}
                        />
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                          }}
                        >
                          <strong>{m.name}</strong>
                          <span
                            style={{
                              fontSize: 10,
                              fontWeight: 700,
                              borderRadius: 999,
                              padding: "2px 8px",
                              background: C.redFaint,
                              color: C.red,
                            }}
                          >
                            {nOut} OUT
                          </span>
                          <span
                            style={{
                              fontSize: 10,
                              fontWeight: 700,
                              borderRadius: 999,
                              padding: "2px 8px",
                              background: C.amberLight,
                              color: C.amber,
                            }}
                          >
                            {nIn} IN
                          </span>
                        </div>
                        {/* <span style={{ color: C.muted }}>{m.sub}</span> */}
                        <span
                          style={{
                            marginLeft: "auto",
                            fontFamily: "monospace",
                            color: C.muted,
                          }}
                        >
                          {boardConfigs[mid]?.host ?? "—"}
                        </span>
                        <Btn
                          small
                          variant={b.connected ? "danger" : "success"}
                          disabled={pending[`c${mid}`]}
                          onClick={() => doConnect(mid)}
                        >
                          {pending[`c${mid}`]
                            ? "..."
                            : b.connected
                              ? "Desconectar"
                              : "Conectar"}
                        </Btn>
                      </div>
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 5,
                          width: "fit-content",
                          fontSize: 10,
                          fontWeight: 700,
                          borderRadius: 999,
                          padding: "2px 8px",
                          marginBottom: 12,
                          background: b.connected ? "#DCFCE7" : "#FEE2E2",
                          color: b.connected ? "#166534" : "#B91C1C",
                        }}
                      >
                        <FontAwesomeIcon
                          icon={b.connected ? faCircleCheck : faCircleXmark}
                        />
                        {b.connected ? "Conectado" : "Desconectado"}
                      </span>
                      <div
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          color: C.red,
                          marginBottom: 6,
                        }}
                      >
                        {nOut} RELÉS DE SALIDA (OUT1..OUT{nOut || "—"})
                      </div>
                      <div
                        style={{ display: "flex", gap: 6, flexWrap: "wrap" }}
                      >
                        {(b.outputs || []).map((v, i) => (
                          <button
                            key={i}
                            onClick={() => doToggle(mid, i + 1, v)}
                            disabled={
                              !b.connected || pending[`${mid}-${i + 1}`]
                            }
                            style={{
                              width: 26,
                              height: 26,
                              borderRadius: 5,
                              border: `1px solid ${v ? C.redBorder : C.border}`,
                              background: v ? C.redFaint : C.white,
                              color: v ? C.red : C.textSub,
                              cursor: b.connected ? "pointer" : "not-allowed",
                            }}
                          >
                            {i + 1}
                          </button>
                        ))}
                      </div>
                      <div
                        style={{ marginTop: 8, fontSize: 11, color: C.textSub }}
                      >
                        Activos:{" "}
                        <strong style={{ color: C.red }}>
                          {(b.outputs || []).filter(Boolean).length}/{nOut || 0}
                        </strong>
                      </div>
                      <div
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          color: C.amber,
                          marginTop: 10,
                          marginBottom: 6,
                        }}
                      >
                        {nIn} ENTRADAS (IN1..IN{nIn || "—"}) - REAL / OVERRIDE
                      </div>
                      <div
                        style={{
                          display: "inline-block",
                          marginBottom: 6,
                          fontSize: 10,
                          fontWeight: 700,
                          color: C.blue,
                          background: C.blueLight,
                          border: `1px solid ${C.blue}44`,
                          borderRadius: 12,
                          padding: "2px 8px",
                        }}
                      >
                        Simulación / Override
                      </div>
                      <div
                        style={{
                          fontSize: 10,
                          color: C.muted,
                          marginBottom: 6,
                        }}
                      >
                        Click para ciclo: REAL -&gt; FORZADA ON -&gt; FORZADA
                        OFF -&gt; REAL
                      </div>
                      <div
                        style={{ display: "flex", gap: 6, flexWrap: "wrap" }}
                      >
                        {(b.inputs || []).map((v, i) =>
                          (() => {
                            const forcedState = b.input_overrides?.[i];
                            const isForced =
                              forcedState !== null && forcedState !== undefined;
                            const forcedOn = forcedState === true;
                            const forcedOff = forcedState === false;
                            return (
                              <button
                                key={i}
                                onClick={() => cycleInputOverride(mid, i + 1)}
                                disabled={!b.connected}
                                style={{
                                  width: 26,
                                  height: 26,
                                  borderRadius: 5,
                                  border: `1px solid ${
                                    forcedOn
                                      ? C.greenBorder
                                      : forcedOff
                                        ? C.blue
                                        : v
                                          ? C.amberBorder
                                          : C.border
                                  }`,
                                  background: forcedOn
                                    ? C.greenLight
                                    : forcedOff
                                      ? C.blueLight
                                      : v
                                        ? C.amberLight
                                        : C.white,
                                  color: forcedOn
                                    ? C.green
                                    : forcedOff
                                      ? C.blue
                                      : v
                                        ? C.amber
                                        : C.textSub,
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  fontSize: 11,
                                  fontWeight: 600,
                                  cursor: b.connected
                                    ? "pointer"
                                    : "not-allowed",
                                }}
                                title={
                                  b.input_overrides?.[i] === null
                                    ? `IN${i + 1} REAL=${b.inputs_raw?.[i] ? "ON" : "OFF"}`
                                    : `IN${i + 1} FORZADA ${b.input_overrides?.[i] ? "ON" : "OFF"} | REAL=${b.inputs_raw?.[i] ? "ON" : "OFF"}`
                                }
                              >
                                {i + 1}
                              </button>
                            );
                          })(),
                        )}
                      </div>
                      <div
                        style={{ marginTop: 8, fontSize: 11, color: C.textSub }}
                      >
                        Activas:{" "}
                        <strong style={{ color: C.amber }}>
                          {(b.inputs || []).filter(Boolean).length}/{nIn || 0}
                        </strong>
                      </div>
                      <div
                        style={{ marginTop: 4, fontSize: 10, color: C.muted }}
                      >
                        Forzadas:{" "}
                        <strong>
                          {
                            (b.input_overrides || []).filter((x) => x !== null)
                              .length
                          }
                        </strong>
                        {" · "}
                        ON:{" "}
                        <strong style={{ color: C.green }}>
                          {
                            (b.input_overrides || []).filter((x) => x === true)
                              .length
                          }
                        </strong>
                        {" · "}
                        OFF:{" "}
                        <strong style={{ color: C.blue }}>
                          {
                            (b.input_overrides || []).filter((x) => x === false)
                              .length
                          }
                        </strong>
                      </div>
                      <div
                        style={{ marginTop: 4, fontSize: 10, color: C.muted }}
                      >
                        Real (Modbus) activas:{" "}
                        <strong>
                          {(b.inputs_raw || []).filter(Boolean).length}/
                          {nIn || 0}
                        </strong>
                      </div>
                      <div
                        style={{
                          display: "flex",
                          gap: 8,
                          marginTop: 8,
                          flexWrap: "wrap",
                          alignItems: "center",
                        }}
                      >
                        <Btn
                          small
                          onClick={() => doAllOn(mid)}
                          disabled={!b.connected || nOut === 0}
                        >
                          Todas ON
                        </Btn>
                        <Btn
                          small
                          onClick={() => doAllOff(mid)}
                          disabled={!b.connected || nOut === 0}
                        >
                          Todas OFF
                        </Btn>
                        {hasInOutAssocReg && (
                          <label
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 6,
                              fontSize: 11,
                              color: C.textSub,
                              cursor:
                                b.connected && !pending[`ioa${mid}`]
                                  ? "pointer"
                                  : "not-allowed",
                              marginLeft: 4,
                            }}
                            title={
                              b.in_out_associated == null && b.connected
                                ? "Estado del equipo aún no leído; al marcar/desmarcar se envía 1/0 al registro IN↔OUT"
                                : "Acople IN↔OUT (1) / desacople (0) en el holding configurado en la placa"
                            }
                          >
                            <input
                              type="checkbox"
                              ref={(el) => {
                                if (el) {
                                  el.indeterminate =
                                    b.connected && b.in_out_associated == null;
                                }
                              }}
                              checked={b.in_out_associated === true}
                              disabled={
                                !b.connected || Boolean(pending[`ioa${mid}`])
                              }
                              onChange={(e) => {
                                setInOutAssociation(mid, e.target.checked);
                              }}
                            />
                            IN↔OUT acoplado
                          </label>
                        )}
                      </div>
                    </div>
                  );
                })}
              </Card>
            </div>
            <Card
              style={{
                padding: 15,
                overflow: "auto",
                display: "flex",
                flexDirection: "column",
              }}
            >
              <SecLabel>Actividad</SecLabel>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                  minHeight: 640,
                }}
              >
                <div
                  ref={logScrollRef}
                  style={{
                    flex: "0 0 auto",
                    height: 500,
                    minHeight: 0,
                    overflowY: "auto",
                    padding: "0 4px 8px",
                  }}
                >
                  {!serverOnline && (
                    <div style={{ color: C.red }}>API offline en `{API}`</div>
                  )}
                  {uiLog.map((e, i) => {
                    const styleByType = {
                      INFO: {
                        icon: faCircleInfo,
                        iconColor: "#2563EB",
                        badgeBg: "#DBEAFE",
                        badgeColor: "#1D4ED8",
                      },
                      OK: {
                        icon: faCircleCheck,
                        iconColor: "#16A34A",
                        badgeBg: "#DCFCE7",
                        badgeColor: "#15803D",
                      },
                      WARN: {
                        icon: faTriangleExclamation,
                        iconColor: "#D97706",
                        badgeBg: "#FEF3C7",
                        badgeColor: "#B45309",
                      },
                      ERR: {
                        icon: faCircleXmark,
                        iconColor: "#DC2626",
                        badgeBg: "#FEE2E2",
                        badgeColor: "#B91C1C",
                      },
                    };
                    const styleCfg = styleByType[e.type] || {
                      icon: faPenToSquare,
                      iconColor: C.textSub,
                      badgeBg: C.surfaceAlt,
                      badgeColor: C.textSub,
                    };
                    return (
                      <div
                        key={i}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "30px 1fr",
                          columnGap: 10,
                          paddingBottom: i === uiLog.length - 1 ? 0 : 12,
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                          }}
                        >
                          <span
                            style={{
                              width: 26,
                              height: 26,
                              borderRadius: "50%",
                              display: "inline-flex",
                              alignItems: "center",
                              justifyContent: "center",
                              background: styleCfg.badgeBg,
                              color: styleCfg.iconColor,
                            }}
                          >
                            <FontAwesomeIcon icon={styleCfg.icon} />
                          </span>
                          {i !== uiLog.length - 1 && (
                            <span
                              style={{
                                width: 2,
                                flex: 1,
                                minHeight: 20,
                                marginTop: 4,
                                background: C.border,
                                borderRadius: 2,
                              }}
                            />
                          )}
                        </div>

                        <div style={{ paddingTop: 1 }}>
                          <div
                            style={{
                              fontSize: 14,
                              fontWeight: 700,
                              color: C.textMid,
                              lineHeight: 1.25,
                            }}
                          >
                            {e.msg}
                          </div>
                          <div
                            style={{
                              marginTop: 2,
                              fontSize: 11,
                              color: C.textSub,
                            }}
                          >
                            Panel ETD8A12
                          </div>
                          <div
                            style={{
                              marginTop: 2,
                              fontSize: 11,
                              color: C.muted,
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                            }}
                          >
                            <span>{e.ts}</span>
                            <span
                              style={{
                                fontSize: 10,
                                fontWeight: 700,
                                borderRadius: 999,
                                padding: "1px 7px",
                                background: styleCfg.badgeBg,
                                color: styleCfg.badgeColor,
                              }}
                            >
                              {e.type}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div
                  style={{
                    flex: "1 1 auto",
                    minHeight: 400,
                    overflowY: "auto",
                    borderTop: `1px solid ${C.border}`,
                    paddingTop: 10,
                    paddingRight: 4,
                    paddingBottom: 8,
                  }}
                >
                  <HomeZaguanSimulation onSimulatePulse={simulateZaguanPulse} />
                </div>
              </div>
            </Card>
          </div>
        )}

        {tab === 1 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
              gap: 12,
            }}
          >
            {orderedModuleIds.map((mid) => {
              const m = metaFor(mid);
              const modCfg = moduleList.find((x) => x.id === mid);
              const b = boards[mid] || {
                connected: false,
                inputs: [],
                inputs_raw: [],
                input_overrides: [],
                outputs: [],
              };
              const nInIo = Math.max(
                b.inputs?.length || 0,
                b.inputs_raw?.length || 0,
                b.input_overrides?.length || 0,
              );
              const outputsActive = (b.outputs || []).filter(Boolean).length;
              const inputsActive = Array.from(
                { length: nInIo },
                (_, i) => inputChannelState(b, i).effective,
              ).filter(Boolean).length;
              return (
                <Card
                  key={mid}
                  style={{
                    border: `1px solid ${b.connected ? C.greenBorder : C.border}`,
                    boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      marginBottom: 6,
                    }}
                  >
                    <img
                      src={templateConfig.boardLogo}
                      alt="Logo placa"
                      style={{ width: 18, height: 18, objectFit: "contain" }}
                      onError={(e) => {
                        e.currentTarget.src = DEFAULT_TEMPLATE_CONFIG.boardLogo;
                      }}
                    />
                    <strong style={{ fontSize: 15 }}>{m.name}</strong>
                    <span
                      style={{
                        marginLeft: "auto",
                        fontSize: 10,
                        fontWeight: 700,
                        borderRadius: 999,
                        padding: "2px 8px",
                        background: b.connected ? "#DCFCE7" : "#FEE2E2",
                        color: b.connected ? "#166534" : "#B91C1C",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 5,
                      }}
                    >
                      <FontAwesomeIcon
                        icon={b.connected ? faCircleCheck : faCircleXmark}
                      />
                      {b.connected ? "Conectada" : "Desconectada"}
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      marginBottom: 10,
                      color: C.muted,
                    }}
                  >
                    {m.sub}
                  </div>

                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 8,
                      marginBottom: 10,
                    }}
                  >
                    <div
                      style={{
                        border: `1px solid ${C.border}`,
                        borderRadius: 8,
                        padding: "7px 9px",
                        background: C.white,
                      }}
                    >
                      <div
                        style={{
                          fontSize: 10,
                          color: C.muted,
                          fontWeight: 700,
                          marginBottom: 3,
                        }}
                      >
                        Salidas activas
                      </div>
                      <div
                        style={{ fontSize: 14, fontWeight: 700, color: C.red }}
                      >
                        {outputsActive}/{b.outputs?.length || 0}
                      </div>
                    </div>
                    <div
                      style={{
                        border: `1px solid ${C.border}`,
                        borderRadius: 8,
                        padding: "7px 9px",
                        background: C.white,
                      }}
                    >
                      <div
                        style={{
                          fontSize: 10,
                          color: C.muted,
                          fontWeight: 700,
                          marginBottom: 3,
                        }}
                      >
                        Entradas activas
                      </div>
                      <div
                        style={{
                          fontSize: 14,
                          fontWeight: 700,
                          color: C.amber,
                        }}
                      >
                        {inputsActive}/{b.inputs?.length || 0}
                      </div>
                    </div>
                  </div>

                  <div
                    style={{
                      marginBottom: 8,
                      fontSize: 12,
                      fontWeight: 700,
                      color: C.textMid,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <FontAwesomeIcon
                      icon={faToggleOn}
                      style={{ color: C.red }}
                    />
                    Salidas
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(6,1fr)",
                      gap: 6,
                      marginBottom: 10,
                    }}
                  >
                    {(b.outputs || []).map((v, i) => (
                      <div
                        key={i}
                        title={channelIoTitle(
                          "output",
                          i,
                          modCfg?.outputs?.[i],
                        )}
                        style={{
                          border: `1px solid ${v ? C.redBorder : C.border}`,
                          background: v ? C.redFaint : C.white,
                          borderRadius: 6,
                          padding: "7px 0",
                          fontSize: 11,
                          fontWeight: 700,
                          color: v ? C.red : C.textSub,
                          textAlign: "center",
                          cursor: "default",
                        }}
                      >{`OUT${i + 1}`}</div>
                    ))}
                  </div>

                  <div
                    style={{
                      marginBottom: 8,
                      fontSize: 12,
                      fontWeight: 700,
                      color: C.textMid,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <FontAwesomeIcon icon={faBolt} style={{ color: C.amber }} />
                    Entradas
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(6,1fr)",
                      gap: 6,
                    }}
                  >
                    {Array.from({ length: nInIo }, (_, i) => {
                      const st = inputChannelState(b, i);
                      return (
                        <div
                          key={i}
                          title={channelIoTitle(
                            "input",
                            i,
                            modCfg?.inputs?.[i],
                            {
                              activeByOverride: st.activeByOverride,
                            },
                          )}
                          style={{
                            border: `1px solid ${
                              st.forcedOn
                                ? C.greenBorder
                                : st.forcedOff
                                  ? C.blue
                                  : st.effective
                                    ? C.amberBorder
                                    : C.border
                            }`,
                            background: st.forcedOn
                              ? C.greenLight
                              : st.forcedOff
                                ? C.blueLight
                                : st.effective
                                  ? C.amberLight
                                  : C.white,
                            borderRadius: 6,
                            padding: "7px 0",
                            textAlign: "center",
                            fontSize: 11,
                            fontWeight: 700,
                            color: st.forcedOn
                              ? C.green
                              : st.forcedOff
                                ? C.blue
                                : st.effective
                                  ? C.amber
                                  : C.textSub,
                            cursor: "default",
                          }}
                        >{`IN${i + 1}`}</div>
                      );
                    })}
                  </div>
                </Card>
              );
            })}
          </div>
        )}

        {tab === 2 && (
          <Card
            style={{
              height: "calc(100vh - 170px)",
              maxHeight: "calc(100vh - 170px)",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
          >
            <SecLabel>Histórico de eventos</SecLabel>
            <div
              style={{
                marginBottom: 10,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 10,
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                <label
                  style={{
                    fontSize: 12,
                    color: C.textSub,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  Desde
                  <input
                    type="date"
                    value={histDateFrom}
                    onChange={(e) => setHistDateFrom(e.target.value)}
                    style={{
                      border: `1px solid ${C.border}`,
                      borderRadius: 8,
                      padding: "4px 8px",
                      fontSize: 12,
                    }}
                  />
                </label>
                <label
                  style={{
                    fontSize: 12,
                    color: C.textSub,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  Hasta
                  <input
                    type="date"
                    value={histDateTo}
                    onChange={(e) => setHistDateTo(e.target.value)}
                    style={{
                      border: `1px solid ${C.border}`,
                      borderRadius: 8,
                      padding: "4px 8px",
                      fontSize: 12,
                    }}
                  />
                </label>
                {(histDateFrom || histDateTo) && (
                  <Btn
                    small
                    variant="ghost"
                    onClick={() => {
                      setHistDateFrom("");
                      setHistDateTo("");
                    }}
                  >
                    Limpiar fechas
                  </Btn>
                )}
              </div>
              <div
                style={{
                  display: "flex",
                  gap: 6,
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                {["ALL", "OK", "WARN", "ERR", "INFO"].map((t) => (
                  <button
                    key={t}
                    onClick={() => setHistFilter(t)}
                    style={{
                      border: `1px solid ${C.border}`,
                      borderRadius: 16,
                      padding: "4px 8px",
                      background: histFilter === t ? C.surfaceAlt : C.white,
                    }}
                  >
                    {t}
                  </button>
                ))}
                <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                  <Btn small variant="ghost" onClick={exportHistoryCsv}>
                    Exportar CSV
                  </Btn>
                  <Btn small variant="danger" onClick={clearHistory}>
                    Borrar histórico
                  </Btn>
                </div>
              </div>
            </div>
            <div
              ref={histScrollRef}
              style={{
                flex: 1,
                minHeight: 0,
                overflowY: "auto",
                border: `1px solid ${C.border}`,
                borderRadius: 12,
                background: C.offWhite,
                padding: 10,
              }}
            >
              {filtered.length === 0 ? (
                <div
                  style={{
                    padding: 18,
                    borderRadius: 10,
                    border: `1px dashed ${C.borderMid}`,
                    background: C.white,
                    color: C.textSub,
                    fontSize: 13,
                  }}
                >
                  No hay eventos para el filtro seleccionado.
                </div>
              ) : (
                filtered.map((e, i) => {
                  const styleByType = {
                    INFO: {
                      icon: faCircleInfo,
                      iconColor: "#2563EB",
                      badgeBg: "#DBEAFE",
                      badgeColor: "#1D4ED8",
                    },
                    OK: {
                      icon: faCircleCheck,
                      iconColor: "#16A34A",
                      badgeBg: "#DCFCE7",
                      badgeColor: "#15803D",
                    },
                    WARN: {
                      icon: faTriangleExclamation,
                      iconColor: "#D97706",
                      badgeBg: "#FEF3C7",
                      badgeColor: "#B45309",
                    },
                    ERR: {
                      icon: faCircleXmark,
                      iconColor: "#DC2626",
                      badgeBg: "#FEE2E2",
                      badgeColor: "#B91C1C",
                    },
                  };
                  const styleCfg = styleByType[e.type] || {
                    icon: faPenToSquare,
                    iconColor: C.textSub,
                    badgeBg: C.surfaceAlt,
                    badgeColor: C.textSub,
                  };
                  return (
                    <div
                      key={e.id ?? i}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "30px 1fr",
                        columnGap: 10,
                        paddingBottom: i === filtered.length - 1 ? 0 : 12,
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center",
                        }}
                      >
                        <span
                          style={{
                            width: 26,
                            height: 26,
                            borderRadius: "50%",
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            background: styleCfg.badgeBg,
                            color: styleCfg.iconColor,
                          }}
                        >
                          <FontAwesomeIcon icon={styleCfg.icon} />
                        </span>
                        {i !== filtered.length - 1 && (
                          <span
                            style={{
                              width: 2,
                              flex: 1,
                              minHeight: 20,
                              marginTop: 4,
                              background: C.border,
                              borderRadius: 2,
                            }}
                          />
                        )}
                      </div>

                      <div
                        style={{
                          padding: "8px 10px",
                          borderRadius: 10,
                          border: `1px solid ${C.border}`,
                          background: C.white,
                        }}
                      >
                        <div
                          style={{
                            fontSize: 14,
                            fontWeight: 700,
                            color: C.textMid,
                            lineHeight: 1.25,
                          }}
                        >
                          {e.msg}
                        </div>
                        <div
                          style={{
                            marginTop: 4,
                            fontSize: 11,
                            color: C.textSub,
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                            flexWrap: "wrap",
                          }}
                        >
                          <span>{e.actor_username || "Sistema"}</span>
                          <span
                            style={{
                              fontSize: 10,
                              fontWeight: 700,
                              borderRadius: 999,
                              padding: "1px 7px",
                              background: C.surfaceAlt,
                              color: C.textSub,
                            }}
                          >
                            {e.actor_principal || "system"}
                          </span>
                          <span>
                            {e.board ? `Placa ${e.board}` : "Sin placa"}
                          </span>
                        </div>
                        <div
                          style={{
                            marginTop: 4,
                            fontSize: 11,
                            color: C.muted,
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                            flexWrap: "wrap",
                          }}
                        >
                          <span>{formatEventDateTime(e)}</span>
                          <span
                            style={{
                              fontSize: 10,
                              fontWeight: 700,
                              borderRadius: 999,
                              padding: "1px 7px",
                              background: styleCfg.badgeBg,
                              color: styleCfg.badgeColor,
                            }}
                          >
                            {e.type}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </Card>
        )}

        {(tab === 3 || tab === 5) && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {tab === 5 && (
              <ZaguanEsp32Panel
                apiFetchZaguan={apiFetchZaguan}
                active={tab === 5}
                activeModeLabel={activeModeLabel}
                modeRefreshKey={selectedMode}
                pendingModeRefreshKey={pendingManualEnclavamientoMode}
                ledPushKey={zaguanLedPushKey}
                pendingModeLabel={
                  pendingManualEnclavamientoMode
                    ? toModeLabel(pendingManualEnclavamientoMode)
                    : null
                }
                onSimulatePulse={simulateZaguanPulse}
                onEmulateLlaveEchada={emulateLlaveEchada}
              />
            )}
            {tab === 3 && (
              <>
                <RulesFormAssistant
                  moduleList={moduleList}
                  rulesJson={rulesJson}
                  setRulesJson={setRulesJson}
                  rulesMap={rulesMap}
                  setRulesMap={setRulesMap}
                  addUI={addUI}
                  setSelectedMode={setSelectedMode}
                />
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                  {orderedModuleIds.map((mid) => {
                    const m = metaFor(mid);
                    const mod = moduleList.find((x) => x.id === mid);
                    const host = boardConfigs[mid]?.host ?? mod?.host ?? "";
                    const port = boardConfigs[mid]?.port ?? mod?.port ?? 5000;
                    const slave_id =
                      boardConfigs[mid]?.slave_id ?? mod?.slave_id ?? 1;
                    return (
                      <Card key={mid} style={{ flex: "1 1 300px" }}>
                        <SecLabel>{m.name}</SecLabel>
                        <div style={{ fontSize: 11, marginBottom: 6 }}>IP</div>
                        <input
                          value={host}
                          onChange={(e) =>
                            setConfigs((p) => ({
                              ...p,
                              [mid]: {
                                host: e.target.value,
                                port: p[mid]?.port ?? port,
                                slave_id: p[mid]?.slave_id ?? slave_id,
                              },
                            }))
                          }
                          style={{
                            width: "100%",
                            padding: 8,
                            border: `1px solid ${C.border}`,
                            borderRadius: 6,
                            marginBottom: 8,
                          }}
                        />
                        <div style={{ fontSize: 11, marginBottom: 6 }}>
                          Puerto
                        </div>
                        <input
                          type="number"
                          value={port}
                          onChange={(e) =>
                            setConfigs((p) => ({
                              ...p,
                              [mid]: {
                                host: p[mid]?.host ?? host,
                                port: Number(e.target.value || 5000),
                                slave_id: p[mid]?.slave_id ?? slave_id,
                              },
                            }))
                          }
                          style={{
                            width: "100%",
                            padding: 8,
                            border: `1px solid ${C.border}`,
                            borderRadius: 6,
                            marginBottom: 8,
                          }}
                        />
                        <div style={{ fontSize: 11, marginBottom: 6 }}>
                          Slave ID
                        </div>
                        <input
                          type="number"
                          value={slave_id}
                          onChange={(e) =>
                            setConfigs((p) => ({
                              ...p,
                              [mid]: {
                                host: p[mid]?.host ?? host,
                                port: p[mid]?.port ?? port,
                                slave_id: normalizeSlaveId(e.target.value),
                              },
                            }))
                          }
                          style={{
                            width: "100%",
                            padding: 8,
                            border: `1px solid ${C.border}`,
                            borderRadius: 6,
                            marginBottom: 8,
                          }}
                        />
                        <Btn variant="primary" onClick={() => doConfig(mid)}>
                          Aplicar configuración
                        </Btn>
                      </Card>
                    );
                  })}
                  <Card style={{ flex: "2 1 620px" }}>
                    <SecLabel>Editor JSON de reglas</SecLabel>
                    <div
                      style={{ fontSize: 11, color: C.muted, marginBottom: 8 }}
                    >
                      Define trigger, bloqueos, enclavamiento y salidas para
                      cada modo que crees (o edita el JSON a mano).
                    </div>
                    <textarea
                      value={rulesJson}
                      onChange={(e) => setRulesJson(e.target.value)}
                      style={{
                        width: "100%",
                        minHeight: 260,
                        padding: 10,
                        border: `1px solid ${C.border}`,
                        borderRadius: 6,
                        fontFamily: "Consolas, monospace",
                        fontSize: 12,
                      }}
                    />
                    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                      <Btn variant="primary" onClick={saveRulesJson}>
                        Guardar reglas JSON
                      </Btn>
                      <Btn onClick={evaluateRulesNow}>Evaluar reglas ahora</Btn>
                    </div>
                  </Card>
                </div>
              </>
            )}
          </div>
        )}

        {tab === 4 && (
          <div>
            <Card style={{ marginBottom: 12 }}>
              <SecLabel>Nueva placa</SecLabel>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                  gap: 8,
                  alignItems: "end",
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 11, color: C.muted }}>Nombre</div>
                  <input
                    value={draftNewMod.name}
                    placeholder="Ej. Puerta calle"
                    onChange={(e) =>
                      setDraftNewMod((p) => ({ ...p, name: e.target.value }))
                    }
                    style={{
                      padding: 6,
                      width: "100%",
                      border: `1px solid ${C.border}`,
                      borderRadius: 6,
                    }}
                  />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 11, color: C.muted }}>IP</div>
                  <input
                    value={draftNewMod.host}
                    placeholder="192.168.1.101"
                    onChange={(e) =>
                      setDraftNewMod((p) => ({ ...p, host: e.target.value }))
                    }
                    style={{
                      padding: 6,
                      width: "100%",
                      border: `1px solid ${C.border}`,
                      borderRadius: 6,
                    }}
                  />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 11, color: C.muted }}>Puerto</div>
                  <input
                    type="number"
                    value={draftNewMod.port}
                    placeholder="5000"
                    onChange={(e) =>
                      setDraftNewMod((p) => ({ ...p, port: e.target.value }))
                    }
                    style={{
                      padding: 6,
                      width: "100%",
                      border: `1px solid ${C.border}`,
                      borderRadius: 6,
                    }}
                  />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 11, color: C.muted }}>Slave</div>
                  <input
                    type="number"
                    value={draftNewMod.slave_id}
                    placeholder="1"
                    onChange={(e) =>
                      setDraftNewMod((p) => ({
                        ...p,
                        slave_id: e.target.value,
                      }))
                    }
                    style={{
                      padding: 6,
                      width: "100%",
                      border: `1px solid ${C.border}`,
                      borderRadius: 6,
                    }}
                  />
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <Btn variant="primary" onClick={createDraftModule}>
                    Crear placa
                  </Btn>
                  <Btn onClick={refreshModuleList}>Recargar lista</Btn>
                </div>
              </div>
              <div style={{ fontSize: 11, color: C.muted, marginTop: 10 }}>
                La configuración de placas se guarda en SQLite. En reglas JSON,
                IN_YY_ZZ / OUT_YY_ZZ usan YY = id de placa (dos dígitos) y ZZ =
                índice de canal.
              </div>
            </Card>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))",
                gap: 12,
                alignItems: "start",
                justifyItems: "center",
              }}
            >
              {moduleList.map((mod) => (
                <ModuleDbEditor
                  key={moduleEditorKey(mod)}
                  mod={mod}
                  addUI={addUI}
                  onRefresh={refreshModuleList}
                />
              ))}
            </div>
          </div>
        )}

        {tab === 6 && (
          <TemplateConfigPanel
            draft={templateDraft}
            colors={templateColors(templateDraft)}
            onChange={updateTemplateDraft}
            onUploadMainLogo={(file) => uploadTemplateLogo(file, "mainLogo")}
            onUploadBoardLogo={(file) => uploadTemplateLogo(file, "boardLogo")}
            onSave={saveTemplateDraft}
            onReset1={resetTemplateConfig1}
            onReset2={resetTemplateConfig2}
          />
        )}

        {tab === 7 && (
          <TabletConfigPanel apiFetch={apiFetch} onNotify={addUI} />
        )}

        {tab === 8 && <SchedulesPanel apiFetch={apiFetch} onNotify={addUI} />}
      </div>
      <style>{`*{box-sizing:border-box} ::-webkit-scrollbar{width:6px;height:6px} ::-webkit-scrollbar-thumb{background:${C.borderMid};border-radius:3px}`}</style>
    </div>
  );
}
