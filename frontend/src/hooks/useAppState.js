/**
 * useAppState — Centralized state machine for the Tessiture app.
 *
 * Replaces 18+ individual useState calls in App.jsx with a single
 * useReducer whose dispatch actions make state transitions explicit
 * and prevent impossible states (e.g. audioSource=null + analysisMode='compare').
 *
 * Usage:
 *   const [state, dispatch] = useAppState();
 *   dispatch({ type: "SELECT_SOURCE", source: "upload" });
 */

import { useReducer } from "react";

// ── Initial state ────────────────────────────────────────────────────────────

export const initialState = {
  // Navigation axes
  audioSource: null,    // 'upload' | 'example' | 'live' | null
  analysisMode: null,   // 'analyze' | 'compare' | null

  // Job lifecycle
  jobId: null,
  status: null,         // normalized job status object
  results: null,
  error: null,
  isSubmitting: false,
  isPolling: false,
  isFetchingResults: false,

  // Source-specific transient state
  acceptedFile: null,
  selectedExampleId: null,
  audioType: "isolated",
  forceVocalSeparation: false,

  // Comparison state
  referenceId: null,
  referenceInfo: null,
  sessionReport: null,

  // Example gallery
  exampleTracks: [],
  isLoadingExamples: false,
  exampleError: null,
};

// ── Reducer ──────────────────────────────────────────────────────────────────

function appReducer(state, action) {
  switch (action.type) {
    // ── Navigation ─────────────────────────────────────────────

    case "SELECT_SOURCE": {
      if (action.source === state.audioSource) return state;
      return {
        ...initialState,
        audioSource: action.source,
        analysisMode: action.source === "live" ? "compare" : null,
        // Preserve gallery data across source changes
        exampleTracks: state.exampleTracks,
        isLoadingExamples: state.isLoadingExamples,
        exampleError: state.exampleError,
      };
    }

    case "SET_ANALYSIS_MODE":
      return { ...state, analysisMode: action.mode };

    case "RESET_ALL":
      return {
        ...initialState,
        exampleTracks: state.exampleTracks,
        isLoadingExamples: state.isLoadingExamples,
        exampleError: state.exampleError,
      };

    // ── Source-specific ────────────────────────────────────────

    case "FILE_ACCEPTED":
      return {
        ...state,
        acceptedFile: action.file,
        analysisMode: null,
        jobId: null,
        status: null,
        results: null,
        error: null,
      };

    case "EXAMPLE_SELECTED":
      return {
        ...state,
        selectedExampleId: action.exampleId,
        analysisMode: null,
        jobId: null,
        status: null,
        results: null,
        error: null,
      };

    case "SET_AUDIO_TYPE":
      return { ...state, audioType: action.audioType };

    case "SET_FORCE_VOCAL_SEPARATION":
      return { ...state, forceVocalSeparation: action.value };

    // ── Job lifecycle ─────────────────────────────────────────

    case "JOB_SUBMITTING":
      return {
        ...state,
        isSubmitting: true,
        error: null,
        results: null,
        status: null,
      };

    case "JOB_SUBMITTED":
      return {
        ...state,
        isSubmitting: false,
        jobId: action.jobId,
        status: action.status ?? null,
      };

    case "JOB_SUBMIT_FAILED":
      return {
        ...state,
        isSubmitting: false,
        error: action.error,
      };

    case "JOB_STATUS_UPDATE":
      return { ...state, status: action.status };

    case "POLLING_STARTED":
      return { ...state, isPolling: true };

    case "POLLING_STOPPED":
      return { ...state, isPolling: false };

    case "FETCHING_RESULTS":
      return { ...state, isFetchingResults: true, error: null };

    case "RESULTS_RECEIVED":
      return { ...state, isFetchingResults: false, results: action.results };

    case "RESULTS_FETCH_FAILED":
      return { ...state, isFetchingResults: false, error: action.error };

    case "SET_ERROR":
      return { ...state, error: action.error, isPolling: false };

    // ── Comparison ────────────────────────────────────────────

    case "REFERENCE_READY":
      return {
        ...state,
        referenceId: action.referenceId,
        referenceInfo: action.referenceInfo,
      };

    case "SESSION_REPORT_RECEIVED":
      return { ...state, sessionReport: action.report };

    case "CLEAR_COMPARISON":
      return {
        ...state,
        referenceId: null,
        referenceInfo: null,
        sessionReport: null,
      };

    // ── Example gallery ───────────────────────────────────────

    case "EXAMPLES_LOADING":
      return { ...state, isLoadingExamples: true, exampleError: null };

    case "EXAMPLES_LOADED":
      return { ...state, isLoadingExamples: false, exampleTracks: action.tracks };

    case "EXAMPLES_LOAD_FAILED":
      return { ...state, isLoadingExamples: false, exampleError: action.error };

    default:
      if (process.env.NODE_ENV !== "production") {
        console.warn(`[useAppState] Unknown action type: ${action.type}`);
      }
      return state;
  }
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export default function useAppState() {
  return useReducer(appReducer, initialState);
}

// Export the reducer for testing
export { appReducer };
