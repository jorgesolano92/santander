import { BranchCriticalAlertBanner } from './BranchCriticalAlertBanner';
import { useCoceLive } from '../context/CoceLiveContext';
import {
  deriveAlertsFromBranchState,
  hasActiveBranchAlert,
} from '../utils/branchAlerts';

export function CoceGlobalAlertsBar() {
  const { connected, getAllLiveBranches } = useCoceLive();
  if (!connected) return null;

  const activeBranches = getAllLiveBranches().filter((branch) =>
    hasActiveBranchAlert(
      deriveAlertsFromBranchState(
        branch.currentMode,
        branch.activeToggleRules,
        branch.alerts,
      ),
    ),
  );
  if (!activeBranches.length) return null;

  return (
    <div className="coce-global-alerts">
      {activeBranches.map((branch) => (
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
  );
}
