import {
  ZAGUAN_PULSADOR_CANALES,
  ZAGUAN_VIDEOPORTERO_CANALES,
  ZAGUAN_LLAVE_ECHADA,
} from "./zaguanConstants";

export function ZaguanSimulationSection({
  onSimulatePulse,
  onEmulateLlaveEchada,
}) {
  if (!onSimulatePulse && !onEmulateLlaveEchada) return null;

  return (
    <div className="panel sim-section">
      <div className="panel-head">
        <h2 className="panel-title">Simulación backend (orquestador)</h2>
      </div>

      {onSimulatePulse ? (
        <>
          <div className="sim-block">
            <h3 className="sim-block-title">Pulsadores → backend</h3>
            <p className="muted sim-block-desc">
              Simula la pulsación del botón físico (
              <code className="mono">POST /api/zaguan/pulsacion/pN</code>). C3
              y C4 son los únicos pulsadores; cada ESP debe estar configurado
              con su canal lógico (p3 / p4).
            </p>
            <div className="sim-grid sim-grid-pulse">
              {ZAGUAN_PULSADOR_CANALES.map(
                ({ canal, puerta, dispositivo, ubicacion, led, ip, inModbus }) => (
                  <article key={canal} className="sim-card">
                    <button
                      type="button"
                      className="btn btn-primary btn-sm sim-card-action"
                      onClick={() => onSimulatePulse(canal)}
                    >
                      Simular pulsación p{canal}
                    </button>
                    <div className="sim-card-title">
                      <span className="canal-chip">{led}</span>
                      {dispositivo}
                    </div>
                    <div className="sim-card-subtitle">{puerta}</div>
                    <div className="sim-card-meta mono">
                      {ubicacion} · {ip} · {inModbus}
                    </div>
                  </article>
                ),
              )}
            </div>
          </div>

          <div className="sim-block">
            <h3 className="sim-block-title">Videoporteros (referencia)</h3>
            <p className="muted sim-block-desc">
              LEDs en canal p1 / p2. La apertura por interfono usa otras reglas;
              aquí solo se indica el mapeo IP ↔ canal del ESP.
            </p>
            <div className="sim-grid sim-grid-pulse">
              {ZAGUAN_VIDEOPORTERO_CANALES.map(
                ({ canal, puerta, dispositivo, ubicacion, led, ip }) => (
                  <article key={canal} className="sim-card sim-card-ref">
                    <div className="sim-card-title">
                      <span className="canal-chip">{led}</span>
                      {dispositivo}
                    </div>
                    <div className="sim-card-subtitle">{puerta}</div>
                    <div className="sim-card-meta mono">
                      Canal p{canal} · {ubicacion} · {ip}
                    </div>
                  </article>
                ),
              )}
            </div>
          </div>
        </>
      ) : null}

      {onEmulateLlaveEchada ? (
        <div className="sim-block">
          <h3 className="sim-block-title">Emular llave echada (WinHose)</h3>
          <p className="muted sim-block-desc">
            Fuerza el inductivo Modbus (cerrado=ON, abierto=OFF).{" "}
            <strong>Maniobra completa</strong> simula el flanco ON→OFF y activa
            la ventana 15 s en autoservicio/cerrado. Modos:{" "}
            <code className="mono">IN_02_03</code> (P1),{" "}
            <code className="mono">IN_03_03</code> (P2).
          </p>
          <div className="sim-grid sim-grid-llave">
            {ZAGUAN_LLAVE_ECHADA.map((llave) => (
              <article key={llave.id} className="sim-card">
                <div className="sim-card-title">{llave.label}</div>
                <div className="sim-card-subtitle">{llave.puerta}</div>
                <div className="sim-card-meta mono">
                  {llave.code} · Placa {llave.placa} IN{llave.canalIn}
                </div>
                <div className="sim-btn-grid">
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => onEmulateLlaveEchada(llave.id, "cerrar")}
                  >
                    Cerrar (ON)
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => onEmulateLlaveEchada(llave.id, "abrir")}
                  >
                    Abrir (OFF)
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm sim-btn-wide"
                    onClick={() => onEmulateLlaveEchada(llave.id, "maniobra")}
                  >
                    Maniobra completa (ON→OFF)
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-ghost sim-btn-wide"
                    onClick={() => onEmulateLlaveEchada(llave.id, "real")}
                  >
                    Volver a lectura REAL
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
