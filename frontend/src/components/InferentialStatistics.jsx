/**
 * InferentialStatistics - Displays inferential statistics table
 * Shows consistency metrics with confidence intervals and p-values
 */

import GlossaryTerm from "./GlossaryTerm";
import {
  formatValue,
  formatPitchWithNote,
  formatConfidenceIntervalWithNotes,
  formatPValue,
  prettifyMetricName,
} from "./AnalysisFormatters";

function InferentialStatistics({ inferentialStatistics, inferentialMetrics }) {
  if (!inferentialMetrics.length) {
    return null;
  }

  return (
    <section className="results__section results__inferential" aria-label="Inferential statistics">
      <div className="results__section-header">
        <h3 className="results__section-title">How consistent each metric is (<GlossaryTerm term="inferential_statistics">inferential statistics</GlossaryTerm>)</h3>
        <p className="results__inferential-meta">
          Analysis preset: {inferentialStatistics?.preset ?? "unknown"} · Confidence interval level: {formatValue(inferentialStatistics?.confidence_level)}
        </p>
      </div>
      <p className="results__section-copy">
        In the table below, "Estimate" is the best single value, "<GlossaryTerm term="confidence_interval">Confidence interval</GlossaryTerm>" is a likely range,
        "<GlossaryTerm term="p_value">p-value</GlossaryTerm>" helps indicate whether a difference is meaningful, and "Samples (N)" is how many data points were used.
      </p>
      <div className="results__inferential-table-wrap">
        <table className="results__inferential-table">
          <thead>
            <tr>
              <th scope="col">Metric</th>
              <th scope="col">Estimate</th>
              <th scope="col">Confidence interval (95%)</th>
              <th scope="col">p-value (significance)</th>
              <th scope="col">Samples (N)</th>
            </tr>
          </thead>
          <tbody>
            {inferentialMetrics.map(([metricName, metricPayload]) => {
              const ci = metricPayload?.confidence_interval ?? null;
              return (
                <tr key={metricName}>
                  <th scope="row">{prettifyMetricName(metricName)}</th>
                  <td>{formatPitchWithNote(metricPayload?.estimate, metricPayload?.estimate_note)}</td>
                  <td>{formatConfidenceIntervalWithNotes(ci)}</td>
                  <td>{formatPValue(metricPayload?.p_value)}</td>
                  <td>{formatValue(metricPayload?.n_samples)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default InferentialStatistics;
