import { useCallback, useEffect, useRef, useState } from "react";
import useComparisonWebSocket from "../hooks/useComparisonWebSocket";
import useMicrophoneCapture from "../hooks/useMicrophoneCapture";
import ComparisonMetricsPanel from "./ComparisonMetricsPanel";
import PitchMeter from "./PitchMeter";


/**
 * Main live comparison session view.
 *
 * @param {object} props
 * @param {string} props.referenceId - ID returned by /reference/* endpoints
 * @param {object} props.referenceInfo - { reference_id, duration_s, key, pitch_frame_count, note_event_count }
 * @param {function} props.onSessionComplete - Called with sessionReport when session ends
 * @param {function} props.onClose - Back/close callback
 */
const LiveComparisonView = ({ referenceId, referenceInfo, onSessionComplete, onClose }) => {
  const ws = useComparisonWebSocket();
  const audioRef = useRef(null);
  const [sessionActive, setSessionActive] = useState(false);
  const [sessionElapsedS, setSessionElapsedS] = useState(0);
  const elapsedTimerRef = useRef(null);

  // Forward mic chunks to WebSocket
  const handleChunk = useCallback(
    (chunk) => {
      ws.sendAudioChunk(chunk);
      if (audioRef.current) {
        ws.sendPlaybackSync(audioRef.current.currentTime);
      }
    },
    [ws]
  );

  const mic = useMicrophoneCapture({ onChunk: handleChunk, sampleRate: 44100 });

  // When session report arrives, signal completion
  useEffect(() => {
    if (ws.sessionReport && typeof onSessionComplete === "function") {
      onSessionComplete(ws.sessionReport);
    }
  }, [ws.sessionReport, onSessionComplete]);

  const handleStart = useCallback(async () => {
    ws.connect(referenceId);
    await mic.start();
    setSessionActive(true);
    setSessionElapsedS(0);
    elapsedTimerRef.current = setInterval(() => {
      setSessionElapsedS((s) => s + 1);
    }, 1000);
  }, [ws, mic, referenceId]);

  const handleStop = useCallback(() => {
    mic.stop();
    ws.sendSessionEnd();
    setSessionActive(false);
    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  }, [mic, ws]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      mic.stop();
      ws.disconnect();
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const deviation = ws.latestFeedback?.pitch_deviation_cents ?? null;
  const userNote = ws.latestFeedback?.user_note_name ?? null;

  // Reference audio: only available for example tracks (served at /examples/{filename})
  // Uploaded references do not have a direct audio playback URL yet.
  const referenceAudioUrl =
    referenceInfo?.filename
      ? `/examples/${encodeURIComponent(referenceInfo.filename)}`
      : null;

  const keyLabel = referenceInfo?.key ? ` · Key: ${referenceInfo.key}` : "";
  const noteCount = referenceInfo?.note_event_count ?? null;

  const combinedError = ws.error || mic.error;

  return (
    <section className="comparison-view" aria-label="Live comparison session">
      {/* Header */}
      <header className="live-session-header">
        <button
          type="button"
          className="button live-session-header__back"
          onClick={onClose}
          aria-label="Back to reference selection"
        >
          ← Back
        </button>
        <div className="live-session-header__info">
          <h2 className="live-session-header__title">Live Comparison</h2>
          <p className="live-session-header__meta">
            Reference{keyLabel}
            {noteCount !== null ? ` · ${noteCount} notes` : ""}
          </p>
        </div>
      </header>

      {/* Reference audio player (only for example tracks) */}
      {referenceAudioUrl ? (
        <div className="live-session-player">
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <audio
            ref={audioRef}
            src={referenceAudioUrl}
            controls
            className="live-session-player__audio"
            aria-label="Reference track audio"
          />
        </div>
      ) : (
        <p className="live-session-player--none">
          Audio playback is not available for uploaded references.
        </p>
      )}

      {/* Live pitch display — uses PitchMeter component */}
      <PitchMeter
        currentDeviation={deviation}
        userNote={userNote}
        referenceNote={ws.latestFeedback?.reference_note_name ?? null}
        accuracyRatio={ws.runningSummary?.pitch_accuracy_ratio ?? null}
        isVoiced={deviation !== null && userNote !== null}
      />

      {/* Metrics panel */}
      <ComparisonMetricsPanel
        runningSummary={ws.runningSummary}
        latestFeedback={ws.latestFeedback}
        sessionElapsedS={sessionElapsedS}
      />

      {/* Error banner */}
      {combinedError ? (
        <p className="live-session-error" role="alert">
          {combinedError}
        </p>
      ) : null}

      {/* Session controls */}
      <div className="live-session-controls">
        {!sessionActive ? (
          <button
            type="button"
            className="button button--primary live-session-controls__start"
            onClick={handleStart}
            disabled={mic.isCapturing || ws.isConnected}
            aria-label="Start comparison session"
          >
            ▶ Start Session
          </button>
        ) : (
          <button
            type="button"
            className="button button--danger live-session-controls__stop"
            onClick={handleStop}
            aria-label="Stop comparison session"
          >
            ■ Stop Session
          </button>
        )}
        {ws.isConnected ? (
          <span className="live-session-controls__status" role="status">
            🔴 Live
          </span>
        ) : null}
      </div>
    </section>
  );
};

export default LiveComparisonView;
