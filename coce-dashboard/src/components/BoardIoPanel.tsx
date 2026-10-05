import { useState } from 'react';
import {
  panelConnectBoard,
  panelDisconnectBoard,
  panelSetInputOverride,
  panelSetOutput,
} from '../api/coceClient';
import type { PanelBoardState, PanelModuleConfig } from '../types';

function asBoolArray(value: unknown, minLen = 12): boolean[] {
  if (Array.isArray(value)) {
    const arr = value.map((v) => Boolean(v));
    while (arr.length < minLen) arr.push(false);
    return arr.slice(0, Math.max(minLen, arr.length));
  }
  return Array.from({ length: minLen }, () => false);
}

function asOverrideArray(value: unknown, len: number): Array<boolean | null> {
  if (!Array.isArray(value)) return Array(len).fill(null);
  return Array.from({ length: len }, (_, i) => {
    const v = value[i];
    if (v === null || v === undefined) return null;
    return Boolean(v);
  });
}

function channelLabel(
  kind: 'input' | 'output',
  index: number,
  mod?: PanelModuleConfig,
): string {
  const list = kind === 'input' ? mod?.inputs : mod?.outputs;
  const name = (list?.[index]?.channel_name || '').trim();
  const base = kind === 'input' ? `IN${index + 1}` : `OUT${index + 1}`;
  return name ? `${base} — ${name}` : base;
}

type InputVisual = {
  effective: boolean;
  forcedOn: boolean;
  forcedOff: boolean;
};

function inputVisual(
  board: PanelBoardState & { inputs_raw?: boolean[]; input_overrides?: Array<boolean | null> },
  index: number,
): InputVisual {
  const overrides = asOverrideArray(board.input_overrides, 12);
  const forced = overrides[index] ?? null;
  const rawList = asBoolArray(board.inputs_raw ?? board.inputs, 12);
  const effList = asBoolArray(board.inputs, 12);
  const raw = rawList[index] ?? false;
  const effective = forced === null ? (effList[index] ?? raw) : Boolean(forced);
  return {
    effective,
    forcedOn: forced === true,
    forcedOff: forced === false,
  };
}

type Props = {
  branchId: string;
  boardId: string;
  board: PanelBoardState & {
    inputs_raw?: boolean[];
    input_overrides?: Array<boolean | null>;
  };
  moduleConfig?: PanelModuleConfig;
  canControl?: boolean;
  onRefresh?: () => void | Promise<void>;
};

export function BoardIoPanel({
  branchId,
  boardId,
  board,
  moduleConfig,
  canControl = false,
  onRefresh,
}: Props) {
  const [busy, setBusy] = useState(false);
  const bid = Number(boardId);

  async function runOp(fn: () => Promise<void>) {
    if (!canControl) return;
    setBusy(true);
    try {
      await fn();
      await onRefresh?.();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const outputs = asBoolArray(board.outputs, 12);
  const effIn = asBoolArray(board.inputs, 12);
  const rawIn = asBoolArray(board.inputs_raw, 12);
  const inputsLen = Math.max(12, effIn.length, rawIn.length);
  const outActive = outputs.filter(Boolean).length;
  const inActive = Array.from({ length: inputsLen }, (_, i) =>
    inputVisual(board, i).effective,
  ).filter(Boolean).length;

  const title = board.config?.name || moduleConfig?.name || `Placa ${boardId}`;

  return (
    <article className="board-io-card">
      <header className="board-io-card-header">
        <div>
          <h3>
            Placa #{boardId} — {title}
          </h3>
          <p className="panel-subtitle">
            {board.config?.host}:{board.config?.port} · esclavo {board.config?.slave_id ?? '—'}
          </p>
        </div>
        <div className="board-io-header-actions">
          <span className={board.connected ? 'badge badge-ok' : 'badge badge-off'}>
            {board.connected ? 'Modbus conectado' : 'Modbus offline'}
          </span>
          {canControl && (
            <>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={busy}
                onClick={() => runOp(() => panelConnectBoard(branchId, bid))}
              >
                Conectar Modbus
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={busy}
                onClick={() => runOp(() => panelDisconnectBoard(branchId, bid))}
              >
                Desconectar
              </button>
            </>
          )}
        </div>
      </header>

      <div className="board-io-stats">
        <span>
          Salidas activas: <strong>{outActive}</strong>/{outputs.length}
        </span>
        <span>
          Entradas activas: <strong>{inActive}</strong>/{inputsLen}
        </span>
      </div>

      <section className="board-io-section">
        <h4>Salidas (OUT)</h4>
        <div className="board-io-grid">
          {outputs.map((on, i) => (
            <div
              key={`out-${i}`}
              role={canControl ? 'button' : undefined}
              tabIndex={canControl ? 0 : undefined}
              className={`board-io-cell board-io-cell--out ${on ? 'board-io-cell--on' : ''} ${canControl ? 'board-io-cell--clickable' : ''}`}
              title={channelLabel('output', i, moduleConfig)}
              onClick={() =>
                canControl && runOp(() => panelSetOutput(branchId, bid, i + 1, !on))
              }
              onKeyDown={(e) => {
                if (canControl && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault();
                  void runOp(() => panelSetOutput(branchId, bid, i + 1, !on));
                }
              }}
            >
              <span className="board-io-cell-code">OUT{i + 1}</span>
              {moduleConfig?.outputs?.[i]?.channel_name?.trim() && (
                <span className="board-io-cell-name">
                  {moduleConfig.outputs[i].channel_name}
                </span>
              )}
              <span className="board-io-cell-state">{on ? 'ON' : 'OFF'}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="board-io-section">
        <h4>Entradas (IN)</h4>
        <p className="board-io-legend">
          <span className="board-io-legend-item board-io-legend--active">Activa</span>
          <span className="board-io-legend-item board-io-legend--forced-on">Forzada ON</span>
          <span className="board-io-legend-item board-io-legend--forced-off">Forzada OFF</span>
        </p>
        <div className="board-io-grid">
          {Array.from({ length: inputsLen }, (_, i) => {
            const st = inputVisual(board, i);
            const cls = [
              'board-io-cell',
              'board-io-cell--in',
              st.effective ? 'board-io-cell--on' : '',
              st.forcedOn ? 'board-io-cell--forced-on' : '',
              st.forcedOff ? 'board-io-cell--forced-off' : '',
            ]
              .filter(Boolean)
              .join(' ');
            const cycleOverride = async () => {
              if (!canControl) return;
              const ov = asOverrideArray(board.input_overrides, inputsLen)[i];
              const next = ov === null ? true : ov === true ? false : null;
              await runOp(() => panelSetInputOverride(branchId, bid, i + 1, next));
            };
            return (
              <div
                key={`in-${i}`}
                role={canControl ? 'button' : undefined}
                tabIndex={canControl ? 0 : undefined}
                className={`${cls} ${canControl ? 'board-io-cell--clickable' : ''}`}
                title={
                  canControl
                    ? `${channelLabel('input', i, moduleConfig)} — clic: REAL → FORZ ON → FORZ OFF`
                    : channelLabel('input', i, moduleConfig)
                }
                onClick={() => void cycleOverride()}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    void cycleOverride();
                  }
                }}
              >
                <span className="board-io-cell-code">IN{i + 1}</span>
                {moduleConfig?.inputs?.[i]?.channel_name?.trim() && (
                  <span className="board-io-cell-name">
                    {moduleConfig.inputs[i].channel_name}
                  </span>
                )}
                <span className="board-io-cell-state">
                  {st.forcedOn ? 'FORZ ON' : st.forcedOff ? 'FORZ OFF' : st.effective ? 'ON' : 'OFF'}
                </span>
              </div>
            );
          })}
        </div>
      </section>
    </article>
  );
}
