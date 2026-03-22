function ReportExporter({
  disabled = false,
  onDownloadCsv,
  onDownloadJson,
  onDownloadPdf,
}) {
  return (
    <section className="card exporter" aria-label="Download reports">
      <header className="card__header">
        <h3 className="card__title">Export reports</h3>
        <p className="card__meta">
          Download results in your preferred format. The PDF report includes pitch curves, 
          piano roll, and range visualizations not shown on this page.
        </p>
      </header>
      <div className="exporter__actions">
        <button
          className="button"
          type="button"
          onClick={() => onDownloadCsv?.()}
          disabled={disabled}
        >
          Download CSV
        </button>
        <button
          className="button"
          type="button"
          onClick={() => onDownloadJson?.()}
          disabled={disabled}
        >
          Download JSON
        </button>
        <button
          className="button button--primary"
          type="button"
          onClick={() => onDownloadPdf?.()}
          disabled={disabled}
          title="Recommended: includes charts and visualizations"
        >
          ⭐ Download PDF
        </button>
      </div>
    </section>
  );
}

export default ReportExporter;
