import { Link } from 'react-router-dom';
import {
  alertTitle,
  deriveAlertsFromBranchState,
  hasActiveBranchAlert,
  parseBranchAlerts,
  type BranchAlertsMap,
} from '../utils/branchAlerts';

type Props = {
  branchId: string;
  branchName: string;
  currentMode?: string | null;
  activeToggleRules?: string[] | null;
  storedAlerts?: BranchAlertsMap;
  compact?: boolean;
};

export function BranchCriticalAlertBanner({
  branchId,
  branchName,
  currentMode,
  activeToggleRules,
  storedAlerts,
  compact = false,
}: Props) {
  const alerts = deriveAlertsFromBranchState(
    currentMode,
    activeToggleRules,
    storedAlerts,
  );
  if (!hasActiveBranchAlert(alerts)) return null;

  const items = Object.values(alerts).filter(
    (a): a is NonNullable<typeof a> => Boolean(a?.active),
  );

  return (
    <section className="coce-critical-alerts" role="alert" aria-live="assertive">
      {items.map((alert) => {
        const kind = String(alert.alert_type || 'unknown').startsWith('door_held')
          ? 'door_held'
          : String(alert.alert_type || 'unknown');
        return (
        <div
          key={String(alert.alert_type)}
          className={`coce-critical-alert coce-critical-alert--${kind}`}
        >
          <div className="coce-critical-alert-inner">
            <strong>{alertTitle(alert)}</strong>
            <span className="coce-critical-alert-branch">{branchName}</span>
            <p>{alert.message}</p>
            {!compact ? (
              <Link to={`/control/${branchId}`} className="btn btn-sm coce-critical-alert-cta">
                Abrir sucursal y contactar oficina
              </Link>
            ) : null}
          </div>
        </div>
        );
      })}
    </section>
  );
}

export function parseAlertsFromLivePartial(partial: unknown): BranchAlertsMap {
  if (!partial || typeof partial !== 'object') return {};
  const p = partial as Record<string, unknown>;
  return parseBranchAlerts(p.alerts);
}

export function activeToggleRulesFromPartial(partial: unknown): string[] {
  if (!partial || typeof partial !== 'object') return [];
  const raw = (partial as Record<string, unknown>).active_toggle_rules;
  return Array.isArray(raw) ? raw.map(String) : [];
}
