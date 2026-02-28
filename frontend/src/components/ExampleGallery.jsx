import { useState } from "react";

function ExampleGallery({
  examples = [],
  isLoading = false,
  onAnalyze,
  isSubmitting = false,
  jobId = null,
  status = null,
  error = null,
}) {
  const [localError, setLocalError] = useState(null);

  const handleAnalyze = async (exampleId) => {
    if (!exampleId) {
      setLocalError("Example selection is invalid.");
      return;
    }

    setLocalError(null);
    try {
      await onAnalyze?.(exampleId);
    } catch {
      // Parent component handles surfaced errors.
    }
  };

  return (
    <section className="card examples" aria-labelledby="example-gallery-title">
      <header className="card__header">
        <h2 id="example-gallery-title" className="card__title">Example track gallery</h2>
        {jobId ? (
          <p className="card__meta">Active job: {jobId} · {status?.status ?? "queued"}</p>
        ) : (
          <p className="card__meta">Run analysis with a server-hosted demo track.</p>
        )}
      </header>

      {isLoading ? (
        <p className="examples__helper">Loading examples…</p>
      ) : examples.length === 0 ? (
        <p className="examples__helper">No examples are currently available.</p>
      ) : (
        <ul className="examples__list">
          {examples.map((example) => (
            <li key={example.id} className="examples__item">
              <div className="examples__info">
                <p className="examples__name">{example.display_name}</p>
                <p className="examples__meta">{example.filename}</p>
              </div>
              <button
                className="button button--secondary"
                type="button"
                onClick={() => handleAnalyze(example.id)}
                disabled={isSubmitting}
              >
                {isSubmitting ? "Submitting…" : "Analyze example"}
              </button>
            </li>
          ))}
        </ul>
      )}

      {(localError || error) ? (
        <p className="uploader__error" role="alert">{localError ?? error}</p>
      ) : null}
    </section>
  );
}

export default ExampleGallery;