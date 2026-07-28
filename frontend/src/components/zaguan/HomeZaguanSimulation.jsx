import { ZaguanSimulationSection } from "./ZaguanSimulationSection";
import "./zaguanEsp32.css";
import "./homeZaguanSim.css";

/**
 * Simulación del orquestador en la página principal (mismos botones azules que pulsadores).
 */
export function HomeZaguanSimulation({ onSimulatePulse }) {
  if (!onSimulatePulse) return null;

  return (
    <div
      className="zaguan-esp32-app home-zaguan-sim"
      data-theme="claro"
      data-density="compacta"
    >
      <ZaguanSimulationSection onSimulatePulse={onSimulatePulse} />
    </div>
  );
}
