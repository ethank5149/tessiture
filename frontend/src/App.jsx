import { useCallback, useEffect, useRef, useState } from "react";
import AudioUploader from "./components/AudioUploader";
import AnalysisStatus from "./components/AnalysisStatus";
import AnalysisResults from "./components/AnalysisResults";
import ExampleGallery from "./components/ExampleGallery";
import {
  downloadJobResults,
  fetchExampleTracks,
  fetchJobResults,
  fetchJobStatus,
  submitAnalysisJob,
  submitExampleAnalysisJob,
} from "./api";

const POLL_INTERVAL_MS = 2000;

const APP_VIEWS = {
  upload: "upload",
  examples: "examples",
};

const isLikelyIosDevice = () => {
  if (typeof navigator === "undefined") {
    return false;
  }
  const ua = navigator.userAgent || "";
  const platform = navigator.platform || "";
  return /iPad|iPhone|iPod/i.test(ua) || (platform === "MacIntel" && navigator.maxTouchPoints > 1);
};

const triggerDownload = (result) => {
  if (!result?.url || typeof document === "undefined") {
    return result;
  }

  const anchor = document.createElement("a");
  anchor.href = result.url;
  anchor.rel = "noopener noreferrer";
  anchor.style.display = "none";

  if (isLikelyIosDevice()) {
    anchor.target = "_blank";
  } else if (result.filename) {
    anchor.download = result.filename;
  }

  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);

  window.setTimeout(() => {
    URL.revokeObjectURL(result.url);
  }, 1000);

  return result;
};

const getErrorMessage = (error, fallback) => {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === "string" && error.trim()) {
    return error;
  }
  return fallback;
};

const isTerminalStatus = (status) =>
  status === "completed" || status === "failed" || status === "error";

function App() {
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState(null);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [isFetchingResults, setIsFetchingResults] = useState(false);
  const [exampleTracks, setExampleTracks] = useState([]);
  const [isLoadingExamples, setIsLoadingExamples] = useState(false);
  const [exampleError, setExampleError] = useState(null);
  const [activeView, setActiveView] = useState(APP_VIEWS.upload);
  const [selectedExampleId, setSelectedExampleId] = useState(null);

  const pollingRef = useRef(null);

  const liveStatusMessage = error
    ? `Error: ${error}`
    : isFetchingResults
      ? "Fetching analysis results."
      : isSubmitting
        ? "Submitting analysis job."
        : isPolling
          ? `Analysis status: ${status?.status ?? "queued"}.`
          : status?.status === "completed"
            ? "Analysis completed."
            : "";

  const resetJob = useCallback(() => {
    setJobId(null);
    setStatus(null);
    setResults(null);
    setError(null);
  }, []);

  const submitJob = useCallback(async (submitter) => {
    setIsSubmitting(true);
    setError(null);
    setResults(null);
    setStatus(null);

    try {
      const response = await submitter();
      const nextJobId = response?.job_id ?? null;
      setJobId(nextJobId);
      if (nextJobId) {
        setStatus({ job_id: nextJobId, status: "queued" });
      }
      return response;
    } catch (submitError) {
      const message = getErrorMessage(submitError, "Unable to submit analysis job.");
      setError(message);
      throw submitError;
    } finally {
      setIsSubmitting(false);
    }
  }, []);

  const submitUploadJob = useCallback(
    async (file) => {
      setSelectedExampleId(null);
      return submitJob(() => submitAnalysisJob(file));
    },
    [submitJob]
  );

  const submitExampleJob = useCallback(
    async (exampleId) => submitJob(() => submitExampleAnalysisJob(exampleId)),
    [submitJob]
  );

  const handleExampleSelection = useCallback(
    async (example) => {
      if (!example?.id) {
        return;
      }
      setSelectedExampleId(example.id);
      setActiveView(APP_VIEWS.upload);
      await submitExampleJob(example.id);
    },
    [submitExampleJob]
  );

  const fetchResults = useCallback(
    async (targetId = jobId) => {
      if (!targetId) {
        return null;
      }
      setIsFetchingResults(true);
      setError(null);
      try {
        const data = await fetchJobResults(targetId, "json");
        setResults(data);
        return data;
      } catch (fetchError) {
        const message = getErrorMessage(fetchError, "Unable to fetch results.");
        setError(message);
        return null;
      } finally {
        setIsFetchingResults(false);
      }
    },
    [jobId]
  );

  const downloadResults = useCallback(
    async (format = "csv") => {
      if (!jobId) {
        return null;
      }
      setIsFetchingResults(true);
      setError(null);
      try {
        const result = await downloadJobResults(jobId, format);
        return triggerDownload(result);
      } catch (downloadError) {
        const message = getErrorMessage(downloadError, "Unable to download results.");
        setError(message);
        return null;
      } finally {
        setIsFetchingResults(false);
      }
    },
    [jobId]
  );

  useEffect(() => {
    let isMounted = true;

    const loadExamples = async () => {
      setIsLoadingExamples(true);
      setExampleError(null);
      try {
        const examples = await fetchExampleTracks();
        if (isMounted) {
          setExampleTracks(examples);
        }
      } catch (loadError) {
        if (isMounted) {
          setExampleError(getErrorMessage(loadError, "Unable to load example tracks."));
        }
      } finally {
        if (isMounted) {
          setIsLoadingExamples(false);
        }
      }
    };

    loadExamples();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!jobId) {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      return undefined;
    }

    let isMounted = true;

    const poll = async () => {
      try {
        const nextStatus = await fetchJobStatus(jobId);
        if (!isMounted) {
          return;
        }
        setStatus(nextStatus);

        if (isTerminalStatus(nextStatus?.status)) {
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
          setIsPolling(false);

          if (nextStatus?.status === "completed") {
            await fetchResults(jobId);
          } else if (nextStatus?.error) {
            setError(nextStatus.error);
          }
        }
      } catch (pollError) {
        if (!isMounted) {
          return;
        }
        const message = getErrorMessage(pollError, "Unable to fetch job status.");
        setError(message);
        setIsPolling(false);
      }
    };

    setIsPolling(true);
    poll();
    pollingRef.current = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      isMounted = false;
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      setIsPolling(false);
    };
  }, [jobId, fetchResults]);

  return (
    <main className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>

      {liveStatusMessage ? (
        <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {liveStatusMessage}
        </p>
      ) : null}

      <header className="app-shell__header">
        <h1 className="app-shell__title">
          <img
            src="/favicon.svg"
            alt=""
            className="app-shell__logo"
            width="36"
            height="36"
          />
          Tessitura Analysis
        </h1>
        <p className="app-shell__subtitle">
          Upload an audio file, or pick a demo track in Example Gallery to run analysis here in the main tab.
        </p>
      </header>

      <div className="app-shell__tabs" role="tablist" aria-label="Analysis input mode">
        <button
          id="tab-upload"
          className={`button app-shell__tab${activeView === APP_VIEWS.upload ? " app-shell__tab--active" : ""}`}
          type="button"
          role="tab"
          aria-selected={activeView === APP_VIEWS.upload}
          aria-controls="panel-upload"
          onClick={() => setActiveView(APP_VIEWS.upload)}
        >
          Upload audio
        </button>
        <button
          id="tab-examples"
          className={`button app-shell__tab${activeView === APP_VIEWS.examples ? " app-shell__tab--active" : ""}`}
          type="button"
          role="tab"
          aria-selected={activeView === APP_VIEWS.examples}
          aria-controls="panel-examples"
          onClick={() => setActiveView(APP_VIEWS.examples)}
        >
          Example gallery
        </button>
      </div>

      <div id="main-content" className="app-shell__content" tabIndex={-1}>
        {activeView === APP_VIEWS.upload ? (
          <>
            <div id="panel-upload" role="tabpanel" aria-labelledby="tab-upload" className="app-shell__panel">
              <AudioUploader
                onSubmit={submitUploadJob}
                isSubmitting={isSubmitting}
                jobId={jobId}
                status={status}
                error={error}
              />
            </div>

            <AnalysisStatus
              jobId={jobId}
              status={status}
              error={error}
              isPolling={isPolling}
              isFetchingResults={isFetchingResults}
            />

            <AnalysisResults
              results={results}
              status={status}
              error={error}
              isFetchingResults={isFetchingResults}
              onDownloadCsv={() => downloadResults("csv")}
              onDownloadJson={() => downloadResults("json")}
              onDownloadPdf={() => downloadResults("pdf")}
            />
          </>
        ) : null}

        {activeView === APP_VIEWS.examples ? (
          <div id="panel-examples" role="tabpanel" aria-labelledby="tab-examples" className="app-shell__panel">
            <ExampleGallery
              examples={exampleTracks}
              isLoading={isLoadingExamples}
              onSelectExample={handleExampleSelection}
              selectedExampleId={selectedExampleId}
              isSelecting={isSubmitting}
              error={exampleError}
            />
          </div>
        ) : null}
      </div>
    </main>
  );
}

export default App;
