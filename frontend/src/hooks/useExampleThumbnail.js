import { useEffect, useRef, useState } from "react";
import jsmediatags from "jsmediatags/dist/jsmediatags.min.js";

const IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"];

export const buildExampleMediaUrl = (filename) => {
  if (!filename) return null;
  return `/examples/${encodeURIComponent(filename)}`;
};

const getBaseFilename = (filename) => {
  if (!filename) return "";
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
      if (signal) signal.removeEventListener("abort", handleAbort);
    };
    const handleAbort = () => { cleanup(); resolve(null); };
    if (signal) signal.addEventListener("abort", handleAbort, { once: true });
    img.onload = () => { cleanup(); resolve(url); };
    img.onerror = () => { cleanup(); resolve(null); };
    img.src = url;
  });

const readArtworkFromBlob = (blob, signal) =>
  new Promise((resolve) => {
    if (!blob || signal?.aborted) { resolve(null); return; }
    try {
      jsmediatags.read(blob, {
        onSuccess: (tag) => {
          if (signal?.aborted) { resolve(null); return; }
          const picture = tag?.tags?.picture;
          if (!picture?.data?.length) { resolve(null); return; }
          const byteArray = new Uint8Array(picture.data);
          const coverBlob = new Blob([byteArray], { type: picture.format || "image/jpeg" });
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
  if (!baseName) return null;
  for (const ext of IMAGE_EXTENSIONS) {
    const candidate = buildExampleMediaUrl(`${baseName}.${ext}`);
    const matched = await loadImageUrl(candidate, signal);
    if (matched) return { url: matched, revoke: false };
  }
  return null;
};

/**
 * Resolves an example track's thumbnail using a multi-step strategy:
 * 1. Server-side /thumbnail endpoint
 * 2. Client-side jsmediatags extraction from the audio file
 * 3. Same-name image sidecar file
 *
 * Returns { url: string|null, revoke: boolean }
 */
export const resolveExampleThumbnail = async (example, signal) => {
  const filename = typeof example?.filename === "string" ? example.filename : "";

  if (filename) {
    const thumbnailUrl = `/examples/${encodeURIComponent(filename)}/thumbnail`;
    try {
      const thumbResponse = await fetch(thumbnailUrl, { signal });
      if (thumbResponse.ok) {
        const blob = await thumbResponse.blob();
        return { url: URL.createObjectURL(blob), revoke: true };
      }
    } catch {
      // Fall through.
    }
  }

  const audioUrl = buildExampleMediaUrl(filename);
  if (audioUrl) {
    try {
      const response = await fetch(audioUrl, { signal });
      if (response.ok) {
        const blob = await response.blob();
        const artwork = await readArtworkFromBlob(blob, signal);
        if (artwork?.url) return artwork;
      }
    } catch {
      // Fall through.
    }
  }

  const fallback = filename ? await resolveFallbackImage(filename, signal) : null;
  return fallback ?? { url: null, revoke: false };
};

/**
 * React hook that lazily resolves thumbnails for a list of examples.
 * Returns a map of { [example.id]: { url: string|null, revoke: boolean, resolved: boolean } }
 */
export function useExampleThumbnails(examples) {
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
    const exampleIds = new Set(examples.map((e) => e?.id).filter(Boolean));
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
        if (!example?.id) continue;
        const thumbnail = example?.thumbnail || example?.thumbnail_url || example?.artwork_url;
        if (typeof thumbnail === "string" && thumbnail.trim()) continue;
        if (resolvedThumbnailsRef.current[example.id]) continue;

        const resolved = await resolveExampleThumbnail(example, controller.signal);
        if (!isActive || controller.signal.aborted) return;

        setResolvedThumbnails((prev) => {
          if (prev[example.id]) return prev;
          if (resolved?.revoke && resolved?.url) objectUrlsRef.current.add(resolved.url);
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

  return resolvedThumbnails;
}

/**
 * Extracts a desaturated average color from an image URL using an off-screen
 * Canvas. Returns a Promise that resolves to { r, g, b } or null on failure.
 */
export function extractDominantColor(imageUrl) {
  return new Promise((resolve) => {
    try {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        try {
          const canvas = document.createElement("canvas");
          canvas.width = 1;
          canvas.height = 1;
          const ctx = canvas.getContext("2d");
          ctx.drawImage(img, 0, 0, 1, 1);
          const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
          // Blend toward neutral (128) to avoid garish tints
          resolve({
            r: Math.round(r * 0.6 + 128 * 0.4),
            g: Math.round(g * 0.6 + 128 * 0.4),
            b: Math.round(b * 0.6 + 128 * 0.4),
          });
        } catch {
          resolve(null);
        }
      };
      img.onerror = () => resolve(null);
      img.src = imageUrl;
    } catch {
      resolve(null);
    }
  });
}
