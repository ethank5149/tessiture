import { useId, useState } from "react";

const AUDIO_TYPE_OPTIONS = [
  { value: "isolated", label: "Isolated Vocals" },
  { value: "mixed",    label: "Mixed Track" },
  { value: "auto",     label: "Auto-detect" },
];

const formatFileSize = (size) => {
  if (!Number.isFinite(size) || size < 0) {
    return "—";
  }
  if (size < 1024) {
    return `${Math.round(size)} B`;
  }

  const units = ["KB", "MB", "GB"];
  let value = size / 1024;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${units[unitIndex]}`;
};

const buildUploadFeedbackMessage = ({ file, isSubmitting, jobId, status }) => {
  if (!file) {
    return "No file selected.";
  }
  if (isSubmitting) {
    return "Uploading audio…";
  }

  const statusValue = status?.status;
  if (jobId && statusValue === "queued") {
    return "Upload received. Waiting for decode…";
  }
  if (jobId && statusValue === "processing") {
    return "Decoding audio and extracting pitch…";
  }
  if (jobId && statusValue === "completed") {
    return "Decode complete. Results are ready below.";
  }
  if (jobId && (statusValue === "failed" || statusValue === "error")) {
    return "Upload processed, but analysis failed.";
  }

  return "Ready to start analysis.";
};

function AudioUploader({
  onSubmit,
  isSubmitting = false,
  jobId = null,
  status = null,
  error = null,
  audioType = "isolated",
  onAudioTypeChange = null,
  forceVocalSeparation = false,
  onForceVocalSeparationChange = null,
}) {
  const inputId = useId();
  const helperId = useId();
  const statusId = useId();
  const audioTypeGroupId = useId();
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

  const handleAudioTypeChange = (event) => {
    onAudioTypeChange?.(event.target.value);
  };

  const handleForceVocalSeparationChange = (event) => {
    onForceVocalSeparationChange?.(event.target.checked);
  };

  const isBusy = Boolean(isSubmitting);
  const uploadFeedbackMessage = buildUploadFeedbackMessage({
    file,
    isSubmitting,
    jobId,
    status,
  });

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

        <div className="uploader__field">
          <fieldset className="uploader__audio-type-group" id={audioTypeGroupId}>
            <legend className="uploader__label">Audio type</legend>
            <div className="uploader__audio-type-options" role="group">
              {AUDIO_TYPE_OPTIONS.map(({ value, label }) => (
                <label
                  key={value}
                  className={`uploader__audio-type-option${audioType === value ? " uploader__audio-type-option--selected" : ""}`}
                >
                  <input
                    type="radio"
                    name={`${audioTypeGroupId}-audio-type`}
                    value={value}
                    checked={audioType === value}
                    onChange={handleAudioTypeChange}
                    disabled={isBusy}
                    className="uploader__audio-type-radio"
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
          <p className="uploader__helper">
            Best results with isolated vocal recordings (no backing track). If your file contains instruments, select Mixed Track.
          </p>
        </div>

        <div className="uploader__field">
          <label className="uploader__checkbox-label">
            <input
              type="checkbox"
              checked={forceVocalSeparation}
              onChange={handleForceVocalSeparationChange}
              disabled={isBusy}
              className="uploader__checkbox"
            />
            Force vocal separation
          </label>
          <p className="uploader__helper">
            Run Demucs vocal separation even for isolated vocals. May help create a cleaner vocal stem for a cappella recordings.
          </p>
        </div>

        <div id={statusId} className="uploader__preview" aria-live="polite">
          {file ? (
            <>
              <p className="uploader__preview-title">Upload preview</p>
              <dl className="summary-list">
                <div className="summary-list__item">
                  <dt>Selected file</dt>
                  <dd>{file.name}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>File size</dt>
                  <dd>{formatFileSize(file.size)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Status</dt>
                  <dd>{uploadFeedbackMessage}</dd>
                </div>
              </dl>
            </>
          ) : (
            <p className="uploader__helper">{uploadFeedbackMessage}</p>
          )}
        </div>

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
