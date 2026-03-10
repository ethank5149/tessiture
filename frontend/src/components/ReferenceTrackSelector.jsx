import { useMemo, useState, useEffect, useRef } from "react";
import { prepareReferenceFromExample, prepareReferenceFromUpload } from "../api";
import { useExampleThumbnails, extractDominantColor } from "../hooks/useExampleThumbnail";

const TABS = { library: "library", upload: "upload" };

/**
 * Groups tracks by album, falling back to artist, then "Other".
 * Returns null if every track lacks both album and artist.
 */
function groupTracks(tracks) {
  const getAlbum = (t) => {
    const album = t?.album;
    return typeof album === "string" && album.trim() ? album : null;
  };
  const getArtist = (t) => String(t?.artist || t?.creator || "Unknown artist");

  const hasGrouping = tracks.some((t) => getAlbum(t) || getArtist(t) !== "Unknown artist");
  if (!hasGrouping) return null;

  const map = new Map();
  for (const track of tracks) {
    const album = getAlbum(track);
    const artist = getArtist(track);
    const key = album || artist || "Other";
    if (!map.has(key)) {
      map.set(key, { key, label: key, artist: album ? artist : null, tracks: [] });
    }
    map.get(key).tracks.push(track);
  }
  return Array.from(map.values());
}

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
  const [openGroups, setOpenGroups] = useState(new Set());
  const [groupColors, setGroupColors] = useState({});
  const colorExtractionRef = useRef({});

  const resolvedThumbnails = useExampleThumbnails(exampleTracks);

  const busy = isLoading || localLoading;
  const displayError = localError || error;

  const groups = useMemo(() => groupTracks(exampleTracks), [exampleTracks]);

  // Extract dominant colors from group thumbnails when groups or resolved thumbnails change
  useEffect(() => {
    if (!groups) return;
    for (const group of groups) {
      const firstTrack = group.tracks[0];
      if (!firstTrack) continue;
      const groupThumbUrl = resolveGroupThumbUrl(firstTrack);
      if (!groupThumbUrl) continue;
      const cacheKey = `${group.key}::${groupThumbUrl}`;
      if (colorExtractionRef.current[cacheKey]) continue;
      colorExtractionRef.current[cacheKey] = true;
      extractDominantColor(groupThumbUrl).then((color) => {
        if (color) {
          setGroupColors((prev) => ({ ...prev, [group.key]: color }));
        }
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, resolvedThumbnails]);

  const toggleGroup = (key) => {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) { next.delete(key); } else { next.add(key); }
      return next;
    });
  };

  const handleExampleSelect = async (example) => {
    if (busy) return;
    const trackId = example?.id ?? example?.example_id ?? example?.filename;
    setSelectedExampleId(trackId);
    setLocalLoading(true);
    setLocalError(null);
    try {
      const info = await prepareReferenceFromExample(trackId);
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
      event.target.value = "";
    }
  };

  const getTrackTitle = (track) =>
    track?.title || track?.display_name || track?.filename || "Untitled";

  const getTrackArtist = (track) =>
    track?.artist || track?.creator || "Unknown artist";

  const resolveGroupThumbUrl = (firstTrack) => {
    if (!firstTrack) return null;
    const direct = firstTrack?.thumbnail || firstTrack?.thumbnail_url || firstTrack?.artwork_url;
    if (typeof direct === "string" && direct.trim()) return direct;
    return resolvedThumbnails[firstTrack?.id]?.url || null;
  };

  const renderLibraryPanel = () => {
    if (exampleTracks.length === 0) {
      return <p className="reference-selector__empty">No example tracks available.</p>;
    }

    if (groups === null) {
      // Flat list fallback
      return (
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
      );
    }

    // Grouped layout
    return (
      <div className="reference-selector__groups">
        {groups.map((group) => {
          const isOpen = openGroups.has(group.key);
          const firstTrack = group.tracks[0];
          const groupThumbUrl = resolveGroupThumbUrl(firstTrack);
          const fallbackLetter = group.label.charAt(0).toUpperCase();
          const extractedColor = groupColors[group.key];
          const groupStyle = extractedColor
            ? { background: `rgba(${extractedColor.r}, ${extractedColor.g}, ${extractedColor.b}, 0.15)` }
            : undefined;

          return (
            <div
              key={group.key}
              className={`reference-selector__group${isOpen ? " reference-selector__group--open" : ""}`}
              style={groupStyle}
            >
              <button
                type="button"
                className={`reference-selector__group-header${!groupThumbUrl ? " reference-selector__group-header--no-thumb" : ""}`}
                onClick={() => toggleGroup(group.key)}
                aria-expanded={isOpen}
                aria-controls={`ref-group-tracks-${group.key}`}
                disabled={busy}
              >
                <div className="reference-selector__group-thumb" aria-hidden="true">
                  {groupThumbUrl ? (
                    <img className="examples__thumb-image" src={groupThumbUrl} alt="" loading="lazy" />
                  ) : (
                    <span className="examples__thumb-fallback">{fallbackLetter}</span>
                  )}
                </div>
                <div className="reference-selector__group-header-overlay">
                  <div className="reference-selector__group-info">
                    <span className="reference-selector__group-label">
                      {group.artist ?? group.label}
                    </span>
                    <span className="reference-selector__group-artist">
                      {group.artist ? group.label : null}
                      <span className="reference-selector__group-count">
                        {group.artist && group.label ? " · " : ""}{group.tracks.length} {group.tracks.length === 1 ? "track" : "tracks"}
                      </span>
                    </span>
                  </div>
                  <span className="reference-selector__group-chevron" aria-hidden="true">▶</span>
                </div>
              </button>

              <ul
                id={`ref-group-tracks-${group.key}`}
                className="reference-selector__group-tracks"
                aria-label={`Tracks in ${group.label}`}
                hidden={!isOpen}
              >
                {group.tracks.map((track) => {
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
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    );
  };

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
          {renderLibraryPanel()}
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
