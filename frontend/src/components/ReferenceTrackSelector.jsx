import { useState } from "react";
import { prepareReferenceFromExample, prepareReferenceFromUpload } from "../api";

const TABS = { library: "library", upload: "upload" };

/**
 * Component for selecting a reference track for live comparison.
 *
 * @param {object} props
 * @param {Array} props.exampleTracks - Available example tracks from /examples API
 * @param {function} props.onReferenceReady - Called with (referenceId, referenceInfo) when ready
 * @param {boolean} [props.isLoading] - External loading state
 * @param {string|null} [props.error] - External error message
 */
const ReferenceTrackSelector = ({ exampleTracks = [], onReferenceReady, isLoading = false, error = null }) => {
  const [activeTab, setActiveTab] = useState(TABS.library);
  const [localLoading, setLocalLoading] = useState(false);
  const [localError, setLocalError] = useState(null);
  const [selectedExampleId, setSelectedExampleId] = useState(null);

  const busy = isLoading || localLoading;
  const displayError = localError || error;

  const handleExampleSelect = async (example) => {
    if (busy) return;
    setSelectedExampleId(example.id);
    setLocalLoading(true);
    setLocalError(null);
    try {
      const info = await prepareReferenceFromExample(example.id);
      if (typeof onReferenceReady === "function") {
        onReferenceReady(info.reference_id, info);
      }
    } catch (err) {
      setLocalError(err?.message ?? "Failed to prepare reference track.");
      setSelectedExampleId(null);
    } finally {
      setLocalLoading(false);
    }
  };

  const handleFileChange = async (event) => {
    const file = event.target.files?.[0];
    if (!file || busy) return;
    setLocalLoading(true);
    setLocalError(null);
    try {
      const info = await prepareReferenceFromUpload(file);
      if (typeof onReferenceReady === "function") {
        onReferenceReady(info.reference_id, info);
      }
    } catch (err) {
      setLocalError(err?.message ?? "Failed to upload reference audio.");
    } finally {
      setLocalLoading(false);
      // Reset file input so the same file can be re-selected
      event.target.value = "";
    }
  };

  const getTrackTitle = (track) =>
    track?.title || track?.display_name || track?.filename || "Untitled";

  const getTrackArtist = (track) =>
    track?.artist || track?.creator || "Unknown artist";

  return (
    <section className="reference-selector" aria-label="Select reference track">
      <h2 className="reference-selector__heading">Choose a Reference Track</h2>
      <p className="reference-selector__description">
        Select a track from the library or upload your own to compare your singing against.
      </p>

      {/* Tab toggle */}
      <div className="reference-selector__tabs" role="tablist" aria-label="Reference source">
        <button
          id="ref-tab-library"
          type="button"
          role="tab"
          aria-selected={activeTab === TABS.library}
          aria-controls="ref-panel-library"
          className={`button reference-selector__tab${activeTab === TABS.library ? " reference-selector__tab--active" : ""}`}
          onClick={() => setActiveTab(TABS.library)}
          disabled={busy}
        >
          From Library
        </button>
        <button
          id="ref-tab-upload"
          type="button"
          role="tab"
          aria-selected={activeTab === TABS.upload}
          aria-controls="ref-panel-upload"
          className={`button reference-selector__tab${activeTab === TABS.upload ? " reference-selector__tab--active" : ""}`}
          onClick={() => setActiveTab(TABS.upload)}
          disabled={busy}
        >
          Upload Reference
        </button>
      </div>

      {/* Library panel */}
      {activeTab === TABS.library ? (
        <div
          id="ref-panel-library"
          role="tabpanel"
          aria-labelledby="ref-tab-library"
          className="reference-selector__panel"
        >
          {exampleTracks.length === 0 ? (
            <p className="reference-selector__empty">No example tracks available.</p>
          ) : (
            <ul className="reference-selector__track-list" aria-label="Example tracks">
              {exampleTracks.map((track) => {
                const trackId = track?.id ?? track?.example_id ?? track?.filename;
                const isSelected = selectedExampleId === trackId;
                return (
                  <li key={trackId} className="reference-selector__track-item">
                    <button
                      type="button"
                      className={`reference-selector__track-btn${isSelected ? " reference-selector__track-btn--selected" : ""}`}
                      onClick={() => handleExampleSelect({ ...track, id: trackId })}
                      disabled={busy}
                      aria-pressed={isSelected}
                    >
                      <span className="reference-selector__track-title">{getTrackTitle(track)}</span>
                      <span className="reference-selector__track-artist">{getTrackArtist(track)}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}

      {/* Upload panel */}
      {activeTab === TABS.upload ? (
        <div
          id="ref-panel-upload"
          role="tabpanel"
          aria-labelledby="ref-tab-upload"
          className="reference-selector__panel"
        >
          <label className="reference-selector__file-label" htmlFor="ref-audio-upload">
            <span className="reference-selector__file-label-text">Select audio file</span>
            <input
              id="ref-audio-upload"
              type="file"
              accept="audio/*"
              className="reference-selector__file-input"
              onChange={handleFileChange}
              disabled={busy}
              aria-describedby={displayError ? "ref-error" : undefined}
            />
          </label>
          <p className="reference-selector__file-hint">
            Supported formats: MP3, WAV, FLAC, OGG, M4A
          </p>
        </div>
      ) : null}

      {/* Loading indicator */}
      {busy ? (
        <p className="reference-selector__loading" role="status" aria-live="polite">
          Preparing reference track…
        </p>
      ) : null}

      {/* Error display */}
      {displayError && !busy ? (
        <p id="ref-error" className="reference-selector__error" role="alert">
          {displayError}
        </p>
      ) : null}
    </section>
  );
};

export default ReferenceTrackSelector;
