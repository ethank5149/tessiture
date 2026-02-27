import { useCallback, useEffect, useRef, useState } from "react";
import AudioUploader from "./components/AudioUploader";
import AnalysisStatus from "./components/AnalysisStatus";
import AnalysisResults from "./components/AnalysisResults";
import {
  downloadJobResults,
  fetchJobResults,
  fetchJobStatus,
  submitAnalysisJob,
} from "./api";

const POLL_INTERVAL_MS = 2000;

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

  const pollingRef = useRef(null);

  const resetJob = useCallback(() => {
    setJobId(null);
    setStatus(null);
    setResults(null);
    setError(null);
  }, []);

  const submitJob = useCallback(async (file) => {
    setIsSubmitting(true);
    setError(null);
    setResults(null);
    setStatus(null);

    try {
      const response = await submitAnalysisJob(file);
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
        return await downloadJobResults(jobId, format);
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
      <header className="app-shell__header">
        <h1 className="app-shell__title">Tessitura Analysis</h1>
        <p className="app-shell__subtitle">
          Upload an audio file to generate tessitura insights and visualizations.
        </p>
      </header>

      <div className="app-shell__content">
        <AudioUploader
          onSubmit={submitJob}
          isSubmitting={isSubmitting}
          jobId={jobId}
          status={status}
          error={error}
        />

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
      </div>
    </main>
  );
}

export default App;
