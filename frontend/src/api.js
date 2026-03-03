const DEFAULT_API_BASE_URL =
  (typeof import.meta !== "undefined" &&
    import.meta.env &&
    import.meta.env.VITE_API_BASE_URL) ||
  "";

const API_BASE_URL = DEFAULT_API_BASE_URL.replace(/\/$/, "");
const TERMINAL_STATUSES = new Set(["completed", "failed", "error"]);

const buildUrl = (path) => {
  if (!path) {
    return API_BASE_URL || "";
  }
  if (!API_BASE_URL) {
    return path.startsWith("/") ? path : `/${path}`;
  }
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
};

const parseErrorMessage = async (response) => {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      const payload = await response.json();
      if (payload?.detail) {
        return payload.detail;
      }
      return JSON.stringify(payload);
    } catch (error) {
      return response.statusText || "Request failed.";
    }
  }
  return response.statusText || "Request failed.";
};

const ensureOk = async (response) => {
  if (response.ok) {
    return response;
  }
  const message = await parseErrorMessage(response);
  throw new Error(message);
};

const extractFilename = (contentDisposition, fallback) => {
  if (!contentDisposition) {
    return fallback;
  }
  const match = /filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?/i.exec(contentDisposition);
  return match?.[1] || fallback;
};

const toNumberOrNull = (value) => {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

const normalizeSummary = (summary = {}, metadata = {}, pitch = {}, tessitura = {}) => {
  const duration =
    summary?.duration_seconds ??
    metadata?.duration_seconds ??
    metadata?.duration ??
    null;
  const f0Min = summary?.f0_min ?? pitch?.f0_min ?? null;
  const f0Max = summary?.f0_max ?? pitch?.f0_max ?? null;
  const tessituraRange =
    summary?.tessitura_range ??
    tessitura?.metrics?.tessitura_band ??
    null;
  const confidence = summary?.confidence ?? null;
  const f0MinNote = summary?.f0_min_note ?? null;
  const f0MaxNote = summary?.f0_max_note ?? null;
  const tessituraRangeNotes =
    summary?.tessitura_range_notes ??
    tessitura?.metrics?.tessitura_band_notes ??
    null;

  return {
    duration_seconds: toNumberOrNull(duration),
    f0_min: toNumberOrNull(f0Min),
    f0_max: toNumberOrNull(f0Max),
    f0_min_note: f0MinNote,
    f0_max_note: f0MaxNote,
    tessitura_range: tessituraRange,
    tessitura_range_notes: tessituraRangeNotes,
    confidence: toNumberOrNull(confidence),
  };
};

const normalizeProgress = (progress, status) => {
  const numeric = Number(progress);
  if (Number.isFinite(numeric)) {
    return Math.max(0, Math.min(100, Math.round(numeric)));
  }
  if (TERMINAL_STATUSES.has(status)) {
    return 100;
  }
  if (status === "queued") {
    return 0;
  }
  return 0;
};

export const normalizeJobStatus = (payload = {}) => {
  const normalized = payload && typeof payload === "object" ? payload : {};
  const status =
    typeof normalized.status === "string" && normalized.status.trim()
      ? normalized.status.trim()
      : "queued";
  const message =
    typeof normalized.message === "string" && normalized.message.trim()
      ? normalized.message.trim()
      : typeof normalized.detail === "string" && normalized.detail.trim()
        ? normalized.detail.trim()
        : null;
  const stage =
    typeof normalized.stage === "string" && normalized.stage.trim()
      ? normalized.stage.trim()
      : status;

  return {
    ...normalized,
    status,
    progress: normalizeProgress(normalized.progress, status),
    stage,
    message,
    detail: message,
  };
};

export const normalizeAnalysisResult = (payload = {}) => {
  if (!payload || typeof payload !== "object") {
    return {
      metadata: {},
      summary: normalizeSummary(),
      pitch: { frames: [], f0_min: null, f0_max: null },
      note_events: [],
      chords: { timeline: [] },
      keys: { trajectory: [], probabilities: {} },
      tessitura: {},
      advanced: {},
      uncertainty: {},
      inferential_statistics: { metrics: {} },
      files: {},
    };
  }

  const root =
    payload.analysis && typeof payload.analysis === "object"
      ? payload.analysis
      : payload;

  const metadata =
    root.metadata && typeof root.metadata === "object"
      ? root.metadata
      : {};
  const pitch =
    root.pitch && typeof root.pitch === "object"
      ? root.pitch
      : {};
  const tessitura =
    root.tessitura && typeof root.tessitura === "object"
      ? root.tessitura
      : {};

  let normalizedInferential;
  if (root.inferential_statistics && typeof root.inferential_statistics === "object") {
    normalizedInferential = {
      ...root.inferential_statistics,
      metrics:
        root.inferential_statistics.metrics &&
        typeof root.inferential_statistics.metrics === "object"
          ? root.inferential_statistics.metrics
          : {},
    };
  } else {
    normalizedInferential = { metrics: {} };
    if (root.metrics && typeof root.metrics === "object") {
      console.warn(
        "[diagnostic] normalizeAnalysisResult schema mismatch: inferential payload is at top-level",
        {
          topLevelKeys: Object.keys(root),
          metricCount: Object.keys(root.metrics).length,
        }
      );
    }
  }

  const frames = Array.isArray(pitch.frames)
    ? pitch.frames
    : Array.isArray(root.pitch_frames)
      ? root.pitch_frames
      : [];

  const noteEvents = Array.isArray(root.note_events)
    ? root.note_events
    : Array.isArray(root?.notes?.events)
      ? root.notes.events
      : [];

  return {
    ...root,
    metadata,
    summary: normalizeSummary(root.summary, metadata, pitch, tessitura),
    pitch: {
      ...pitch,
      frames,
      f0_min: toNumberOrNull(pitch.f0_min ?? root.summary?.f0_min),
      f0_max: toNumberOrNull(pitch.f0_max ?? root.summary?.f0_max),
    },
    pitch_frames: frames,
    note_events: noteEvents,
    chords:
      root.chords && typeof root.chords === "object"
        ? { timeline: Array.isArray(root.chords.timeline) ? root.chords.timeline : [] }
        : { timeline: [] },
    keys:
      root.keys && typeof root.keys === "object"
        ? {
            trajectory: Array.isArray(root.keys.trajectory) ? root.keys.trajectory : [],
            probabilities:
              root.keys.probabilities && typeof root.keys.probabilities === "object"
                ? root.keys.probabilities
                : {},
          }
        : { trajectory: [], probabilities: {} },
    tessitura,
    advanced:
      root.advanced && typeof root.advanced === "object"
        ? root.advanced
        : {},
    uncertainty:
      root.uncertainty && typeof root.uncertainty === "object"
        ? root.uncertainty
        : {},
    inferential_statistics: normalizedInferential,
    files:
      root.files && typeof root.files === "object"
        ? root.files
        : {},
  };
};

export const submitAnalysisJob = async (file) => {
  if (!file) {
    throw new Error("Audio file is required.");
  }
  const formData = new FormData();
  formData.append("audio", file);
  const response = await ensureOk(
    await fetch(buildUrl("/analyze"), {
      method: "POST",
      body: formData,
    })
  );
  return response.json();
};

export const fetchExampleTracks = async () => {
  const response = await ensureOk(
    await fetch(buildUrl("/examples"), {
      method: "GET",
    })
  );
  const payload = await response.json();
  return Array.isArray(payload?.examples) ? payload.examples : [];
};

export const submitExampleAnalysisJob = async (exampleId) => {
  if (!exampleId) {
    throw new Error("Example ID is required.");
  }
  const query = new URLSearchParams({ example_id: exampleId }).toString();
  const response = await ensureOk(
    await fetch(buildUrl(`/analyze/example?${query}`), {
      method: "POST",
    })
  );
  return response.json();
};

export const fetchJobStatus = async (jobId) => {
  if (!jobId) {
    throw new Error("Job ID is required.");
  }
  const response = await ensureOk(
    await fetch(buildUrl(`/status/${jobId}`), {
      method: "GET",
    })
  );
  return normalizeJobStatus(await response.json());
};

export const fetchJobResults = async (jobId, format = "json") => {
  if (!jobId) {
    throw new Error("Job ID is required.");
  }
  const query = new URLSearchParams({ format }).toString();
  const response = await ensureOk(
    await fetch(buildUrl(`/results/${jobId}?${query}`), {
      method: "GET",
    })
  );
  if (format === "json") {
    return normalizeAnalysisResult(await response.json());
  }
  const blob = await response.blob();
  const contentDisposition = response.headers.get("content-disposition");
  return {
    blob,
    contentType: response.headers.get("content-type") || "",
    filename: extractFilename(contentDisposition, `results.${format}`),
  };
};

export const downloadJobResults = async (jobId, format = "csv") => {
  const result = await fetchJobResults(jobId, format);
  if (!result?.blob) {
    return result;
  }
  const url = URL.createObjectURL(result.blob);
  return {
    ...result,
    url,
  };
};

export const prepareReferenceFromExample = async (exampleId) => {
  const response = await fetch(buildUrl(`/reference/from-example/${encodeURIComponent(exampleId)}`), {
    method: "POST",
  });
  await ensureOk(response);
  return response.json();
};

export const prepareReferenceFromUpload = async (audioFile) => {
  const formData = new FormData();
  formData.append("audio", audioFile);
  const response = await fetch(buildUrl("/reference/upload"), {
    method: "POST",
    body: formData,
  });
  await ensureOk(response);
  return response.json();
};
