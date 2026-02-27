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
        <p className="card__meta">Download results in your preferred format.</p>
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
          className="button button--secondary"
          type="button"
          onClick={() => onDownloadPdf?.()}
          disabled={disabled}
        >
          Download PDF
        </button>
      </div>
    </section>
  );
}

export default ReportExporter;
