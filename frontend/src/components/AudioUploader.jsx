import { useId, useState } from "react";

function AudioUploader({ onSubmit, isSubmitting = false, jobId = null, status = null, error = null }) {
  const inputId = useId();
  const helperId = useId();
  const statusId = useId();
  const [file, setFile] = useState(null);
  const [localError, setLocalError] = useState(null);

  const handleClick = (event) => {
    event.currentTarget.value = "";
  };

  const handleChange = (event) => {
    const nextFile = event.target.files?.[0] ?? null;
    setFile(nextFile);
    setLocalError(null);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!file) {
      setLocalError("Select an audio file to analyze.");
      return;
    }
    try {
      await onSubmit?.(file);
    } catch {
      // Errors are surfaced by parent state.
    }
  };

  const isBusy = Boolean(isSubmitting);

  return (
    <section className="card uploader" aria-labelledby={`${inputId}-label`}>
      <header className="card__header">
        <h2 id={`${inputId}-label`} className="card__title">Upload audio</h2>
        {jobId ? (
          <p className="card__meta">Active job: {jobId} · {status?.status ?? "queued"}</p>
        ) : (
          <p className="card__meta">Submit an audio file to start analysis.</p>
        )}
      </header>
      <form className="uploader__form" onSubmit={handleSubmit} aria-busy={isBusy}>
        <div className="uploader__field">
          <label className="uploader__label" htmlFor={inputId}>Audio file</label>
          <input
            id={inputId}
            className="uploader__input"
            type="file"
            accept="audio/*,.wav,.mp3,.flac,.m4a,.opus"
            onClick={handleClick}
            onChange={handleChange}
            aria-describedby={`${helperId} ${statusId}`}
            disabled={isBusy}
          />
          <p id={helperId} className="uploader__helper">
            Supported formats: WAV, MP3, FLAC, M4A, Opus. Max size depends on server settings.
          </p>
        </div>

        {file ? (
          <output id={statusId} className="uploader__filename" aria-live="polite">
            Selected file: {file.name}
          </output>
        ) : (
          <p id={statusId} className="uploader__helper">No file selected.</p>
        )}

        {(localError || error) ? (
          <p className="uploader__error" role="alert">{localError ?? error}</p>
        ) : null}

        <div className="uploader__actions">
          <button className="button button--primary" type="submit" disabled={isBusy || !file}>
            {isBusy ? "Submitting…" : "Start analysis"}
          </button>
        </div>
      </form>
    </section>
  );
}

export default AudioUploader;
