import { useCallback, useEffect, useMemo, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCircleCheck,
  faCircleXmark,
  faDoorOpen,
  faNetworkWired,
  faRotate,
} from "@fortawesome/free-solid-svg-icons";
import { LedStrip } from "./zaguan/ZaguanLedComponents";
import {
  CANAL_DEFAULT_IPS,
  CANAL_INFO,
  ESTADO_META,
} from "./zaguan/zaguanConstants";
import { createZaguanDeviceApi } from "./zaguan/zaguanDeviceApi";

const C = {
  red: "var(--template-primary)",
  redDark: "var(--template-primary-dark)",
  white: "#FFFFFF",
  surface: "#F5F5F5",
  border: "#E0E0E0",
  muted: "#999999",
  text: "#1A1A1A",
  textSub: "#555555",
  green: "#00873D",
  greenLight: "#E8F5EE",
  greenBorder: "#99DDBB",
  amber: "#C87A00",
  amberLight: "#FFF8E8",
  blue: "#0066CC",
  blueLight: "#E8F0FF",
};

const ESTADO_LED = {
  libre: { color: [0, 200, 80], animacion: "fijo", velocidad: 0 },
  ocupado: { color: [220, 40, 40], animacion: "fijo", velocidad: 0 },
  abriendo: { color: [255, 170, 0], animacion: "respiracion", velocidad: 1800 },
  apagado: { color: [48, 48, 48], animacion: "fijo", velocidad: 0 },
};

const ESTADO_BADGE = {
  libre: { bg: "#DCFCE7", fg: "#166534", border: "#86EFAC" },
  ocupado: { bg: "#FEE2E2", fg: "#B91C1C", border: "#FCA5A5" },
  abriendo: { bg: "#FEF3C7", fg: "#B45309", border: "#FCD34D" },
  apagado: { bg: "#F3F4F6", fg: "#6B7280", border: "#D1D5DB" },
};

const PUERTAS = [
  {
    id: "p1",
    titulo: "Puerta P1",
    subtitulo: "Calle · acceso exterior",
    canales: [1, 3],
  },
  {
    id: "p2",
    titulo: "Puerta P2",
    subtitulo: "Oficina · acceso interior",
    canales: [2, 4],
  },
];

function resolveIp(canal, channels) {
  const ch = channels?.[`p${canal}`] || {};
  const resolved = String(ch.resolved_host || "").trim();
  if (resolved) return resolved;
  const override = String(ch.host || "").trim();
  if (override) return override;
  return CANAL_DEFAULT_IPS[canal] || "—";
}

function EstadoPill({ estado }) {
  const key = ESTADO_META[estado] ? estado : "apagado";
  const meta = ESTADO_META[key];
  const style = ESTADO_BADGE[key];
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: 0.4,
        textTransform: "uppercase",
        borderRadius: 999,
        padding: "3px 9px",
        background: style.bg,
        color: style.fg,
        border: `1px solid ${style.border}`,
      }}
    >
      {meta.label}
    </span>
  );
}

function DeviceCard({ canal, estado, online, ip, port }) {
  const info = CANAL_INFO[canal];
  const ledCfg = ESTADO_LED[estado] || ESTADO_LED.apagado;

  return (
    <div
      style={{
        border: `1px solid ${online ? C.greenBorder : C.border}`,
        borderRadius: 14,
        padding: "14px 14px 12px",
        background: online
          ? "linear-gradient(165deg, #FFFFFF 0%, #F7FBF8 100%)"
          : "linear-gradient(165deg, #FFFFFF 0%, #FAFAFA 100%)",
        boxShadow: online
          ? "0 2px 10px rgba(0, 135, 61, 0.06)"
          : "0 1px 4px rgba(0,0,0,0.03)",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        transition: "border-color 0.2s ease, box-shadow 0.2s ease",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              marginBottom: 4,
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontWeight: 800,
                letterSpacing: 0.8,
                color: C.red,
                background: "color-mix(in srgb, var(--template-primary) 10%, white)",
                border: `1px solid color-mix(in srgb, var(--template-primary) 22%, white)`,
                borderRadius: 6,
                padding: "2px 7px",
              }}
            >
              {info.corto}
            </span>
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: C.text,
              }}
            >
              {info.rol}
            </span>
          </div>
          <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.3 }}>
            {info.ubicacion} · {info.puerta}
          </div>
        </div>
        <span
          style={{
            flexShrink: 0,
            fontSize: 10,
            fontWeight: 700,
            borderRadius: 999,
            padding: "3px 8px",
            background: online ? "#DCFCE7" : "#FEE2E2",
            color: online ? "#166534" : "#B91C1C",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          <FontAwesomeIcon icon={online ? faCircleCheck : faCircleXmark} />
          {online ? "Online" : "Offline"}
        </span>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 12px",
          borderRadius: 10,
          background: "#F3F5F8",
          border: "1px solid #E0E4EA",
        }}
      >
        <LedStrip
          leds={12}
          brillo={online ? 180 : 60}
          estadoCfg={ledCfg}
          ledPx={8}
          gapPx={3}
          glow={online}
          haloOn={online}
        />
        <div style={{ marginLeft: "auto" }}>
          <EstadoPill estado={estado} />
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 10px",
          borderRadius: 10,
          background: C.blueLight,
          border: "1px solid #C7DBF7",
        }}
      >
        <FontAwesomeIcon
          icon={faNetworkWired}
          style={{ color: C.blue, fontSize: 12 }}
        />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: 0.6,
              textTransform: "uppercase",
              color: C.blue,
              marginBottom: 1,
            }}
          >
            IP asociada
          </div>
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              color: C.text,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={port ? `${ip}:${port}` : ip}
          >
            {ip}
            {port ? (
              <span style={{ color: C.muted, fontWeight: 600 }}>:{port}</span>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function DevicesAffiliatedPanel({
  apiFetchZaguan,
  active = true,
}) {
  const api = useMemo(
    () => createZaguanDeviceApi(apiFetchZaguan),
    [apiFetchZaguan],
  );
  const [channels, setChannels] = useState({});
  const [estados, setEstados] = useState({
    1: "apagado",
    2: "apagado",
    3: "apagado",
    4: "apagado",
  });
  const [onlineMap, setOnlineMap] = useState({
    1: false,
    2: false,
    3: false,
    4: false,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async (silencioso = false) => {
    if (!apiFetchZaguan) return;
    if (!silencioso) setLoading(true);
    setError("");
    try {
      const [target, estadoRes, pingRes] = await Promise.all([
        api.getTarget().catch(() => null),
        apiFetchZaguan("/api/zaguan/estado").catch(() => null),
        api.pingAll().catch(() => null),
      ]);

      if (target?.channels) {
        setChannels(target.channels);
      }

      if (estadoRes) {
        const next = {};
        for (let n = 1; n <= 4; n += 1) {
          const est = estadoRes[`p${n}`];
          if (est) next[n] = est;
        }
        if (Object.keys(next).length) {
          setEstados((prev) => ({ ...prev, ...next }));
        }
      }

      if (pingRes?.channels) {
        const map = { 1: false, 2: false, 3: false, 4: false };
        for (let n = 1; n <= 4; n += 1) {
          const entry = pingRes.channels[`p${n}`];
          map[n] = Boolean(entry?.ok);
        }
        setOnlineMap(map);
      }
    } catch (e) {
      setError(e?.message || "No se pudo cargar dispositivos");
    } finally {
      if (!silencioso) setLoading(false);
    }
  }, [api, apiFetchZaguan]);

  useEffect(() => {
    if (!active) return undefined;
    refresh(true);
    const id = setInterval(() => refresh(true), 8000);
    return () => clearInterval(id);
  }, [active, refresh]);

  return (
    <div
      style={{
        background: C.white,
        border: `1px solid ${C.border}`,
        borderRadius: 20,
        padding: 18,
        boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginBottom: 14,
          paddingBottom: 12,
          borderBottom: `1px solid ${C.border}`,
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 10,
            display: "grid",
            placeItems: "center",
            background: `linear-gradient(135deg, color-mix(in srgb, var(--template-primary) 18%, white), color-mix(in srgb, var(--template-primary) 8%, white))`,
            color: C.red,
            border: `1px solid color-mix(in srgb, var(--template-primary) 25%, white)`,
          }}
        >
          <FontAwesomeIcon icon={faDoorOpen} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 800,
              letterSpacing: 1.2,
              textTransform: "uppercase",
              background: `linear-gradient(90deg, ${C.red} 0%, ${C.redDark} 100%)`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            Dispositivos afiliados
          </div>
          <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>
            Puertas del sistema con tiras LED e IP asociada
          </div>
        </div>
        <button
          type="button"
          onClick={() => refresh(false)}
          disabled={loading}
          title="Actualizar estado"
          style={{
            border: `1px solid ${C.border}`,
            background: C.surface,
            borderRadius: 10,
            width: 36,
            height: 36,
            cursor: loading ? "wait" : "pointer",
            color: C.textSub,
            display: "grid",
            placeItems: "center",
          }}
        >
          <FontAwesomeIcon
            icon={faRotate}
            spin={loading}
            style={{ fontSize: 13 }}
          />
        </button>
      </div>

      {error ? (
        <div
          style={{
            marginBottom: 12,
            padding: "10px 12px",
            borderRadius: 10,
            background: "#FEF2F2",
            border: "1px solid #FECACA",
            color: "#B91C1C",
            fontSize: 12,
          }}
        >
          {error}
        </div>
      ) : null}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
          gap: 14,
        }}
      >
        {PUERTAS.map((puerta) => (
          <div
            key={puerta.id}
            style={{
              borderRadius: 16,
              border: `1px solid ${C.border}`,
              background:
                "linear-gradient(180deg, #FAFBFC 0%, #FFFFFF 48%, #FFFFFF 100%)",
              padding: 14,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <div
                style={{
                  width: 8,
                  height: 28,
                  borderRadius: 999,
                  background: `linear-gradient(180deg, ${C.red}, ${C.redDark})`,
                }}
              />
              <div>
                <div
                  style={{
                    fontSize: 15,
                    fontWeight: 800,
                    color: C.text,
                    letterSpacing: 0.2,
                  }}
                >
                  {puerta.titulo}
                </div>
                <div style={{ fontSize: 11, color: C.muted }}>
                  {puerta.subtitulo}
                </div>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                gap: 10,
              }}
            >
              {puerta.canales.map((canal) => {
                const ch = channels[`p${canal}`] || {};
                const ip = resolveIp(canal, channels);
                const port = ch.resolved_port || ch.port || null;
                return (
                  <DeviceCard
                    key={canal}
                    canal={canal}
                    estado={estados[canal] || "apagado"}
                    online={Boolean(onlineMap[canal])}
                    ip={ip}
                    port={port}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
