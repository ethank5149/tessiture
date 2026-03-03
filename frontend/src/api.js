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

  return {
    duration_seconds: toNumberOrNull(duration),
    f0_min: toNumberOrNull(f0Min),
    f0_max: toNumberOrNull(f0Max),
    tessitura_range: tessituraRange,
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

  const metadata =
    payload.metadata && typeof payload.metadata === "object"
      ? payload.metadata
      : {};
  const pitch =
    payload.pitch && typeof payload.pitch === "object"
      ? payload.pitch
      : {};
  const tessitura =
    payload.tessitura && typeof payload.tessitura === "object"
      ? payload.tessitura
      : {};

  let normalizedInferential;
  if (payload.inferential_statistics && typeof payload.inferential_statistics === "object") {
    normalizedInferential = {
      ...payload.inferential_statistics,
      metrics:
        payload.inferential_statistics.metrics &&
        typeof payload.inferential_statistics.metrics === "object"
          ? payload.inferential_statistics.metrics
          : {},
    };
  } else {
    normalizedInferential = { metrics: {} };
    if (payload.metrics && typeof payload.metrics === "object") {
      console.warn(
        "[diagnostic] normalizeAnalysisResult schema mismatch: inferential payload is at top-level",
        {
          topLevelKeys: Object.keys(payload),
          metricCount: Object.keys(payload.metrics).length,
        }
      );
    }
  }

  const frames = Array.isArray(pitch.frames)
    ? pitch.frames
    : Array.isArray(payload.pitch_frames)
      ? payload.pitch_frames
      : [];

  const noteEvents = Array.isArray(payload.note_events)
    ? payload.note_events
    : Array.isArray(payload?.notes?.events)
      ? payload.notes.events
      : [];

  return {
    ...payload,
    metadata,
    summary: normalizeSummary(payload.summary, metadata, pitch, tessitura),
    pitch: {
      ...pitch,
      frames,
      f0_min: toNumberOrNull(pitch.f0_min ?? payload.summary?.f0_min),
      f0_max: toNumberOrNull(pitch.f0_max ?? payload.summary?.f0_max),
    },
    pitch_frames: frames,
    note_events: noteEvents,
    chords:
      payload.chords && typeof payload.chords === "object"
        ? { timeline: Array.isArray(payload.chords.timeline) ? payload.chords.timeline : [] }
        : { timeline: [] },
    keys:
      payload.keys && typeof payload.keys === "object"
        ? {
            trajectory: Array.isArray(payload.keys.trajectory) ? payload.keys.trajectory : [],
            probabilities:
              payload.keys.probabilities && typeof payload.keys.probabilities === "object"
                ? payload.keys.probabilities
                : {},
          }
        : { trajectory: [], probabilities: {} },
    tessitura,
    advanced:
      payload.advanced && typeof payload.advanced === "object"
        ? payload.advanced
        : {},
    uncertainty:
      payload.uncertainty && typeof payload.uncertainty === "object"
        ? payload.uncertainty
        : {},
    inferential_statistics: normalizedInferential,
    files:
      payload.files && typeof payload.files === "object"
        ? payload.files
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
