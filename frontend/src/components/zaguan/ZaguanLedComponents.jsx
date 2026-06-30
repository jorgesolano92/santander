import { useRef, useEffect } from "react";
import { CANAL_INFO, ESTADO_META, withWinhoseParpadeo } from "./zaguanConstants";

function brilloLed(animacion, velocidad, t, idx, n) {
  switch (animacion) {
    case "respiracion": {
      const vel = velocidad || 3000;
      return 0.15 + 0.85 * (0.5 + 0.5 * Math.sin((2 * Math.PI * t) / vel));
    }
    case "parpadeo": {
      const vel = velocidad || 1000;
      return (t % vel) / vel < 0.8 ? 1 : 0;
    }
    case "barrido": {
      const vel = velocidad || 30;
      const span = n + 8;
      const head = Math.floor(t / vel) % span;
      const d = head - idx;
      if (d < 0 || d > 8) return 0;
      return 1 - d / 8.5;
    }
    default:
      return 1;
  }
}

export function LedStrip({
  leds,
  brillo,
  estadoCfg,
  vertical = false,
  ledPx = 9,
  gapPx = 3,
  glow = true,
  haloOn = true,
}) {
  const ref = useRef(null);
  const cfgRef = useRef();
  cfgRef.current = { leds, brillo, estadoCfg, vertical, ledPx, gapPx, glow, haloOn };

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas.getContext("2d");
    let raf;
    const dpr = window.devicePixelRatio || 1;

    const draw = () => {
      const { leds, brillo, estadoCfg, vertical, ledPx, gapPx, glow, haloOn } =
        cfgRef.current;
      const n = Math.max(1, leds || 1);
      const span = n * ledPx + (n - 1) * gapPx + 8;
      const thick = ledPx + 10;
      const w = vertical ? thick : span;
      const h = vertical ? span : thick;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        canvas.style.width = `${w}px`;
        canvas.style.height = `${h}px`;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const showHalo = glow && haloOn;
      const [r, g, b] = (estadoCfg && estadoCfg.color) || [0, 0, 0];
      const anim = (estadoCfg && estadoCfg.animacion) || "fijo";
      const vel = (estadoCfg && estadoCfg.velocidad) || 0;
      const master = Math.min(1, (brillo == null ? 255 : brillo) / 255);
      const t = performance.now();

      for (let i = 0; i < n; i++) {
        const f = brilloLed(anim, vel, t, i, n) * master;
        const cx = vertical ? thick / 2 : 4 + i * (ledPx + gapPx) + ledPx / 2;
        const cy = vertical ? 4 + i * (ledPx + gapPx) + ledPx / 2 : thick / 2;
        ctx.shadowBlur = 0;
        ctx.fillStyle = "rgba(127,127,127,0.16)";
        ctx.beginPath();
        ctx.arc(cx, cy, ledPx / 2, 0, Math.PI * 2);
        ctx.fill();
        if (f > 0.02 && r + g + b > 0) {
          ctx.fillStyle = `rgba(${r},${g},${b},${(0.25 + 0.75 * f).toFixed(3)})`;
          if (showHalo) {
            ctx.shadowColor = `rgba(${r},${g},${b},${(0.85 * f).toFixed(3)})`;
            ctx.shadowBlur = ledPx * 1.1 * f;
          }
          ctx.beginPath();
          ctx.arc(cx, cy, (ledPx / 2) * (0.62 + 0.38 * f), 0, Math.PI * 2);
          ctx.fill();
          ctx.shadowBlur = 0;
        }
      }
    };

    draw();
    const loop = () => {
      draw();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  return <canvas ref={ref} style={{ display: "block" }} />;
}

function MiniStrip(props) {
  const shown = Math.min(props.leds, props.max || 20);
  return <LedStrip {...props} leds={shown} ledPx={props.ledPx || 7} gapPx={2} />;
}

export function EstadoBadge({ estado }) {
  const meta = ESTADO_META[estado] || { label: estado };
  return <span className={`badge badge-${estado}`}>{meta.label}</span>;
}

export function ZaguanDiagram({
  estados,
  resolveCanalConfig,
  onSelectCanal,
  seleccionado,
  pulsos,
  haloOn,
  winhoseParpadeo = {},
}) {
  const pulso = pulsos || {};
  const cfgCanal = (n) => resolveCanalConfig(n) || null;
  const estadoCfg = (n) => {
    const c = cfgCanal(n);
    const est = estados[n] || "apagado";
    if (!c) {
      return withWinhoseParpadeo(
        n,
        est,
        { color: [0, 0, 0], animacion: "fijo", velocidad: 0 },
        winhoseParpadeo,
      );
    }
    const base =
      c.estados.find((e) => e.estado === est) || {
        color: [0, 0, 0],
        animacion: "fijo",
        velocidad: 0,
      };
    return withWinhoseParpadeo(n, est, base, winhoseParpadeo);
  };
  const brillo = (n) => {
    const c = cfgCanal(n);
    return c ? c.brillo : 150;
  };
  const leds = (n) => {
    const c = cfgCanal(n);
    return c ? c.leds : 10;
  };

  const StripBlock = ({ canal, vertical, max }) => (
    <button
      type="button"
      className={`diagram-strip${seleccionado === canal ? " is-selected" : ""}`}
      onClick={() => onSelectCanal && onSelectCanal(canal)}
      title={CANAL_INFO[canal].nombre}
    >
      <span className="diagram-strip-label">
        <span className="canal-chip">{CANAL_INFO[canal].corto}</span>
        <EstadoBadge estado={estados[canal] || "apagado"} />
      </span>
      <MiniStrip
        leds={leds(canal)}
        max={max}
        brillo={brillo(canal)}
        estadoCfg={estadoCfg(canal)}
        vertical={vertical}
        haloOn={haloOn}
      />
    </button>
  );

  return (
    <div className="zaguan-diagram">
      <div className="zona zona-calle">
        <span className="zona-label">Calle</span>
      </div>

      <div className="puerta">
        <span className="puerta-label">Puerta P1</span>
        <div className="puerta-hoja" />
        <div className="puerta-strips">
          <StripBlock canal={1} vertical max={14} />
          <span
            className={`pulsador-icono${pulso[1] ? " is-pulsed" : ""}`}
            title={CANAL_INFO[1].nombre}
          >
            ⏻
          </span>
        </div>
      </div>

      <div className="zona zona-zaguan">
        <span className="zona-label">Zaguán</span>
        <div className="pulsadores-interiores">
          <div className="pulsador-grupo">
            <StripBlock canal={3} vertical max={14} />
            <span
              className={`pulsador-icono${pulso[3] ? " is-pulsed" : ""}`}
              title={CANAL_INFO[3].nombre}
            >
              ⏻
            </span>
          </div>
          <div className="pulsador-grupo">
            <StripBlock canal={4} vertical max={14} />
            <span
              className={`pulsador-icono${pulso[4] ? " is-pulsed" : ""}`}
              title={CANAL_INFO[4].nombre}
            >
              ⏻
            </span>
          </div>
        </div>
      </div>

      <div className="puerta">
        <span className="puerta-label">Puerta P2</span>
        <div className="puerta-hoja" />
        <div className="puerta-strips">
          <StripBlock canal={2} vertical max={14} />
          <span
            className={`pulsador-icono${pulso[2] ? " is-pulsed" : ""}`}
            title={CANAL_INFO[2].nombre}
          >
            ⏻
          </span>
        </div>
      </div>

      <div className="zona zona-oficina">
        <span className="zona-label">Oficina</span>
      </div>
    </div>
  );
}
