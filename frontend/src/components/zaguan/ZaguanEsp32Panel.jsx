import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import {
  CANAL_INFO,
  ESTADOS_VALIDOS,
  ESTADO_META,
  TWEAK_DEFAULTS,
  withWinhoseParpadeo,
} from "./zaguanConstants";
import { createZaguanDeviceApi } from "./zaguanDeviceApi";
import { LedStrip, ZaguanDiagram, EstadoBadge } from "./ZaguanLedComponents";
import {
  ConfigRedPanel,
  ConfigCanalPanel,
  ConfigEstadoPanel,
  ConfigFlashPanel,
  OtaPanel,
  EventLog,
} from "./ZaguanConfigPanels";
import {
  useTweaks,
  TweaksPanel,
  TweakSection,
  TweakRadio,
  TweakToggle,
  TweakSlider,
} from "./ZaguanTweaksPanel";
import { ZaguanSimulationSection } from "./ZaguanSimulationSection";
import "./zaguanEsp32.css";

let _logId = 0;

function estadosFromBackendPayload(r) {
  const nuevos = {};
  for (let n = 1; n <= 4; n += 1) {
    const est = r[`p${n}`];
    if (est) nuevos[n] = est;
  }
  return nuevos;
}

export default function ZaguanEsp32Panel({
  apiFetchZaguan,
  active = true,
  activeModeLabel = "Sin modo seleccionado",
  modeRefreshKey = null,
  pendingModeRefreshKey = null,
  ledPushKey = 0,
  pendingModeLabel = null,
  onSimulatePulse,
  onEmulateLlaveEchada,
}) {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [tweaksOpen, setTweaksOpen] = useState(false);

  const [target, setTarget] = useState({ host: "", port: 80, timeout_s: 2 });
  const [ipDraft, setIpDraft] = useState("");
  const [online, setOnline] = useState(false);
  const [sync, setSync] = useState(false);
  const [estados, setEstados] = useState({
    1: "apagado",
    2: "apagado",
    3: "apagado",
    4: "apagado",
  });
  const [pulsaciones, setPulsaciones] = useState({ 1: 0, 2: 0, 3: 0, 4: 0 });
  const [config, setConfig] = useState(null);
  const [ota, setOta] = useState(null);
  const [eventos, setEventos] = useState([]);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("red");
  const [canalCfg, setCanalCfg] = useState(1);
  const [canalSel, setCanalSel] = useState(null);
  const [winhoseParpadeo, setWinhoseParpadeo] = useState({});
  const pulsRef = useRef(pulsaciones);
  pulsRef.current = pulsaciones;

  const api = useMemo(
    () => createZaguanDeviceApi(apiFetchZaguan),
    [apiFetchZaguan],
  );

  const [pulsos, setPulsos] = useState({});
  const pulsoTimers = useRef({});

  const marcarPulso = useCallback((canal) => {
    canal = Number(canal);
    setPulsos((p) => ({ ...p, [canal]: true }));
    clearTimeout(pulsoTimers.current[canal]);
    pulsoTimers.current[canal] = setTimeout(() => {
      setPulsos((p) => ({ ...p, [canal]: false }));
    }, 1800);
  }, []);

  const log = useCallback((tipo, msg) => {
    const hora = new Date().toLocaleTimeString("es-ES", { hour12: false });
    setEventos((prev) =>
      [{ id: ++_logId, tipo, msg, hora }, ...prev].slice(0, 200),
    );
  }, []);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    api
      .getTarget()
      .then((t) => {
        if (cancelled) return;
        const next = {
          host: t.host || "",
          port: Number(t.port || 80),
          timeout_s: Number(t.timeout_s || 2),
        };
        setTarget(next);
        setIpDraft(next.host);
      })
      .catch((e) => log("err", `Target: ${e.message}`));
    return () => {
      cancelled = true;
    };
  }, [api, active, log]);

  const refreshBackendEstado = useCallback(
    async (silencioso = true) => {
      try {
        const r = await apiFetchZaguan("/api/zaguan/estado");
        const nuevos = estadosFromBackendPayload(r);
        if (Object.keys(nuevos).length) {
          setEstados((p) => ({ ...p, ...nuevos }));
        }
        setWinhoseParpadeo(r._autoservicio?.winhose_libre_parpadeo || {});
        if (!silencioso) {
          log("rx", `LED orquestador: ${JSON.stringify(nuevos)}`);
        }
      } catch (e) {
        if (!silencioso) {
          log("err", `Estado backend: ${e.message || "error"}`);
        }
      }
    },
    [apiFetchZaguan, log],
  );

  useEffect(() => {
    if (!active) return;
    refreshBackendEstado(true);
  }, [active, modeRefreshKey, pendingModeRefreshKey, ledPushKey, refreshBackendEstado]);

  useEffect(() => {
    if (!active) return;
    const onFocus = () => {
      refreshBackendEstado(true);
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [active, refreshBackendEstado]);

  const ejecutar = useCallback(
    async (metodo, ...args) => {
      const descripciones = {
        setEstado: (c, e) => `POST /api/p${c}/estado {"estado":"${e}"}`,
        configRed: () => "POST /api/config/red",
        configCanal: (p) =>
          `POST /api/config/canal {canal:${p.canal}, leds:${p.leds}, brillo:${p.brillo}}`,
        configEstado: (p) =>
          `POST /api/config/estado {estado:"${p.estado}"${p.canal ? `, canal:${p.canal}` : " → todos"}}`,
        configFlash: (p) =>
          `POST /api/config/flash {color:[${p.color}], n_flashes:${p.n_flashes}, duracion_ms:${p.duracion_ms}}`,
        getConfig: () => "GET /api/config",
        getEstado: () => "GET /api/estado",
        getOtaVersion: () => "GET /api/ota/version",
      };
      setBusy(true);
      log(
        "tx",
        descripciones[metodo] ? descripciones[metodo](...args) : metodo,
      );
      try {
        const res = await api[metodo](...args);
        log("rx", `OK — ${JSON.stringify(res).slice(0, 140)}`);
        setBusy(false);
        return res;
      } catch (err) {
        const msg =
          err.name === "AbortError" ? "Sin respuesta (timeout)" : err.message;
        log("err", `${metodo}: ${msg}`);
        setBusy(false);
        throw err;
      }
    },
    [api, log],
  );

  const refreshDeviceEstado = useCallback(
    async (silencioso = true) => {
      try {
        const data = await api.getEstado();
        const nuevos = {};
        const nuevasPuls = {};
        (data.canales || []).forEach((c) => {
          nuevos[c.canal] = c.estado;
          nuevasPuls[c.canal] = c.pulsaciones;
        });
        Object.keys(nuevasPuls).forEach((k) => {
          const antes = pulsRef.current[k] || 0;
          if (nuevasPuls[k] > antes && antes !== 0) {
            log(
              "btn",
              `Pulsación en canal ${k} — total ${nuevasPuls[k]} desde el arranque`,
            );
            marcarPulso(k);
          }
        });
        setPulsaciones((p) => ({ ...p, ...nuevasPuls }));
        setSync(!!data.sync);
        if (!silencioso) {
          log("rx", `ESP32 hardware: ${JSON.stringify(nuevos)}`);
        }
      } catch {
        /* el ping gestiona el estado online */
      }
    },
    [api, log, marcarPulso],
  );

  useEffect(() => {
    if (!active) return;
    let vivo = true;
    const hacerPing = async () => {
      try {
        const r = await api.ping();
        if (!vivo) return;
        const estaba = online;
        setOnline(!!r.pong);
        setSync(!!r.sync);
        if (!estaba && r.pong) {
          log(
            "rx",
            `Dispositivo en línea en ${target.host || ipDraft} (sync: ${r.sync ? "sí" : "no"})`,
          );
          api
            .getConfig()
            .then(setConfig)
            .catch(() => {});
          api
            .getOtaVersion()
            .then(setOta)
            .catch(() => {});
          api
            .getOtaVersion()
            .then(setOta)
            .catch(() => {});
          refreshDeviceEstado();
        }
      } catch (e) {
        if (!vivo) return;
        log("err", e.message || `Sin respuesta de ${target.host || ipDraft}`);
        setOnline(false);
      }
    };
    hacerPing();
    const intPing = setInterval(hacerPing, Math.max(3, t.intervaloPing) * 1000);
    return () => {
      vivo = false;
      clearInterval(intPing);
    };
  }, [
    api,
    online,
    t.intervaloPing,
    refreshDeviceEstado,
    active,
    log,
    target.host,
    ipDraft,
  ]);

  const handleSimulatePulse = useCallback(
    async (canal) => {
      if (onSimulatePulse) {
        await onSimulatePulse(canal);
      }
      marcarPulso(canal);
      await refreshBackendEstado(true);
    },
    [onSimulatePulse, marcarPulso, refreshBackendEstado],
  );

  const handleEmulateLlaveEchada = useCallback(
    async (llaveId, action) => {
      if (onEmulateLlaveEchada) {
        await onEmulateLlaveEchada(llaveId, action);
      }
      await refreshBackendEstado(true);
    },
    [onEmulateLlaveEchada, refreshBackendEstado],
  );

  const cambiarEstado = async (canal, estado) => {
    try {
      await ejecutar("setEstado", canal, estado);
      setEstados((p) => ({ ...p, [canal]: estado }));
    } catch {
      /* logged */
    }
  };

  const conectar = async (e) => {
    e.preventDefault();
    const nueva = ipDraft.trim();
    if (!nueva) return;
    setOnline(false);
    setConfig(null);
    setOta(null);
    const nextTarget = { ...target, host: nueva };
    setTarget(nextTarget);
    log("tx", `Conectando con ${nueva}…`);
    try {
      await api.saveTarget(nextTarget);
      log("rx", "Target guardado en backend");
    } catch (err) {
      log("err", `No se pudo guardar target: ${err.message}`);
    }
  };

  const enviarConfig = async (metodo, payload) => {
    try {
      const res = await ejecutar(metodo, payload);
      if (metodo === "configRed" && payload.ip && payload.ip !== target.host) {
        log(
          "rx",
          `IP cambiada en caliente → el panel apunta ahora a ${payload.ip}`,
        );
        const next = { ...target, host: payload.ip };
        setTarget(next);
        setIpDraft(payload.ip);
        api.saveTarget(next).catch(() => {});
      }
      api
        .getConfig()
        .then(setConfig)
        .catch(() => {});
      return res;
    } catch {
      return null;
    }
  };

  const refreshOta = async () => {
    try {
      setOta(await ejecutar("getOtaVersion"));
    } catch {
      /* logged */
    }
  };

  const estadoCfgDe = (canal, estado) => {
    const c = config && config.canales && config.canales[canal - 1];
    if (!c) {
      return withWinhoseParpadeo(
        canal,
        estado,
        { color: [0, 0, 0], animacion: "fijo", velocidad: 0 },
        winhoseParpadeo,
      );
    }
    const base =
      c.estados.find((x) => x.estado === estado) || {
        color: [0, 0, 0],
        animacion: "fijo",
        velocidad: 0,
      };
    return withWinhoseParpadeo(canal, estado, base, winhoseParpadeo);
  };

  const haloOn = t.halo;

  const renderCanalCard = (n) => {
    const c = config && config.canales && config.canales[n - 1];
    return (
      <article
        key={n}
        className={`panel canal-card${canalSel === n ? " is-selected" : ""}`}
        data-screen-label={`Canal ${n}`}
      >
        <header className="canal-head">
          <div>
            <span className="canal-chip">C{n}</span>
            <h3 className="canal-nombre">{CANAL_INFO[n].nombre}</h3>
          </div>
          <EstadoBadge estado={estados[n]} />
        </header>
        <div className="canal-strip">
          <LedStrip
            leds={Math.min(c ? c.leds : 10, 26)}
            brillo={c ? c.brillo : 150}
            estadoCfg={estadoCfgDe(n, estados[n])}
            haloOn={haloOn}
          />
        </div>
        <div
          className="canal-estados"
          role="group"
          aria-label={`Estado del canal ${n}`}
        >
          {ESTADOS_VALIDOS.map((s) => (
            <button
              key={s}
              type="button"
              className={`estado-btn estado-btn-${s}${estados[n] === s ? " is-active" : ""}`}
              disabled={!online || busy}
              onClick={() => cambiarEstado(n, s)}
            >
              {ESTADO_META[s].label}
            </button>
          ))}
        </div>
        <footer className="canal-meta mono">
          <span>{c ? `${c.leds} LEDs` : "— LEDs"}</span>
          <span>{c ? `brillo ${c.brillo}/255` : ""}</span>
          <span>{pulsaciones[n] || 0} pulsaciones</span>
        </footer>
      </article>
    );
  };

  return (
    <div
      className="zaguan-esp32-app app"
      data-theme="claro"
      data-density={t.densidad}
      data-halo={t.halo ? "on" : "off"}
    >
      <header className="topbar">
        <div className="brand">
          <span className="brand-sub">
            Panel de control · ESP32-S3-ETH zaguán
          </span>
        </div>
        <form className="conn" onSubmit={conectar}>
          <span className={`dot ${online ? "dot-on" : "dot-off"}`} />
          <span className="conn-status">
            {online ? "En línea" : "Sin conexión"}
          </span>
          <input
            className="input input-ip mono"
            value={ipDraft}
            spellCheck={false}
            onChange={(e) => setIpDraft(e.target.value)}
            aria-label="IP del ESP32"
          />
          <button type="submit" className="btn btn-sm">
            Conectar
          </button>
        </form>
        <div className="topbar-meta">
          <span className={`badge ${sync ? "badge-libre" : "badge-abriendo"}`}>
            {sync ? "Sincronizado" : "Sin sincronizar"}
          </span>
          <span className="badge badge-neutral mono">
            {ota ? `FW v${ota.version}` : "FW —"}
          </span>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => refreshBackendEstado(false)}
            title="Actualizar LEDs desde el orquestador (GET /api/zaguan/estado)"
          >
            LEDs
          </button>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => setTweaksOpen(true)}
            title="Apariencia y sondeo"
          >
            Tweaks
          </button>
        </div>
      </header>

      <main className="layout">
        <section className="col-main">
          <div className="panel">
            <div className="panel-head">
              <h2 className="panel-title">Acceso — vista en planta</h2>
              <div className="modo-actual">
                <span className="modo-actual-label">
                  Modo activo del sistema
                </span>
                <span
                  className={`modo-actual-value${
                    activeModeLabel === "Sin modo seleccionado"
                      ? " is-empty"
                      : ""
                  }`}
                  title={activeModeLabel}
                >
                  {activeModeLabel}
                </span>
                {pendingModeLabel ? (
                  <span className="modo-actual-pending">
                    En cola: {pendingModeLabel}
                  </span>
                ) : null}
              </div>
            </div>
            <ZaguanDiagram
              estados={estados}
              config={config}
              seleccionado={canalSel}
              pulsos={pulsos}
              haloOn={haloOn}
              winhoseParpadeo={winhoseParpadeo}
              onSelectCanal={(c) => setCanalSel(c === canalSel ? null : c)}
            />
          </div>

          <div className="canales-grid canales-grid-exterior">
            {[1, 2].map(renderCanalCard)}
          </div>

          <div className="canales-interior-block">
            <div className="canales-grid canales-grid-interior">
              {[3, 4].map(renderCanalCard)}
            </div>
            <ZaguanSimulationSection
              onSimulatePulse={handleSimulatePulse}
              onEmulateLlaveEchada={handleEmulateLlaveEchada}
            />
          </div>
        </section>

        <aside className="col-side">
          <div className="panel">
            <nav className="tabs" role="tablist">
              {[
                ["red", "Red"],
                ["canal", "Canales"],
                ["estado", "Estados"],
                ["flash", "Flash"],
                ["ota", "OTA"],
              ].map(([k, lbl]) => (
                <button
                  key={k}
                  type="button"
                  role="tab"
                  aria-selected={tab === k}
                  className={`tab${tab === k ? " is-active" : ""}`}
                  onClick={() => setTab(k)}
                >
                  {lbl}
                </button>
              ))}
            </nav>
            <div className="tab-body">
              {tab === "red" ? (
                <ConfigRedPanel
                  config={config}
                  ejecutar={enviarConfig}
                  busy={busy}
                />
              ) : null}
              {tab === "canal" ? (
                <ConfigCanalPanel
                  config={config}
                  ejecutar={enviarConfig}
                  busy={busy}
                  canal={canalCfg}
                  setCanal={setCanalCfg}
                />
              ) : null}
              {tab === "estado" ? (
                <ConfigEstadoPanel
                  config={config}
                  ejecutar={enviarConfig}
                  busy={busy}
                  haloOn={haloOn}
                />
              ) : null}
              {tab === "flash" ? (
                <ConfigFlashPanel
                  config={config}
                  ejecutar={enviarConfig}
                  busy={busy}
                />
              ) : null}
              {tab === "ota" ? (
                <OtaPanel ota={ota} onRefresh={refreshOta} busy={busy} />
              ) : null}
            </div>
          </div>
          <div className="panel panel-log">
            <EventLog eventos={eventos} onClear={() => setEventos([])} />
          </div>
        </aside>
      </main>

      <TweaksPanel open={tweaksOpen} onClose={() => setTweaksOpen(false)}>
        <TweakSection label="Apariencia" />
        <TweakRadio
          label="Densidad"
          value={t.densidad}
          options={["compacta", "normal"]}
          onChange={(v) => setTweak("densidad", v)}
        />
        <TweakToggle
          label="Halo en LEDs"
          value={t.halo}
          onChange={(v) => setTweak("halo", v)}
        />
        <TweakSection label="Sondeo" />
        <TweakSlider
          label="Intervalo de ping"
          value={t.intervaloPing}
          min={3}
          max={60}
          step={1}
          unit="s"
          onChange={(v) => setTweak("intervaloPing", v)}
        />
      </TweaksPanel>
    </div>
  );
}
