import { useMemo, useState } from "react";
import { useExampleThumbnails } from "../hooks/useExampleThumbnail";

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

function GroupThumbnail({ thumbnailUrl, fallbackLetter }) {
  return (
    <div className="examples__group-header-thumb" aria-hidden="true">
      {thumbnailUrl ? (
        <img className="examples__thumb-image" src={thumbnailUrl} alt="" loading="lazy" />
      ) : (
        <span className="examples__thumb-fallback">{fallbackLetter}</span>
      )}
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

  const resolvedThumbnails = useExampleThumbnails(examples);

  const groups = useMemo(() => groupExamples(examples), [examples]);

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

  return (
    <section className="card examples" aria-labelledby="example-gallery-title">
      <header className="card__header">
        <h2 id="example-gallery-title" className="card__title">Example gallery</h2>
        <p className="card__meta">Select a demo track to run analysis in the main tab.</p>
      </header>

      {isLoading ? (
        <p className="examples__helper">Loading examples…</p>
      ) : examples.length === 0 ? (
        <p className="examples__helper">No examples are currently available.</p>
      ) : groups === null ? (
        // Flat grid fallback when no album/artist metadata exists
        <ul className="examples__grid" role="list">
          {examples.map((example) => {
            const title = getTitle(example);
            const isSelected = selectedExampleId === example.id;
            const thumbUrl = resolveThumbUrl(example);
            return (
              <li key={example.id} className="examples__grid-item">
                <button
                  className={`examples__card${isSelected ? " examples__card--selected" : ""}`}
                  type="button"
                  onClick={() => handleSelect(example)}
                  aria-pressed={isSelected}
                  aria-label={`Select example track: ${title}`}
                  disabled={isSelecting}
                >
                  <div className="examples__thumb" aria-hidden="true">
                    {thumbUrl ? (
                      <img className="examples__thumb-image" src={thumbUrl} alt="" loading="lazy" />
                    ) : (
                      <span className="examples__thumb-fallback">{title.charAt(0).toUpperCase()}</span>
                    )}
                  </div>
                  <div className="examples__info">
                    <p className="examples__name">{title}</p>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        // Grouped layout
        <div className="examples__groups">
          {groups.map((group) => {
            const isOpen = openGroups.has(group.key);
            const firstTrack = group.tracks[0];
            const groupThumbUrl = firstTrack ? resolveThumbUrl(firstTrack) : null;
            const fallbackLetter = group.label.charAt(0).toUpperCase();

            return (
              <div
                key={group.key}
                className={`examples__group${isOpen ? " examples__group--open" : ""}`}
              >
                <button
                  type="button"
                  className="examples__group-header"
                  onClick={() => toggleGroup(group.key)}
                  aria-expanded={isOpen}
                  aria-controls={`examples-group-tracks-${group.key}`}
                >
                  <GroupThumbnail thumbnailUrl={groupThumbUrl} fallbackLetter={fallbackLetter} />
                  <div className="examples__group-info">
                    <span className="examples__group-label">
                      {group.label}
                      <span className="examples__group-count">
                        · {group.tracks.length} {group.tracks.length === 1 ? "track" : "tracks"}
                      </span>
                    </span>
                    {group.artist ? (
                      <span className="examples__group-artist">{group.artist}</span>
                    ) : null}
                  </div>
                  <span className="examples__group-chevron" aria-hidden="true">▶</span>
                </button>

                <ul
                  id={`examples-group-tracks-${group.key}`}
                  className="examples__group-tracks examples__grid"
                  role="list"
                >
                  {group.tracks.map((example) => {
                    const title = getTitle(example);
                    const isSelected = selectedExampleId === example.id;
                    return (
                      <li key={example.id} className="examples__grid-item">
                        <button
                          className={`examples__card examples__card--compact${isSelected ? " examples__card--selected" : ""}`}
                          type="button"
                          onClick={() => handleSelect(example)}
                          aria-pressed={isSelected}
                          aria-label={`Select example track: ${title}`}
                          disabled={isSelecting}
                        >
                          <div className="examples__info">
                            <p className="examples__name">{title}</p>
                          </div>
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