/**
 * Visual bar (0–100 YES) with current YES price marker (fixed) and exit-threshold
 * marker (synced from slider). Left of current YES = green, right = red.
 * Region between the two markers is highlighted (striped); if 6+ apart, show difference.
 */
interface ExitYesBarProps {
  currentYesPrice: number;
  exitThreshold: number;
}

export function ExitYesBar({ currentYesPrice, exitThreshold }: ExitYesBarProps) {
  const exitYesPct = Math.round(exitThreshold * 100);
  const currentPct = Math.round(currentYesPrice);
  const lo = Math.min(currentPct, exitYesPct);
  const hi = Math.max(currentPct, exitYesPct);
  const gapWidth = hi - lo;
  const showDifference = gapWidth >= 6;

  return (
    <div className="exit-yes-bar">
      <div className="exit-yes-bar-label">
        <span className="exit-yes-bar-legend">Current YES</span>
      </div>
      <div className="exit-yes-bar-track-wrap">
        <div className="exit-yes-bar-track" aria-hidden>
          <div
            className="exit-yes-bar-segment exit-yes-bar-green"
            style={{ width: `${currentPct}%` }}
          />
          <div
            className="exit-yes-bar-segment exit-yes-bar-red"
            style={{ left: `${currentPct}%`, width: `${100 - currentPct}%` }}
          />
        </div>
        {/* Highlighted gap between current and exit */}
        {gapWidth > 0 && (
          <div
            className="exit-yes-bar-gap"
            style={{
              left: `${lo}%`,
              width: `${gapWidth}%`,
            }}
          >
            {showDifference && (
              <span className="exit-yes-bar-gap-label">{gapWidth}</span>
            )}
          </div>
        )}
        {/* Current YES marker — label above, no % */}
        <div
          className="exit-yes-bar-marker exit-yes-bar-marker-current"
          style={{ left: `${currentPct}%` }}
          title={`Current YES ${currentPct}%`}
        >
          <span className="exit-yes-bar-marker-label">{currentPct}</span>
        </div>
        {/* Exit threshold marker */}
        <div
          className="exit-yes-bar-marker exit-yes-bar-marker-exit"
          style={{ left: `${exitYesPct}%` }}
          title={`Exit @ ${exitYesPct}% YES`}
        >
          <span className="exit-yes-bar-marker-label exit-yes-bar-marker-label-exit">{exitYesPct}</span>
        </div>
      </div>
      <div className="exit-yes-bar-axis">
        <span>0%</span>
        <span>100%</span>
      </div>
    </div>
  );
}
