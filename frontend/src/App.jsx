import { useCallback, useEffect, useRef, useState } from "react";
import AudioUploader from "./components/AudioUploader";
import AnalysisStatus from "./components/AnalysisStatus";
import AnalysisResults from "./components/AnalysisResults";
import ExampleGallery from "./components/ExampleGallery";
import ReferenceTrackSelector from "./components/ReferenceTrackSelector";
import LiveComparisonView from "./components/LiveComparisonView";
import ComparisonResults from "./components/ComparisonResults";
import {
  downloadJobResults,
  fetchExampleTracks,
  fetchJobResults,
  fetchJobStatus,
  normalizeJobStatus,
  submitAnalysisJob,
  submitExampleAnalysisJob,
} from "./api";

const POLL_INTERVAL_MS = 2000;

// Two-axis state replaces the old APP_VIEWS tab constant.
// source: 'upload' | 'example' | 'live' | null
// mode:   'analyze' | 'compare' | null

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

const normalizeReleaseVersion = (value) => {
  if (typeof value !== "string") {
    return "";
  }
  const trimmed = value.trim();
  if (!/^v?\d+\.\d+\.\d+$/.test(trimmed)) {
    return "";
  }
  return trimmed.replace(/^v/, "");
};

// Source card definitions
const SOURCE_CARDS = [
  { id: "upload",  emoji: "📁", label: "Upload a File",    desc: "Analyze your own recording" },
  { id: "example", emoji: "🎵", label: "Example Library",  desc: "Pick a demo track" },
  { id: "live",    emoji: "🎤", label: "Record Live",       desc: "Mic comparison session" },
];

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

  // Two-axis state machine — replaces activeView / APP_VIEWS
  const [audioSource, setAudioSource] = useState(null); // 'upload' | 'example' | 'live' | null
  const [analysisMode, setAnalysisMode] = useState(null); // 'analyze' | 'compare' | null

  // Per-source transient state
  const [selectedExampleId, setSelectedExampleId] = useState(null);
  const [acceptedFile, setAcceptedFile] = useState(null); // file accepted by uploader before intent
  const [audioType, setAudioType] = useState("isolated");
  const [forceVocalSeparation, setForceVocalSeparation] = useState(false);

  // Comparison state
  const [referenceId, setReferenceId] = useState(null);
  const [referenceInfo, setReferenceInfo] = useState(null);
  const [sessionReport, setSessionReport] = useState(null);

  const appReleaseVersion = normalizeReleaseVersion(import.meta?.env?.VITE_APP_VERSION);

  const pollingRef = useRef(null);

  const liveStatusMessage = error
    ? `Error: ${error}`
    : isFetchingResults
      ? "Fetching analysis results."
      : isSubmitting
        ? "Submitting analysis job."
        : isPolling
          ? `Analysis status: ${status?.stage ?? status?.status ?? "queued"} (${status?.progress ?? 0}%).`
          : status?.status === "completed"
            ? "Analysis completed."
            : "";

  // ── Reset helpers ──────────────────────────────────────────────────────────

  const resetJob = useCallback(() => {
    setJobId(null);
    setStatus(null);
    setResults(null);
    setError(null);
  }, []);

  /** Full reset — back to Step 1 */
  const resetAll = useCallback(() => {
    resetJob();
    setAudioSource(null);
    setAnalysisMode(null);
    setSelectedExampleId(null);
    setAcceptedFile(null);
    setReferenceId(null);
    setReferenceInfo(null);
    setSessionReport(null);
  }, [resetJob]);

  /** Change source — resets downstream state */
  const selectSource = useCallback(
    (src) => {
      if (src === audioSource) return;
      resetJob();
      setAudioSource(src);
      setAnalysisMode(src === "live" ? "compare" : null);
      setSelectedExampleId(null);
      setAcceptedFile(null);
      setReferenceId(null);
      setReferenceInfo(null);
      setSessionReport(null);
    },
    [audioSource, resetJob]
  );

  // ── Job submission helpers ──────────────────────────────────────────────────

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
        setStatus(normalizeJobStatus({ job_id: nextJobId, status: "queued", progress: 0 }));
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
      return submitJob(() => submitAnalysisJob(file, audioType, forceVocalSeparation));
    },
    [submitJob, audioType, forceVocalSeparation]
  );

  const submitExampleJob = useCallback(
    async (exampleId) => submitJob(() => submitExampleAnalysisJob(exampleId)),
    [submitJob]
  );

  // ── Intent handlers (Step 2 → Step 3) ─────────────────────────────────────

  /**
   * Called when user picks "Full analysis" intent for an upload file.
   * Immediately starts the job.
   */
  const handleUploadAnalyzeIntent = useCallback(async () => {
    if (!acceptedFile) return;
    setAnalysisMode("analyze");
    await submitUploadJob(acceptedFile);
  }, [acceptedFile, submitUploadJob]);

  /**
   * Called when user picks "Full analysis" intent for an example.
   */
  const handleExampleAnalyzeIntent = useCallback(async () => {
    if (!selectedExampleId) return;
    setAnalysisMode("analyze");
    await submitExampleJob(selectedExampleId);
  }, [selectedExampleId, submitExampleJob]);

  /**
   * AudioUploader's onSubmit callback — in the new flow, we use this to
   * capture the file and show the intent panel, not to immediately start a job.
   * The component itself calls onSubmit with the file; we intercept and store it.
   */
  const handleFileAccepted = useCallback((file) => {
    setAcceptedFile(file);
    setAnalysisMode(null); // reset intent so intent panel appears
    resetJob();
  }, [resetJob]);

  /**
   * Called by ExampleGallery when user picks an example track.
   * Stores selected ID and shows intent panel.
   */
  const handleExampleSelected = useCallback((example) => {
    if (!example?.id) return;
    setSelectedExampleId(example.id);
    setAnalysisMode(null); // show intent panel
    resetJob();
  }, [resetJob]);

  // ── Results fetching ───────────────────────────────────────────────────────

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

  // ── Side effects ───────────────────────────────────────────────────────────

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
    const clearPollingTimer = () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };

    if (!jobId) {
      clearPollingTimer();
      setIsPolling(false);
      return undefined;
    }

    let isMounted = true;

    const poll = async () => {
      try {
        const nextStatus = normalizeJobStatus(await fetchJobStatus(jobId));
        if (!isMounted) {
          return;
        }
        setStatus(nextStatus);

        if (isTerminalStatus(nextStatus?.status)) {
          clearPollingTimer();
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
        clearPollingTimer();
        setError(message);
        setIsPolling(false);
      }
    };

    setIsPolling(true);
    poll();
    pollingRef.current = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      isMounted = false;
      clearPollingTimer();
      setIsPolling(false);
    };
  }, [jobId, fetchResults]);

  // ── Derived booleans ───────────────────────────────────────────────────────

  const hasJobInProgress = isSubmitting || isPolling || isFetchingResults;
  const showResults = results !== null || error !== null || isSubmitting || isPolling || isFetchingResults;

  const analysisAudioSourceUrl = (() => {
    if (!results || typeof results !== "object") {
      return null;
    }

    const source = String(results?.metadata?.source ?? results?.metadata?.input_type ?? "").toLowerCase();
    if (source !== "example") {
      return null;
    }

    const originalFilename =
      typeof results?.metadata?.original_filename === "string" && results.metadata.original_filename.trim()
        ? results.metadata.original_filename.trim()
        : null;

    if (!originalFilename) {
      return null;
    }

    return `/examples/${encodeURIComponent(originalFilename)}`;
  })();

  const analysisAudioSourceLabel =
    analysisAudioSourceUrl && typeof results?.metadata?.filename === "string" && results.metadata.filename.trim()
      ? results.metadata.filename.trim()
      : analysisAudioSourceUrl
        ? "Example track"
        : null;

  // Whether the results/status region should be shown (Step 3)
  const showStep3 =
    showResults ||
    (analysisMode === "compare" && (referenceInfo !== null || sessionReport !== null));

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
          Choose an audio source below to get started. Upload your own file, pick a demo track, or use your microphone for a live session.
        </p>
        {appReleaseVersion ? (
          <p className="app-shell__release-version">Release {appReleaseVersion}</p>
        ) : null}
      </header>

      {/* ── Step 1: Audio Source Selector ──────────────────────────────────── */}
      <section className="source-selector" aria-label="Step 1: Choose audio source">
        <div className="source-selector__grid" role="group" aria-label="Audio source">
          {SOURCE_CARDS.map(({ id, emoji, label, desc }) => (
            <button
              key={id}
              type="button"
              className={`source-card${audioSource === id ? " source-card--active" : ""}`}
              aria-pressed={audioSource === id}
              onClick={() => selectSource(id)}
            >
              <span className="source-card__emoji" aria-hidden="true">{emoji}</span>
              <span className="source-card__label">{label}</span>
              <span className="source-card__desc">{desc}</span>
            </button>
          ))}
        </div>
      </section>

      <div id="main-content" className="app-shell__content" tabIndex={-1}>
        {/* ── Step 2: Context-Sensitive Panel ──────────────────────────────── */}

        {/* Upload source: show uploader; after file accepted show intent panel */}
        {audioSource === "upload" ? (
          <section
            className={`step-panel${audioSource ? " step-panel--visible" : ""}`}
            aria-label="Step 2: Upload and select analysis type"
          >
            <AudioUploader
              onSubmit={handleFileAccepted}
              isSubmitting={isSubmitting}
              jobId={jobId}
              status={status}
              error={acceptedFile ? null : error}
              audioType={audioType}
              onAudioTypeChange={(t) => setAudioType(t)}
              forceVocalSeparation={forceVocalSeparation}
              onForceVocalSeparationChange={(v) => setForceVocalSeparation(v)}
            />

            {acceptedFile && analysisMode === null ? (
              <div className="intent-panel">
                <p className="intent-panel__prompt">What would you like to do with <strong>{acceptedFile.name}</strong>?</p>
                <div className="intent-panel__cards">
                  <button
                    type="button"
                    className="intent-card"
                    onClick={handleUploadAnalyzeIntent}
                    disabled={hasJobInProgress}
                  >
                    <span className="intent-card__emoji" aria-hidden="true">🔬</span>
                    <span className="intent-card__label">Full analysis</span>
                    <span className="intent-card__desc">Tessitura, pitch range, and statistics</span>
                  </button>
                  <button
                    type="button"
                    className="intent-card"
                    onClick={() => setAnalysisMode("compare")}
                    disabled={hasJobInProgress}
                  >
                    <span className="intent-card__emoji" aria-hidden="true">🎯</span>
                    <span className="intent-card__label">Compare to a reference</span>
                    <span className="intent-card__desc">Match your performance against a reference track</span>
                  </button>
                </div>
              </div>
            ) : null}

            {/* Upload + compare intent: show reference selector then start job */}
            {acceptedFile && analysisMode === "compare" && !referenceInfo && !sessionReport ? (
              <div className="step-panel__section">
                <ReferenceTrackSelector
                  exampleTracks={exampleTracks}
                  onReferenceReady={(refId, refInfo) => {
                    setReferenceId(refId);
                    setReferenceInfo(refInfo);
                  }}
                />
              </div>
            ) : null}
          </section>
        ) : null}

        {/* Example source: show gallery; after selection show intent panel */}
        {audioSource === "example" ? (
          <section
            className={`step-panel${audioSource ? " step-panel--visible" : ""}`}
            aria-label="Step 2: Example library and analysis type"
          >
            <ExampleGallery
              examples={exampleTracks}
              isLoading={isLoadingExamples}
              onSelectExample={handleExampleSelected}
              selectedExampleId={selectedExampleId}
              isSelecting={isSubmitting}
              error={exampleError}
            />

            {selectedExampleId && analysisMode === null ? (
              <div className="intent-panel">
                <p className="intent-panel__prompt">What would you like to do with this example?</p>
                <div className="intent-panel__cards">
                  <button
                    type="button"
                    className="intent-card"
                    onClick={handleExampleAnalyzeIntent}
                    disabled={hasJobInProgress}
                  >
                    <span className="intent-card__emoji" aria-hidden="true">🔬</span>
                    <span className="intent-card__label">Full analysis</span>
                    <span className="intent-card__desc">Tessitura, pitch range, and statistics</span>
                  </button>
                  <button
                    type="button"
                    className="intent-card"
                    onClick={() => setAnalysisMode("compare")}
                    disabled={hasJobInProgress}
                  >
                    <span className="intent-card__emoji" aria-hidden="true">🎯</span>
                    <span className="intent-card__label">Compare to a reference</span>
                    <span className="intent-card__desc">Match your performance against a reference track</span>
                  </button>
                </div>
              </div>
            ) : null}

            {/* Example + compare intent: show reference selector */}
            {selectedExampleId && analysisMode === "compare" && !referenceInfo && !sessionReport ? (
              <div className="step-panel__section">
                <ReferenceTrackSelector
                  exampleTracks={exampleTracks}
                  onReferenceReady={(refId, refInfo) => {
                    setReferenceId(refId);
                    setReferenceInfo(refInfo);
                  }}
                />
              </div>
            ) : null}
          </section>
        ) : null}

        {/* Live mic source: skip intent panel, go directly to reference selector */}
        {audioSource === "live" ? (
          <section
            className={`step-panel${audioSource ? " step-panel--visible" : ""}`}
            aria-label="Step 2: Select reference track for live comparison"
          >
            {!referenceInfo && !sessionReport ? (
              <>
                <p className="step-panel__note">
                  <strong>Live mic mode</strong> — comparison only. Select a reference track below then start your session.
                  For full formant analysis, upload a recording after the session.
                </p>
                <ReferenceTrackSelector
                  exampleTracks={exampleTracks}
                  onReferenceReady={(refId, refInfo) => {
                    setReferenceId(refId);
                    setReferenceInfo(refInfo);
                  }}
                />
              </>
            ) : null}
          </section>
        ) : null}

        {/* ── Step 3: Results region ────────────────────────────────────────── */}

        {/* Full analysis results (upload or example → analyze) */}
        {analysisMode === "analyze" && showStep3 ? (
          <section
            className={`step-panel step-panel--results${showStep3 ? " step-panel--visible" : ""}`}
            aria-label="Step 3: Analysis results"
          >
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
              audioSourceUrl={analysisAudioSourceUrl}
              audioSourceLabel={analysisAudioSourceLabel}
              jobId={jobId}
            />
            <div className="step-panel__actions">
              <button type="button" className="button" onClick={resetAll}>
                ↩ Analyze another
              </button>
            </div>
          </section>
        ) : null}

        {/* Comparison results: live session or upload/example compare path */}
        {analysisMode === "compare" && (referenceInfo || sessionReport) ? (
          <section
            className={`step-panel step-panel--results step-panel--visible`}
            aria-label="Step 3: Comparison session"
          >
            {sessionReport ? (
              <ComparisonResults
                sessionReport={sessionReport}
                onClose={() => {
                  setSessionReport(null);
                  setReferenceInfo(null);
                  setReferenceId(null);
                }}
                onStartNew={resetAll}
              />
            ) : referenceInfo ? (
              <LiveComparisonView
                referenceId={referenceId}
                referenceInfo={referenceInfo}
                onSessionComplete={setSessionReport}
                onClose={() => {
                  setReferenceInfo(null);
                  setReferenceId(null);
                }}
              />
            ) : null}
          </section>
        ) : null}
      </div>
    </main>
  );
}

export default App;
