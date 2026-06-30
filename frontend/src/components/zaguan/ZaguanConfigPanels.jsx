import { useState, useEffect } from "react";
import { LedStrip } from "./ZaguanLedComponents";
import { CANAL_INFO, ESTADOS_VALIDOS, ESTADO_META } from "./zaguanConstants";

function Field({ label, children, hint }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

function BtnEnviar({ busy, children, ...rest }) {
  return (
    <button type="submit" className="btn btn-primary" disabled={busy} {...rest}>
      {busy ? "Enviando…" : children}
    </button>
  );
}

export function ConfigRedPanel({ config, ejecutar, busy }) {
  const red = (config && config.red) || {};
  const [f, setF] = useState(null);
  useEffect(() => {
    if (config) setF({ ...(config.red || {}) });
  }, [config]);

  if (!f) {
    return (
      <p className="muted">
        Carga la configuración del dispositivo para editar la red.
      </p>
    );
  }

  const up = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const enviar = (e) => {
    e.preventDefault();
    ejecutar("configRed", {
      ip: f.ip,
      gateway: f.gateway,
      subnet: f.subnet,
      backend_ip: f.backend_ip,
      backend_puerto: Number(f.backend_puerto),
      backend_ruta: f.backend_ruta,
      pulsacion_ruta: f.pulsacion_ruta,
    });
  };

  return (
    <form className="cfg-form" onSubmit={enviar}>
      <div className="cfg-grid">
        <Field label="IP del ESP32">
          <input className="input" value={f.ip || ""} onChange={up("ip")} />
        </Field>
        <Field label="Gateway">
          <input className="input" value={f.gateway || ""} onChange={up("gateway")} />
        </Field>
        <Field label="Máscara de red">
          <input className="input" value={f.subnet || ""} onChange={up("subnet")} />
        </Field>
        <Field label="IP backend">
          <input
            className="input"
            value={f.backend_ip || ""}
            onChange={up("backend_ip")}
          />
        </Field>
        <Field label="Puerto backend">
          <input
            className="input"
            type="number"
            value={f.backend_puerto || ""}
            onChange={up("backend_puerto")}
          />
        </Field>
        <Field label="Ruta estado">
          <input
            className="input"
            value={f.backend_ruta || ""}
            onChange={up("backend_ruta")}
          />
        </Field>
        <Field label="Ruta pulsación">
          <input
            className="input"
            value={f.pulsacion_ruta || ""}
            onChange={up("pulsacion_ruta")}
          />
        </Field>
      </div>
      <p className="nota">
        Si cambias la IP del ESP32, se reconecta con la nueva dirección en &lt;2 s.
        El panel actualizará la IP de destino automáticamente.
      </p>
      <BtnEnviar busy={busy}>Aplicar configuración de red</BtnEnviar>
    </form>
  );
}

export function ConfigCanalPanel({
  config,
  ejecutar,
  busy,
  canal,
  setCanal,
  multiDevice = false,
}) {
  const c = config && config.canales && config.canales[canal - 1];
  const [leds, setLeds] = useState("");
  const [brillo, setBrillo] = useState("");
  useEffect(() => {
    if (c) {
      setLeds(c.leds);
      setBrillo(c.brillo);
    }
  }, [config, canal, c]);

  if (!c) return <p className="muted">Sin configuración cargada.</p>;

  const enviar = (e) => {
    e.preventDefault();
    ejecutar("configCanal", {
      canal,
      leds: Number(leds),
      brillo: Number(brillo),
    });
  };

  return (
    <form className="cfg-form" onSubmit={enviar}>
      {!multiDevice ? (
        <div className="canal-tabs" role="tablist">
          {[1, 2, 3, 4].map((n) => (
            <button
              key={n}
              type="button"
              role="tab"
              aria-selected={canal === n}
              className={`canal-tab${canal === n ? " is-active" : ""}`}
              onClick={() => setCanal(n)}
            >
              C{n}
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">
          Configuración del canal lógico <strong>p{canal}</strong> en este ESP (
          {CANAL_INFO[canal].nombre}).
        </p>
      )}
      <p className="muted">
        {CANAL_INFO[canal].nombre} · GPIO LED {c.gpio_led} · GPIO pulsador{" "}
        {c.gpio_boton}
      </p>
      <div className="cfg-grid">
        <Field label="Nº de LEDs activos" hint="1–100">
          <input
            className="input"
            type="number"
            min="1"
            max="100"
            value={leds}
            onChange={(e) => setLeds(e.target.value)}
          />
        </Field>
        <Field label={`Brillo — ${brillo} / 255`}>
          <input
            className="range"
            type="range"
            min="0"
            max="255"
            value={brillo}
            onChange={(e) => setBrillo(e.target.value)}
          />
        </Field>
      </div>
      <BtnEnviar busy={busy}>
        Aplicar canal {canal} en este ESP
      </BtnEnviar>
    </form>
  );
}

const VEL_HINT = {
  respiracion: "Duración del ciclo completo (ms). Por defecto 3000.",
  parpadeo: "Ciclo ON+OFF (ms). Por defecto 1000.",
  barrido: "ms entre pasos del cometa. 30 = rápido, 100 = lento.",
  fijo: "No aplica para animación fija.",
};

function rgbToHex([r, g, b]) {
  return `#${[r, g, b]
    .map((v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, "0"))
    .join("")}`;
}

function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return [0, 0, 0];
  const v = parseInt(m[1], 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

export function ConfigEstadoPanel({
  config,
  ejecutar,
  busy,
  haloOn,
  deviceCanal = 1,
  multiDevice = false,
  onActivarEstado,
}) {
  const [estado, setEstado] = useState("libre");
  const [canal, setCanal] = useState(deviceCanal);
  const [color, setColor] = useState([0, 200, 0]);
  const [animacion, setAnimacion] = useState("respiracion");
  const [velocidad, setVelocidad] = useState(3000);
  const [activarEnDispositivo, setActivarEnDispositivo] = useState(true);

  const canalEfectivo = multiDevice ? deviceCanal : canal || deviceCanal;

  useEffect(() => {
    if (multiDevice) setCanal(deviceCanal);
  }, [deviceCanal, multiDevice]);

  useEffect(() => {
    if (!config) return;
    const c = config.canales[(canalEfectivo || 1) - 1];
    const e = c && c.estados.find((x) => x.estado === estado);
    if (e) {
      setColor(e.color.slice());
      setAnimacion(e.animacion);
      setVelocidad(e.velocidad);
    }
  }, [config, estado, canalEfectivo]);

  const enviar = async (ev) => {
    ev.preventDefault();
    const payload = { estado, color, animacion, velocidad: Number(velocidad) };
    const targetCanal = multiDevice ? deviceCanal : canal;
    if (targetCanal) payload.canal = targetCanal;
    await ejecutar("configEstado", payload);
    if (activarEnDispositivo && targetCanal && onActivarEstado) {
      await onActivarEstado(targetCanal, estado);
    }
  };

  return (
    <form className="cfg-form" onSubmit={enviar}>
      <p className="muted">
        Define color y animación de cada estado. Para cambiar el LED en vivo,
        marca «Activar en el dispositivo» o usa los botones Libre / Ocupado en
        la tarjeta del canal.
        {multiDevice ? (
          <>
            {" "}
            Con varios ESP, la configuración se envía al dispositivo de{" "}
            <strong>p{deviceCanal}</strong> (fila seleccionada en la tabla de
            red).
          </>
        ) : null}
      </p>
      <div className="cfg-grid">
        <Field label="Estado a configurar">
          <select
            className="input"
            value={estado}
            onChange={(e) => setEstado(e.target.value)}
          >
            {ESTADOS_VALIDOS.map((s) => (
              <option key={s} value={s}>
                {ESTADO_META[s].label}
              </option>
            ))}
          </select>
        </Field>
        {!multiDevice ? (
          <Field label="Canal">
            <select
              className="input"
              value={canal}
              onChange={(e) => setCanal(Number(e.target.value))}
            >
              <option value={0}>Todos los canales</option>
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  Canal {n} — {CANAL_INFO[n].puerta}
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <Field label="Dispositivo">
            <span className="input input-readonly">
              Canal {deviceCanal} — {CANAL_INFO[deviceCanal].puerta}
            </span>
          </Field>
        )}
        <Field label="Activar en el dispositivo">
          <label className="check-row">
            <input
              type="checkbox"
              checked={activarEnDispositivo}
              onChange={(e) => setActivarEnDispositivo(e.target.checked)}
            />
            <span>
              Tras guardar, poner el LED en este estado (POST /api/p
              {canalEfectivo || "n"}/estado)
            </span>
          </label>
        </Field>
        <Field label="Color RGB">
          <span className="color-row">
            <input
              className="color-input"
              type="color"
              value={rgbToHex(color)}
              onChange={(e) => setColor(hexToRgb(e.target.value))}
            />
            <code className="mono">[{color.join(", ")}]</code>
          </span>
        </Field>
        <Field label="Animación">
          <select
            className="input"
            value={animacion}
            onChange={(e) => setAnimacion(e.target.value)}
          >
            <option value="fijo">Fijo</option>
            <option value="respiracion">Respiración</option>
            <option value="parpadeo">Parpadeo (80/20)</option>
            <option value="barrido">Barrido (cometa)</option>
          </select>
        </Field>
        <Field label="Velocidad (ms)" hint={VEL_HINT[animacion]}>
          <input
            className="input"
            type="number"
            min="0"
            value={velocidad}
            disabled={animacion === "fijo"}
            onChange={(e) => setVelocidad(e.target.value)}
          />
        </Field>
        <Field label="Vista previa">
          <span className="preview-box">
            <LedStrip
              leds={14}
              brillo={200}
              estadoCfg={{ color, animacion, velocidad: Number(velocidad) }}
              haloOn={haloOn}
            />
          </span>
        </Field>
      </div>
      <BtnEnviar busy={busy}>
        {canalEfectivo
          ? `Aplicar y${activarEnDispositivo ? " activar" : ""} en canal ${canalEfectivo}`
          : "Aplicar a los 4 canales"}
      </BtnEnviar>
    </form>
  );
}

function FlashPreview({ color, nFlashes, duracion, fireKey }) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!fireKey) return;
    let cancel = false;
    const dur = Math.max(40, duracion || 150);
    (async () => {
      for (let i = 0; i < Math.max(1, nFlashes || 1); i++) {
        if (cancel) return;
        setOn(true);
        await new Promise((r) => setTimeout(r, dur));
        if (cancel) return;
        setOn(false);
        await new Promise((r) => setTimeout(r, dur * 0.6));
      }
    })();
    return () => {
      cancel = true;
      setOn(false);
    };
  }, [fireKey, nFlashes, duracion]);

  const rgb = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
  return (
    <span
      className={`flash-preview${on ? "" : " flash-preview-idle"}`}
      style={{
        background: on ? rgb : "var(--bg-inset)",
        boxShadow: on ? `0 0 22px ${rgb}` : "none",
      }}
    >
      {on ? "FLASH" : "pulsa “Probar”"}
    </span>
  );
}

export function ConfigFlashPanel({ config, ejecutar, busy }) {
  const fl =
    (config && config.flash) || {
      color: [0, 200, 0],
      n_flashes: 1,
      duracion_ms: 150,
    };
  const [color, setColor] = useState(fl.color);
  const [nFlashes, setNFlashes] = useState(fl.n_flashes);
  const [duracion, setDuracion] = useState(fl.duracion_ms);
  const [fireKey, setFireKey] = useState(0);

  useEffect(() => {
    if (config && config.flash) {
      setColor(config.flash.color);
      setNFlashes(config.flash.n_flashes);
      setDuracion(config.flash.duracion_ms);
    }
  }, [config]);

  const enviar = (e) => {
    e.preventDefault();
    ejecutar("configFlash", {
      color,
      n_flashes: Number(nFlashes),
      duracion_ms: Number(duracion),
    });
  };

  return (
    <form className="cfg-form" onSubmit={enviar}>
      <p className="muted">
        Destello de confirmación que muestra el pulsador al detectar una pulsación
        válida (estados libre, ocupado y abriendo).
      </p>
      <div className="cfg-grid">
        <Field label="Color del flash">
          <span className="color-row">
            <input
              className="color-input"
              type="color"
              value={rgbToHex(color)}
              onChange={(e) => setColor(hexToRgb(e.target.value))}
            />
            <code className="mono">[{color.join(", ")}]</code>
          </span>
        </Field>
        <Field label="Nº de destellos" hint="1–5">
          <input
            className="input"
            type="number"
            min="1"
            max="5"
            value={nFlashes}
            onChange={(e) => setNFlashes(e.target.value)}
          />
        </Field>
        <Field label="Duración por destello (ms)" hint="40–800">
          <input
            className="input"
            type="number"
            min="40"
            max="800"
            value={duracion}
            onChange={(e) => setDuracion(e.target.value)}
          />
        </Field>
        <Field label="Previsualización">
          <span className="flash-row">
            <FlashPreview
              color={color}
              nFlashes={Number(nFlashes)}
              duracion={Number(duracion)}
              fireKey={fireKey}
            />
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => setFireKey((k) => k + 1)}
            >
              Probar
            </button>
          </span>
        </Field>
      </div>
      <p className="nota">
        El doble destello rojo de un canal en estado <strong>apagado</strong> está
        fijo en el firmware y no se configura aquí.
      </p>
      <BtnEnviar busy={busy}>Aplicar flash de confirmación</BtnEnviar>
    </form>
  );
}

export function formatUptime(s) {
  if (s == null) return "—";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h}h ${String(m).padStart(2, "0")}m ${String(sec).padStart(2, "0")}s`;
}

export function OtaPanel({ ota, onRefresh, busy }) {
  return (
    <div className="cfg-form">
      {ota ? (
        <dl className="ota-dl">
          <div>
            <dt>Firmware</dt>
            <dd className="mono">v{ota.version}</dd>
          </div>
          <div>
            <dt>Versión anterior</dt>
            <dd className="mono">v{ota.version_anterior}</dd>
          </div>
          <div>
            <dt>Validación OTA</dt>
            <dd>
              {ota.pendiente_validacion ? (
                <span className="badge badge-abriendo">
                  Pendiente — rollback en {ota.rollback_timeout_s}s si no sincroniza
                </span>
              ) : (
                <span className="badge badge-libre">Validado</span>
              )}
            </dd>
          </div>
          <div>
            <dt>Sincronización</dt>
            <dd>
              {ota.sync_completada ? (
                <span className="badge badge-libre">Completada</span>
              ) : (
                <span className="badge badge-ocupado">Pendiente</span>
              )}
            </dd>
          </div>
          <div>
            <dt>Uptime</dt>
            <dd className="mono">{formatUptime(ota.uptime_s)}</dd>
          </div>
        </dl>
      ) : (
        <p className="muted">Sin datos. Consulta la versión del dispositivo.</p>
      )}
      <p className="nota">
        La actualización OTA se realiza por TCP en el puerto 8266 (protocolo
        binario, fuera del alcance de este panel). Durante el flasheo los LEDs se
        muestran en azul.
      </p>
      <button type="button" className="btn" onClick={onRefresh} disabled={busy}>
        Consultar versión OTA
      </button>
    </div>
  );
}

export function EventLog({ eventos, onClear }) {
  return (
    <div className="event-log">
      <div className="event-log-head">
        <h2 className="panel-title">Registro de eventos</h2>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
          Limpiar
        </button>
      </div>
      <div className="event-log-body">
        {eventos.length === 0 ? (
          <p className="muted">Sin eventos todavía.</p>
        ) : (
          eventos.map((ev) => (
            <div key={ev.id} className={`log-row log-${ev.tipo}`}>
              <span className="log-ts mono">{ev.hora}</span>
              <span className={`log-tag log-tag-${ev.tipo}`}>
                {ev.tipo.toUpperCase()}
              </span>
              <span className="log-msg">{ev.msg}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
