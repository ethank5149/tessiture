import { useMemo, useState, useEffect, useRef } from "react";
import { useExampleThumbnails, extractDominantColor } from "../hooks/useExampleThumbnail";

const getTitle = (example) =>
  String(example?.title || example?.display_name || example?.filename || "Untitled track");

const getArtist = (example) =>
  String(example?.artist || example?.creator || "Unknown artist");

const getAlbum = (example) => {
  const album = example?.album;
  return typeof album === "string" && album.trim() ? album : null;
};

const getThumbnailUrl = (example) => {
  const thumbnail = example?.thumbnail || example?.thumbnail_url || example?.artwork_url;
  return typeof thumbnail === "string" && thumbnail.trim() ? thumbnail : null;
};

/**
 * Groups examples by album, falling back to artist, then "Other".
 * Returns an array of { key, label, artist, tracks[] } group objects.
 * If every track lacks both album and artist, returns null (render flat).
 */
function groupExamples(examples) {
  const hasGrouping = examples.some((e) => getAlbum(e) || getArtist(e) !== "Unknown artist");
  if (!hasGrouping) return null;

  const map = new Map();
  for (const example of examples) {
    const album = getAlbum(example);
    const artist = getArtist(example);
    const key = album || artist || "Other";
    if (!map.has(key)) {
      map.set(key, { key, label: key, artist: album ? artist : null, tracks: [] });
    }
    map.get(key).tracks.push(example);
  }
  return Array.from(map.values());
}

function TrackThumb({ url, fallbackLetter, size = "sm" }) {
  if (url) {
    return (
      <div className={`examples__track-thumb examples__track-thumb--${size}`} aria-hidden="true">
        <img className="examples__thumb-image" src={url} alt="" loading="lazy" />
      </div>
    );
  }
  return (
    <div className={`examples__track-thumb examples__track-thumb--${size}`} aria-hidden="true">
      <span className="examples__thumb-fallback">{fallbackLetter}</span>
    </div>
  );
}

function ExampleGallery({
  examples = [],
  isLoading = false,
  onSelectExample,
  selectedExampleId = null,
  isSelecting = false,
  error = null,
}) {
  const [localError, setLocalError] = useState(null);
  const [openGroups, setOpenGroups] = useState(new Set());
  const [groupColors, setGroupColors] = useState({});
  const colorExtractionRef = useRef({});
  const autoOpenedRef = useRef(false);

  const resolvedThumbnails = useExampleThumbnails(examples);

  const groups = useMemo(() => groupExamples(examples), [examples]);

  // Auto-open the first group when groups first load
  useEffect(() => {
    if (autoOpenedRef.current || !groups || groups.length === 0) return;
    autoOpenedRef.current = true;
    setOpenGroups(new Set([groups[0].key]));
  }, [groups]);

  const toggleGroup = (key) => {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleSelect = async (example) => {
    if (!example?.id) {
      setLocalError("Example selection is invalid.");
      return;
    }
    setLocalError(null);
    try {
      await onSelectExample?.(example);
    } catch {
      // Parent component handles surfaced processing errors.
    }
  };

  const resolveThumbUrl = (example) => {
    const direct = getThumbnailUrl(example);
    return direct || resolvedThumbnails[example?.id]?.url || null;
  };

  // Extract dominant colors for group headers
  useEffect(() => {
    if (!groups) return;
    for (const group of groups) {
      const firstTrack = group.tracks[0];
      if (!firstTrack) continue;
      const thumbUrl = resolveThumbUrl(firstTrack);
      if (!thumbUrl) continue;
      const cacheKey = `${group.key}::${thumbUrl}`;
      if (colorExtractionRef.current[cacheKey]) continue;
      colorExtractionRef.current[cacheKey] = true;
      extractDominantColor(thumbUrl).then((color) => {
        if (color) {
          setGroupColors((prev) => ({ ...prev, [group.key]: color }));
        }
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, resolvedThumbnails]);

  return (
    <section className="card examples" aria-labelledby="example-gallery-title">
      <header className="card__header">
        <h2 id="example-gallery-title" className="card__title">Example gallery</h2>
        <p className="card__meta">Select a demo track to run analysis.</p>
      </header>

      {isLoading ? (
        <p className="examples__helper">Loading examples…</p>
      ) : examples.length === 0 ? (
        <p className="examples__helper">No examples are currently available.</p>
      ) : groups === null ? (
        // Flat list fallback when no album/artist metadata exists
        <ul className="examples__track-list" role="list">
          {examples.map((example) => {
            const title = getTitle(example);
            const artist = getArtist(example);
            const isSelected = selectedExampleId === example.id;
            const thumbUrl = resolveThumbUrl(example);
            return (
              <li key={example.id}>
                <button
                  className={`examples__track-row${isSelected ? " examples__track-row--selected" : ""}`}
                  type="button"
                  onClick={() => handleSelect(example)}
                  aria-pressed={isSelected}
                  aria-label={`Select example track: ${title}`}
                  disabled={isSelecting}
                >
                  <TrackThumb url={thumbUrl} fallbackLetter={title.charAt(0).toUpperCase()} />
                  <div className="examples__track-info">
                    <p className="examples__track-title">{title}</p>
                    <p className="examples__track-artist">{artist}</p>
                  </div>
                  {isSelected && <span className="examples__track-check" aria-hidden="true">✓</span>}
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        // Grouped list layout
        <div className="examples__groups">
          {groups.map((group) => {
            const isOpen = openGroups.has(group.key);
            const firstTrack = group.tracks[0];
            const groupThumbUrl = firstTrack ? resolveThumbUrl(firstTrack) : null;
            const fallbackLetter = group.label.charAt(0).toUpperCase();
            const extractedColor = groupColors[group.key];
            const accentStyle = extractedColor
              ? { "--group-accent": `rgba(${extractedColor.r}, ${extractedColor.g}, ${extractedColor.b}, 0.25)` }
              : undefined;

            return (
              <div
                key={group.key}
                className={`examples__group${isOpen ? " examples__group--open" : ""}`}
                style={accentStyle}
              >
                {/* Group header — horizontal compact row */}
                <button
                  type="button"
                  className="examples__group-header"
                  onClick={() => toggleGroup(group.key)}
                  aria-expanded={isOpen}
                  aria-controls={`examples-group-tracks-${group.key}`}
                >
                  <TrackThumb url={groupThumbUrl} fallbackLetter={fallbackLetter} size="md" />
                  <div className="examples__group-info">
                    <span className="examples__group-label">
                      {group.artist ?? group.label}
                    </span>
                    <span className="examples__group-sublabel">
                      {group.artist ? group.label : null}
                      {group.artist && group.label ? " · " : ""}
                      {group.tracks.length} {group.tracks.length === 1 ? "track" : "tracks"}
                    </span>
                  </div>
                  <span className="examples__group-chevron" aria-hidden="true" />
                </button>

                {/* Track list */}
                <ul
                  id={`examples-group-tracks-${group.key}`}
                  className="examples__track-list examples__group-tracks"
                  role="list"
                  hidden={!isOpen}
                >
                  {group.tracks.map((example) => {
                    const title = getTitle(example);
                    const artist = getArtist(example);
                    const isSelected = selectedExampleId === example.id;
                    const thumbUrl = resolveThumbUrl(example);
                    return (
                      <li key={example.id}>
                        <button
                          className={`examples__track-row${isSelected ? " examples__track-row--selected" : ""}`}
                          type="button"
                          onClick={() => handleSelect(example)}
                          aria-pressed={isSelected}
                          aria-label={`Select example track: ${title}`}
                          disabled={isSelecting}
                        >
                          <TrackThumb url={thumbUrl} fallbackLetter={title.charAt(0).toUpperCase()} />
                          <div className="examples__track-info">
                            <p className="examples__track-title">{title}</p>
                            <p className="examples__track-artist">{artist}</p>
                          </div>
                          {isSelected && <span className="examples__track-check" aria-hidden="true">✓</span>}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </div>
      )}

      {(localError || error) ? (
        <p className="uploader__error" role="alert">{localError ?? error}</p>
      ) : null}
    </section>
  );
}

export default ExampleGallery;
