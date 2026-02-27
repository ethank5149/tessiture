const DEFAULT_API_BASE_URL =
  (typeof import.meta !== "undefined" &&
    import.meta.env &&
    import.meta.env.VITE_API_BASE_URL) ||
  "";

const API_BASE_URL = DEFAULT_API_BASE_URL.replace(/\/$/, "");

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

export const fetchJobStatus = async (jobId) => {
  if (!jobId) {
    throw new Error("Job ID is required.");
  }
  const response = await ensureOk(
    await fetch(buildUrl(`/status/${jobId}`), {
      method: "GET",
    })
  );
  return response.json();
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
    return response.json();
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
