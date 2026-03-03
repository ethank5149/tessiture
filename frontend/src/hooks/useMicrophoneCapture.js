import { useCallback, useRef, useState } from "react";

/**
 * Custom hook for capturing microphone audio and producing Float32 PCM chunks.
 *
 * Note: Uses ScriptProcessorNode which is deprecated but broadly supported across
 * browsers. AudioWorkletNode is the modern replacement but has less compatibility.
 *
 * @param {object} options
 * @param {function} options.onChunk - Called with each Float32Array PCM chunk
 * @param {number} [options.sampleRate=44100] - Desired audio sample rate
 * @param {number} [options.chunkIntervalMs=100] - Target chunk interval in ms (informational;
 *   actual chunk size is determined by bufferSize=4096 at 44100 Hz ≈ 93ms)
 * @returns {{ start: function, stop: function, isCapturing: boolean, error: string|null }}
 */
const useMicrophoneCapture = ({ onChunk, sampleRate = 44100, chunkIntervalMs = 100 } = {}) => {
  const [isCapturing, setIsCapturing] = useState(false);
  const [error, setError] = useState(null);

  const audioContextRef = useRef(null);
  const streamRef = useRef(null);
  const sourceNodeRef = useRef(null);
  const processorNodeRef = useRef(null);

  // chunkIntervalMs is accepted for API compatibility but actual intervals are
  // governed by the bufferSize of the ScriptProcessorNode (4096 samples).
  void chunkIntervalMs;

  const stop = useCallback(() => {
    if (processorNodeRef.current) {
      processorNodeRef.current.onaudioprocess = null;
      processorNodeRef.current.disconnect();
      processorNodeRef.current = null;
    }
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    setIsCapturing(false);
  }, []);

  const start = useCallback(async () => {
    if (isCapturing) {
      return;
    }
    setError(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      streamRef.current = stream;

      // Create AudioContext at the desired sample rate
      const audioContext = new AudioContext({ sampleRate });
      audioContextRef.current = audioContext;

      // Create source node from the mic stream
      const sourceNode = audioContext.createMediaStreamSource(stream);
      sourceNodeRef.current = sourceNode;

      // ScriptProcessorNode: 4096 samples, 1 input channel, 1 output channel
      // Deprecated but broadly supported. At 44100 Hz, 4096 samples ≈ 93ms per chunk.
      const processorNode = audioContext.createScriptProcessor(4096, 1, 1);
      processorNodeRef.current = processorNode;

      processorNode.onaudioprocess = (event) => {
        const channelData = event.inputBuffer.getChannelData(0);
        // Copy to a new Float32Array so the buffer doesn't get reused
        const chunk = new Float32Array(channelData);
        if (typeof onChunk === "function") {
          onChunk(chunk);
        }
      };

      // Connect: source → processor → destination (required for onaudioprocess to fire)
      sourceNode.connect(processorNode);
      processorNode.connect(audioContext.destination);

      setIsCapturing(true);
    } catch (err) {
      let message = "Microphone access failed.";
      if (err?.name === "NotAllowedError" || err?.name === "PermissionDeniedError") {
        message = "Microphone permission denied. Please allow microphone access and try again.";
      } else if (err?.name === "NotFoundError" || err?.name === "DevicesNotFoundError") {
        message = "No microphone found. Please connect a microphone and try again.";
      } else if (err?.name === "NotReadableError" || err?.name === "TrackStartError") {
        message = "Microphone is already in use by another application.";
      } else if (err?.message) {
        message = err.message;
      }
      setError(message);
      // Clean up any partial state
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
        audioContextRef.current = null;
      }
    }
  }, [isCapturing, onChunk, sampleRate]);

  return { start, stop, isCapturing, error };
};

export default useMicrophoneCapture;
