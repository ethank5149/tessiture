import { useState } from "react";

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

function ExampleGallery({
  examples = [],
  isLoading = false,
  onSelectExample,
  selectedExampleId = null,
  isSelecting = false,
  error = null,
}) {
  const [localError, setLocalError] = useState(null);

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
      ) : (
        <ul className="examples__grid" role="list">
          {examples.map((example) => {
            const title = getTitle(example);
            const artist = getArtist(example);
            const album = getAlbum(example);
            const thumbnailUrl = getThumbnailUrl(example);
            const isSelected = selectedExampleId === example.id;

            return (
              <li key={example.id} className="examples__grid-item">
                <button
                  className={`examples__card${isSelected ? " examples__card--selected" : ""}`}
                  type="button"
                  onClick={() => handleSelect(example)}
                  aria-pressed={isSelected}
                  aria-label={`Select example track: ${title} by ${artist}`}
                  disabled={isSelecting}
                >
                  <div className="examples__thumb" aria-hidden="true">
                    {thumbnailUrl ? (
                      <img className="examples__thumb-image" src={thumbnailUrl} alt="" loading="lazy" />
                    ) : (
                      <span className="examples__thumb-fallback">{title.charAt(0).toUpperCase()}</span>
                    )}
                  </div>

                  <div className="examples__info">
                    <p className="examples__name">{title}</p>
                    <p className="examples__artist">{artist}</p>
                    {album ? <p className="examples__album">{album}</p> : null}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {(localError || error) ? (
        <p className="uploader__error" role="alert">{localError ?? error}</p>
      ) : null}
    </section>
  );
}

export default ExampleGallery;