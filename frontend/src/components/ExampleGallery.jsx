import { useEffect, useRef, useState } from "react";
import jsmediatags from "jsmediatags/dist/jsmediatags.min.js";

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

const IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"];

const buildExampleMediaUrl = (filename) => {
  if (!filename) {
    return null;
  }
  return `/examples/${encodeURIComponent(filename)}`;
};

const getBaseFilename = (filename) => {
  if (!filename) {
    return "";
  }
  const normalized = filename.split("/").pop() || filename;
  return normalized.replace(/\.[^/.]+$/, "");
};

const loadImageUrl = (url, signal) =>
  new Promise((resolve) => {
    if (!url || signal?.aborted) {
      resolve(null);
      return;
    }

    const img = new Image();
    const cleanup = () => {
      img.onload = null;
      img.onerror = null;
      if (signal) {
        signal.removeEventListener("abort", handleAbort);
      }
    };
    const handleAbort = () => {
      cleanup();
      resolve(null);
    };

    if (signal) {
      signal.addEventListener("abort", handleAbort, { once: true });
    }

    img.onload = () => {
      cleanup();
      resolve(url);
    };
    img.onerror = () => {
      cleanup();
      resolve(null);
    };
    img.src = url;
  });

const readArtworkFromBlob = (blob, signal) =>
  new Promise((resolve) => {
    if (!blob || signal?.aborted) {
      resolve(null);
      return;
    }

    try {
      jsmediatags.read(blob, {
        onSuccess: (tag) => {
          if (signal?.aborted) {
            resolve(null);
            return;
          }
          const picture = tag?.tags?.picture;
          if (!picture?.data?.length) {
            resolve(null);
            return;
          }
          const byteArray = new Uint8Array(picture.data);
          const coverBlob = new Blob([byteArray], {
            type: picture.format || "image/jpeg",
          });
          resolve({ url: URL.createObjectURL(coverBlob), revoke: true });
        },
        onError: () => resolve(null),
      });
    } catch {
      resolve(null);
    }
  });

const resolveFallbackImage = async (filename, signal) => {
  const baseName = getBaseFilename(filename);
  if (!baseName) {
    return null;
  }

  for (const extension of IMAGE_EXTENSIONS) {
    const candidate = buildExampleMediaUrl(`${baseName}.${extension}`);
    const matched = await loadImageUrl(candidate, signal);
    if (matched) {
      return { url: matched, revoke: false };
    }
  }
  return null;
};

const resolveExampleThumbnail = async (example, signal) => {
  const filename = typeof example?.filename === "string" ? example.filename : "";

  // 1. Try server-side thumbnail extraction (supports FLAC, Opus, MP3, M4A).
  if (filename) {
    const thumbnailUrl = `/examples/${encodeURIComponent(filename)}/thumbnail`;
    try {
      const thumbResponse = await fetch(thumbnailUrl, { signal });
      if (thumbResponse.ok) {
        const blob = await thumbResponse.blob();
        return { url: URL.createObjectURL(blob), revoke: true };
      }
    } catch {
      // Ignore and fall through.
    }
  }

  // 2. Try client-side jsmediatags extraction from the raw audio file.
  const audioUrl = buildExampleMediaUrl(filename);
  if (audioUrl) {
    try {
      const response = await fetch(audioUrl, { signal });
      if (response.ok) {
        const blob = await response.blob();
        const artwork = await readArtworkFromBlob(blob, signal);
        if (artwork?.url) {
          return artwork;
        }
      }
    } catch {
      // Ignore example artwork fetch failures and fall back to images.
    }
  }

  // 3. Fall back to a same-name image sidecar file.
  const fallback = filename ? await resolveFallbackImage(filename, signal) : null;
  return fallback ?? { url: null, revoke: false };
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
  const [resolvedThumbnails, setResolvedThumbnails] = useState({});
  const resolvedThumbnailsRef = useRef(resolvedThumbnails);
  const objectUrlsRef = useRef(new Set());

  useEffect(() => {
    resolvedThumbnailsRef.current = resolvedThumbnails;
  }, [resolvedThumbnails]);

  const revokeThumbnail = (entry) => {
    if (entry?.revoke && entry?.url) {
      URL.revokeObjectURL(entry.url);
      objectUrlsRef.current.delete(entry.url);
    }
  };

  useEffect(() => {
    const exampleIds = new Set(examples.map((example) => example?.id).filter(Boolean));
    setResolvedThumbnails((prev) => {
      const next = { ...prev };
      Object.entries(next).forEach(([id, entry]) => {
        if (!exampleIds.has(id)) {
          revokeThumbnail(entry);
          delete next[id];
        }
      });
      return next;
    });

    const controller = new AbortController();
    let isActive = true;

    const resolveAll = async () => {
      for (const example of examples) {
        if (!example?.id) {
          continue;
        }
        if (getThumbnailUrl(example)) {
          continue;
        }
        if (resolvedThumbnailsRef.current[example.id]) {
          continue;
        }

        const resolved = await resolveExampleThumbnail(example, controller.signal);
        if (!isActive || controller.signal.aborted) {
          return;
        }

        setResolvedThumbnails((prev) => {
          if (prev[example.id]) {
            return prev;
          }
          if (resolved?.revoke && resolved?.url) {
            objectUrlsRef.current.add(resolved.url);
          }
          return { ...prev, [example.id]: { ...resolved, resolved: true } };
        });
      }
    };

    resolveAll();

    return () => {
      isActive = false;
      controller.abort();
    };
  }, [examples]);

  useEffect(
    () => () => {
      objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      objectUrlsRef.current.clear();
    },
    []
  );

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
            const resolvedThumbnailUrl = resolvedThumbnails[example.id]?.url;
            const thumbnailUrl = getThumbnailUrl(example) || resolvedThumbnailUrl;
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