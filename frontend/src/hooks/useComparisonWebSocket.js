import { useCallback, useRef, useState } from "react";

/**
 * Build a WebSocket base URL from the same env variable used in api.js.
 * Converts http:// → ws:// and https:// → wss://.
 * Falls back to current window host if no env var is set.
 */
const buildWsBaseUrl = () => {
  const apiBase =
    (typeof import.meta !== "undefined" &&
      import.meta.env &&
      import.meta.env.VITE_API_BASE_URL) ||
    "";

  if (apiBase) {
    return apiBase.replace(/\/$/, "").replace(/^http(s?):\/\//, "ws$1://");
  }

  // Default: derive from current window location
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}`;
  }

  return "";
};

/**
 * Custom hook managing the WebSocket connection for a live comparison session.
 *
 * @returns {{
 *   connect: (referenceId: string) => void,
 *   disconnect: () => void,
 *   sendAudioChunk: (chunk: Float32Array) => void,
 *   sendPlaybackSync: (positionS: number) => void,
 *   sendSessionEnd: () => void,
 *   isConnected: boolean,
 *   sessionInfo: object|null,
 *   latestFeedback: object|null,
 *   runningSummary: object|null,
 *   sessionReport: object|null,
 *   error: string|null,
 * }}
 */
const useComparisonWebSocket = () => {
  const wsRef = useRef(null);

  const [isConnected, setIsConnected] = useState(false);
  const [sessionInfo, setSessionInfo] = useState(null);
  const [latestFeedback, setLatestFeedback] = useState(null);
  const [runningSummary, setRunningSummary] = useState(null);
  const [sessionReport, setSessionReport] = useState(null);
  const [error, setError] = useState(null);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      // Remove event handlers before closing to prevent spurious error state
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setSessionInfo(null);
    setLatestFeedback(null);
    setRunningSummary(null);
    setSessionReport(null);
    setError(null);
  }, []);

  const connect = useCallback(
    (referenceId) => {
      // Close any existing connection first
      if (wsRef.current) {
        wsRef.current.onmessage = null;
        wsRef.current.onerror = null;
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }

      // Reset state for new session
      setIsConnected(false);
      setSessionInfo(null);
      setLatestFeedback(null);
      setRunningSummary(null);
      setSessionReport(null);
      setError(null);

      const wsBase = buildWsBaseUrl();
      const url = `${wsBase}/compare/live?reference_id=${encodeURIComponent(referenceId)}`;

      let ws;
      try {
        ws = new WebSocket(url);
      } catch (err) {
        setError(`Failed to open WebSocket: ${err?.message ?? String(err)}`);
        return;
      }

      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setError(null);
      };

      ws.onmessage = (event) => {
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          // Ignore non-JSON frames (shouldn't happen from our backend)
          return;
        }

        switch (data.type) {
          case "session_start":
            setSessionInfo({
              session_id: data.session_id,
              reference_id: data.reference_id,
              reference_duration_s: data.reference_duration_s,
              reference_note_count: data.reference_note_count,
            });
            break;
          case "chunk_feedback":
            setLatestFeedback(data);
            break;
          case "running_summary":
            setRunningSummary(data);
            break;
          case "session_report":
            setSessionReport(data);
            break;
          default:
            // Unknown message type; ignore gracefully
            break;
        }
      };

      ws.onerror = () => {
        setError("WebSocket connection error. Check your network and backend.");
        setIsConnected(false);
      };

      ws.onclose = (event) => {
        setIsConnected(false);
        if (!event.wasClean) {
          setError(`Connection closed unexpectedly (code ${event.code}).`);
        }
        wsRef.current = null;
      };
    },
    []
  );

  const sendAudioChunk = useCallback((float32Array) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(float32Array.buffer);
    }
  }, []);

  const sendPlaybackSync = useCallback((positionS) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "playback_sync", position_s: positionS }));
    }
  }, []);

  const sendSessionEnd = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "session_end" }));
    }
  }, []);

  return {
    connect,
    disconnect,
    sendAudioChunk,
    sendPlaybackSync,
    sendSessionEnd,
    isConnected,
    sessionInfo,
    latestFeedback,
    runningSummary,
    sessionReport,
    error,
  };
};

export default useComparisonWebSocket;
