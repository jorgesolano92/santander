import { useEffect, useRef, useState } from 'react';

import { BranchCriticalAlertBanner } from './BranchCriticalAlertBanner';
import { useCoceLive } from '../context/CoceLiveContext';
import {
  alertTitle,
  deriveAlertsFromBranchState,
  listActiveAlerts,
} from '../utils/branchAlerts';

function playAlertTone(): void {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const notes = [880, 660, 880, 660];
    notes.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      const start = ctx.currentTime + i * 0.28;
      osc.type = 'square';
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.25, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.25);
      osc.connect(gain).connect(ctx.destination);
      osc.start(start);
      osc.stop(start + 0.26);
    });
    window.setTimeout(() => void ctx.close(), notes.length * 300 + 200);
  } catch {
    // el navegador puede bloquear el audio hasta que el usuario interactúe
  }
}

function notificationsSupported(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window && window.isSecureContext;
}

export function CoceGlobalAlertsBar() {
  const { connected, getAllLiveBranches } = useCoceLive();
  const seenRef = useRef<Set<string>>(new Set());
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>(
    notificationsSupported() ? Notification.permission : 'unsupported',
  );

  const branches = connected ? getAllLiveBranches() : [];
  const active = branches
    .map((branch) => ({
      branch,
      alerts: listActiveAlerts(
        deriveAlertsFromBranchState(branch.currentMode, branch.activeToggleRules, branch.alerts),
      ),
    }))
    .filter((row) => row.alerts.length > 0);

  const activeKeys = active
    .flatMap(({ branch, alerts }) =>
      alerts.map((a) => `${branch.installationId}:${String(a.alert_type)}`),
    )
    .sort()
    .join('|');

  useEffect(() => {
    const current = new Set(activeKeys ? activeKeys.split('|') : []);
    const fresh = [...current].filter((k) => !seenRef.current.has(k));
    seenRef.current = current;
    if (!fresh.length) return;
    playAlertTone();
    if (permission !== 'granted') return;
    for (const key of fresh) {
      const [branchId, alertType] = key.split(':');
      const row = active.find((r) => r.branch.installationId === branchId);
      const alert = row?.alerts.find((a) => String(a.alert_type) === alertType);
      if (!row || !alert) continue;
      try {
        new Notification(`${alertTitle(alert)} · ${row.branch.nombre || branchId}`, {
          body: alert.message || '',
          tag: key,
          requireInteraction: true,
        });
      } catch {
        // ignore
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKeys, permission]);

  if (!connected) return null;

  return (
    <>
      {permission === 'default' ? (
        <button
          type="button"
          className="coce-alert-notify-btn"
          onClick={() => {
            void Notification.requestPermission().then(setPermission);
          }}
        >
          Activar avisos del navegador para alertas de sucursal
        </button>
      ) : null}
      {active.length ? (
        <div className="coce-global-alerts">
          {active.map(({ branch }) => (
            <BranchCriticalAlertBanner
              key={branch.installationId}
              branchId={branch.installationId}
              branchName={branch.nombre || branch.installationId}
              currentMode={branch.currentMode}
              activeToggleRules={branch.activeToggleRules}
              storedAlerts={branch.alerts}
              compact
            />
          ))}
        </div>
      ) : null}
    </>
  );
}
