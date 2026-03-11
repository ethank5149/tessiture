/**
 * CalibrationSummary - Displays reference calibration summary
 * Shows metrics from reference dataset calibration
 */

import { formatValue, formatCountValue, formatMinMaxRange, isPlainObject } from "./AnalysisFormatters";

function CalibrationSummary({ calibrationSummary, calibrationTabId, titleId }) {
  if (!calibrationSummary || !isPlainObject(calibrationSummary)) {
    return null;
  }

  const hasCalibrationSummary = Object.keys(calibrationSummary).length > 0;
  if (!hasCalibrationSummary) {
    return null;
  }

  return (
    <section
      id={calibrationTabId}
      className="results__section results__section--calibration"
      role="tabpanel"
      aria-labelledby={titleId}
      aria-label="Reference calibration summary"
    >
      <div className="results__section-header">
        <h3 className="results__section-title">Reference calibration summary</h3>
        <p className="results__section-meta">
          These metrics come from reference dataset calibration (ground-truth generated data) and are not derived from uploaded or example track runtime behavior.
        </p>
      </div>
      <dl className="summary-list">
        <div className="summary-list__item">
          <dt>Reference samples (N)</dt>
          <dd>{formatCountValue(calibrationSummary?.reference_sample_count)}</dd>
        </div>
        <div className="summary-list__item">
          <dt>Reference frequency range (Hz)</dt>
          <dd>
            {formatMinMaxRange(
              calibrationSummary?.reference_frequency_min_hz,
              calibrationSummary?.reference_frequency_max_hz
            )}
          </dd>
        </div>
        <div className="summary-list__item">
          <dt>Frequency bins (total)</dt>
          <dd>{formatCountValue(calibrationSummary?.frequency_bin_count)}</dd>
        </div>
        <div className="summary-list__item">
          <dt>Frequency bins (populated)</dt>
          <dd>{formatCountValue(calibrationSummary?.populated_frequency_bin_count)}</dd>
        </div>
        <div className="summary-list__item">
          <dt>Mean pitch bias (cents)</dt>
          <dd>{formatValue(calibrationSummary?.mean_pitch_bias_cents)}</dd>
        </div>
        <div className="summary-list__item">
          <dt>Max absolute pitch bias (cents)</dt>
          <dd>{formatValue(calibrationSummary?.max_abs_pitch_bias_cents)}</dd>
        </div>
        <div className="summary-list__item">
          <dt>Mean pitch variance (cents²)</dt>
          <dd>{formatValue(calibrationSummary?.mean_pitch_variance_cents2)}</dd>
        </div>
        <div className="summary-list__item">
          <dt>Pitch error mean (cents)</dt>
          <dd>{formatValue(calibrationSummary?.pitch_error_mean_cents)}</dd>
        </div>
        <div className="summary-list__item">
          <dt>Pitch error standard deviation (cents)</dt>
          <dd>{formatValue(calibrationSummary?.pitch_error_std_cents)}</dd>
        </div>
        <div className="summary-list__item">
          <dt>Mean frame uncertainty (MIDI)</dt>
          <dd>{formatValue(calibrationSummary?.mean_frame_uncertainty_midi)}</dd>
        </div>
        <div className="summary-list__item">
          <dt>Voiced frame count</dt>
          <dd>{formatCountValue(calibrationSummary?.voiced_frame_count)}</dd>
        </div>
      </dl>
    </section>
  );
}

export default CalibrationSummary;
