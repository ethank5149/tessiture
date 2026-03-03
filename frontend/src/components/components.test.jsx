import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import {
  fetchExampleTracks,
  fetchJobResults,
  fetchJobStatus,
  normalizeJobStatus,
  submitAnalysisJob,
  submitExampleAnalysisJob,
} from "../api";
import AnalysisResults from "./AnalysisResults";
import AnalysisStatus from "./AnalysisStatus";
import AudioUploader from "./AudioUploader";
import ComparisonMetricsPanel from "./ComparisonMetricsPanel";
import ComparisonResults from "./ComparisonResults";
import ExampleGallery from "./ExampleGallery";
import ReferenceTrackSelector from "./ReferenceTrackSelector";

vi.mock("../api", () => ({
  downloadJobResults: vi.fn(),
  fetchExampleTracks: vi.fn(),
  fetchJobResults: vi.fn(),
  fetchJobStatus: vi.fn(),
  normalizeJobStatus: vi.fn((payload) => payload),
  submitAnalysisJob: vi.fn(),
  submitExampleAnalysisJob: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("AudioUploader", () => {
  it("submits a selected audio file", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue({ job_id: "job-1" });

    render(<AudioUploader onSubmit={onSubmit} isSubmitting={false} />);

    const input = screen.getByLabelText("Audio file");
    expect(input).toHaveAttribute("accept", "audio/*,.wav,.mp3,.flac,.m4a,.opus");
    expect(screen.getByText(/Supported formats:/)).toHaveTextContent("Opus");

    const file = new File(["wave"], "sample.wav", { type: "audio/wav" });

    await user.upload(input, file);
    await user.click(screen.getByRole("button", { name: "Start analysis" }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith(file);
  });
});

describe("ExampleGallery", () => {
  it("renders example cards and emits selected example object", async () => {
    const user = userEvent.setup();
    const onSelectExample = vi.fn().mockResolvedValue({ job_id: "job-2" });
    const demoExample = {
      id: "demo-1",
      display_name: "Demo Example",
      artist: "Demo Artist",
      album: "Demo Album",
      filename: "demo.opus",
      content_type: "audio/opus",
    };

    render(
      <ExampleGallery
        examples={[demoExample]}
        isLoading={false}
        onSelectExample={onSelectExample}
        selectedExampleId={null}
        isSelecting={false}
      />
    );

    expect(screen.getByText("Demo Example")).toBeInTheDocument();
    expect(screen.getByText("Demo Artist")).toBeInTheDocument();
    expect(screen.getByText("Demo Album")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Select example track: Demo Example by Demo Artist" }));

    expect(onSelectExample).toHaveBeenCalledTimes(1);
    expect(onSelectExample).toHaveBeenCalledWith(demoExample);
  });

  it("marks selected example card with pressed state", () => {
    render(
      <ExampleGallery
        examples={[
          {
            id: "demo-1",
            display_name: "Demo Example",
            artist: "Demo Artist",
          },
        ]}
        isLoading={false}
        onSelectExample={vi.fn()}
        selectedExampleId="demo-1"
        isSelecting={false}
      />
    );

    expect(
      screen.getByRole("button", { name: "Select example track: Demo Example by Demo Artist" })
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("shows loading state", () => {
    render(<ExampleGallery examples={[]} isLoading onSelectExample={vi.fn()} />);
    expect(screen.getByText("Loading examples…")).toBeInTheDocument();
  });
});

describe("AnalysisStatus", () => {
  it("shows polling activity when requested", () => {
    render(
      <AnalysisStatus
        jobId="job-1"
        status={{ status: "processing" }}
        isPolling
        isFetchingResults={false}
      />
    );

    expect(screen.getByText("Polling for updates…")).toBeInTheDocument();
    expect(screen.getByText("processing", { selector: ".status__value" })).toBeInTheDocument();
  });

  it("shows idle state without a progress bar before any job is submitted", () => {
    render(<AnalysisStatus jobId={null} status={null} isPolling={false} isFetchingResults={false} />);

    expect(screen.getByText("No active job")).toBeInTheDocument();
    expect(screen.getByText("idle", { selector: ".status__value" })).toBeInTheDocument();
    expect(screen.getByText("not started")).toBeInTheDocument();
    expect(screen.queryByLabelText("Progress")).not.toBeInTheDocument();
    expect(screen.getByText("Progress will appear after you submit a job.")).toBeInTheDocument();
  });

  it("shows stage, progress bar, and polling activity", () => {
    render(
      <AnalysisStatus
        jobId="job-1"
        status={{
          status: "processing",
          stage: "pitch_extraction",
          progress: 42,
          message: "Extracting pitch and harmonic tracks.",
        }}
        isPolling
        isFetchingResults={false}
      />
    );

    expect(screen.getByText("processing", { selector: ".status__value" })).toBeInTheDocument();
    expect(screen.getByText("pitch extraction")).toBeInTheDocument();
    expect(screen.getByText("Extracting pitch and harmonic tracks.")).toBeInTheDocument();
    expect(screen.getByText("Polling for updates…")).toBeInTheDocument();
    expect(screen.getByLabelText("Progress")).toHaveAttribute("value", "42");
    expect(screen.getByText("42%", { selector: ".status__progress-value" })).toBeInTheDocument();
  });
});

describe("API status normalization", () => {
  it("normalizes progress, stage, and backward-compatible detail fields", async () => {
    const actualApi = await vi.importActual("../api");

    const normalized = actualApi.normalizeJobStatus({
      status: "processing",
      progress: "61.2",
      stage: "advanced_analysis",
      message: "Running advanced analysis.",
    });

    expect(normalized.status).toBe("processing");
    expect(normalized.progress).toBe(61);
    expect(normalized.stage).toBe("advanced_analysis");
    expect(normalized.message).toBe("Running advanced analysis.");
    expect(normalized.detail).toBe("Running advanced analysis.");
  });

  it("fills defaults for missing stage and terminal progress", async () => {
    const actualApi = await vi.importActual("../api");

    const normalized = actualApi.normalizeJobStatus({
      status: "completed",
      detail: "Analysis completed.",
    });

    expect(normalized.status).toBe("completed");
    expect(normalized.progress).toBe(100);
    expect(normalized.stage).toBe("completed");
    expect(normalized.message).toBe("Analysis completed.");
    expect(normalized.detail).toBe("Analysis completed.");
  });

  it("normalizes inferential statistics shape for analysis results", async () => {
    const actualApi = await vi.importActual("../api");

    const normalized = actualApi.normalizeAnalysisResult({
      summary: {
        f0_min: 220.0,
        f0_max: 440.0,
        f0_min_note: "A3",
        f0_max_note: "A4",
        tessitura_range: [57.0, 69.0],
        tessitura_range_notes: ["A3", "A4"],
      },
      inferential_statistics: {
        preset: "casual",
        confidence_level: 0.95,
        metrics: {
          f0_mean_hz: {
            estimate: 220.1,
            estimate_note: "A3",
            confidence_interval: {
              low: 210.2,
              high: 230.3,
              low_note: "G#3",
              high_note: "A#3",
              level: 0.95,
            },
            p_value: 0.012,
            n_samples: 120,
          },
        },
      },
    });

    expect(normalized.inferential_statistics).toBeDefined();
    expect(normalized.inferential_statistics.metrics).toBeDefined();
    expect(normalized.inferential_statistics.metrics.f0_mean_hz.estimate).toBe(220.1);
    expect(normalized.inferential_statistics.metrics.f0_mean_hz.estimate_note).toBe("A3");
    expect(normalized.inferential_statistics.metrics.f0_mean_hz.confidence_interval.low_note).toBe("G#3");
    expect(normalized.inferential_statistics.metrics.f0_mean_hz.confidence_interval.high_note).toBe("A#3");
    expect(normalized.summary.f0_min_note).toBe("A3");
    expect(normalized.summary.f0_max_note).toBe("A4");
    expect(normalized.summary.tessitura_range_notes).toEqual(["A3", "A4"]);
  });

  it("preserves nested calibration summary from analysis payload", async () => {
    const actualApi = await vi.importActual("../api");

    const normalized = actualApi.normalizeAnalysisResult({
      analysis: {
        summary: {
          f0_min: 220.0,
          f0_max: 440.0,
        },
        calibration: {
          summary: {
            reference_sample_count: 5,
            voiced_frame_count: 12,
          },
        },
      },
    });

    expect(normalized.calibration).toBeDefined();
    expect(normalized.calibration.summary.reference_sample_count).toBe(5);
    expect(normalized.calibration.summary.voiced_frame_count).toBe(12);
  });
});

describe("AnalysisResults", () => {
  it("renders summary values and export controls", () => {
    const results = {
      metadata: { duration_seconds: 10.0 },
      summary: {
        duration_seconds: 10.0,
        f0_min: 220.0,
        f0_max: 440.0,
        f0_min_note: "A3",
        f0_max_note: "A4",
        tessitura_range: [57.0, 69.0],
        tessitura_range_notes: ["A3", "A4"],
        confidence: 0.92,
      },
      inferential_statistics: {
        preset: "casual",
        confidence_level: 0.95,
        metrics: {
          f0_mean_hz: {
            estimate: 221.4,
            estimate_note: "A3",
            confidence_interval: {
              low: 215.2,
              high: 228.7,
              low_note: "G#3",
              high_note: "A#3",
              level: 0.95,
            },
            p_value: 0.008,
            n_samples: 140,
          },
          tessitura_center_midi: {
            estimate: 57.0,
            estimate_note: "A3",
            confidence_interval: {
              low: 56.5,
              high: 57.5,
              low_note: "G#3",
              high_note: "A#3",
              level: 0.95,
            },
            p_value: 0.011,
            n_samples: 140,
          },
        },
      },
      pitch: {
        frames: [
          { time: 0.0, f0: 220.0 },
          { time: 1.0, f0: 440.0 },
        ],
      },
      tessitura: {
        histogram: [0.2, 0.5, 0.3],
      },
    };

    render(
      <AnalysisResults
        results={results}
        status={{ status: "completed" }}
        isFetchingResults={false}
        onDownloadCsv={vi.fn()}
        onDownloadJson={vi.fn()}
        onDownloadPdf={vi.fn()}
      />
    );

    expect(screen.getByText("Analysis results")).toBeInTheDocument();
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("Visualizations")).toBeInTheDocument();
    expect(screen.getByText("completed", { selector: ".results__status" })).toBeInTheDocument();
    expect(screen.getByText("10.00")).toBeInTheDocument();
    expect(screen.getByText("220.00 (A3)")).toBeInTheDocument();
    expect(screen.getByText("440.00 (A4)")).toBeInTheDocument();
    expect(screen.getByText("57.00 to 69.00 (A3 to A4)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download JSON" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeInTheDocument();
    expect(screen.getByText("How consistent each metric is (inferential statistics)")).toBeInTheDocument();
    expect(screen.getByText("F0 Mean Hz")).toBeInTheDocument();
    expect(screen.getByText("Tessitura Center Midi")).toBeInTheDocument();
    expect(screen.getByText("221.40 (A3)")).toBeInTheDocument();
    expect(screen.getByText("[215.20, 228.70] (G#3 to A#3)")).toBeInTheDocument();
    expect(screen.getByText("57.00 (A3)")).toBeInTheDocument();
    expect(screen.getByText("[56.50, 57.50] (G#3 to A#3)")).toBeInTheDocument();
    expect(screen.getByText("0.008")).toBeInTheDocument();
  });

  it("renders the coaching trio with clear chart purposes and a populated 2D heatmap", () => {
    const results = {
      metadata: { duration_seconds: 12.3 },
      summary: {
        duration_seconds: 12.3,
      },
      pitch: {
        frames: [
          { time: 0.0, midi: 60, confidence: 0.6 },
          { time: 0.5, midi: 62, confidence: 0.9 },
          { time: 1.0, midi: 64, confidence: 0.8 },
        ],
      },
      tessitura: {
        histogram: [0.3, 0.7, 0.5],
      },
    };

    render(
      <AnalysisResults
        results={results}
        status={{ status: "completed" }}
        isFetchingResults={false}
        onDownloadCsv={vi.fn()}
        onDownloadJson={vi.fn()}
        onDownloadPdf={vi.fn()}
      />
    );

    expect(screen.getByText("Piano roll")).toBeInTheDocument();
    expect(screen.getByText("Session distribution summary (1D tessitura)")).toBeInTheDocument();
    expect(screen.getByText("Time × pitch heatmap (2D)")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Use this coaching trio together: detailed note trace (piano roll), session distribution summary (1D tessitura), and a 2D time × pitch heatmap."
      )
    ).toBeInTheDocument();

    const heatmap = screen.getByLabelText("Time by pitch density heatmap");
    expect(heatmap).toBeInTheDocument();
    const heatmapSvg = heatmap.querySelector("svg");
    expect(heatmapSvg).not.toBeNull();
    expect(heatmapSvg.querySelectorAll("rect").length).toBeGreaterThan(1);

    expect(screen.getByText("Time span: 1.0s")).toBeInTheDocument();
    expect(screen.getByText("Pitch span: 60.0–64.0 MIDI")).toBeInTheDocument();
  });

  it("shows a 2D heatmap placeholder when no pitch-frame data is available", () => {
    const results = {
      summary: {
        duration_seconds: 8.0,
      },
      tessitura: {
        histogram: [0.2, 0.4, 0.6],
      },
    };

    render(
      <AnalysisResults
        results={results}
        status={{ status: "completed" }}
        isFetchingResults={false}
        onDownloadCsv={vi.fn()}
        onDownloadJson={vi.fn()}
        onDownloadPdf={vi.fn()}
      />
    );

    expect(screen.getByText("Time × pitch heatmap (2D)")).toBeInTheDocument();
    expect(
      screen.getByText("No pitch frame data available for the 2D time × pitch heatmap.")
    ).toBeInTheDocument();
  });

  it("renders a dedicated reference calibration tab and allows selecting it", async () => {
    const user = userEvent.setup();
    const results = {
      summary: {
        duration_seconds: 10.0,
        f0_min: 220.0,
        f0_max: 440.0,
      },
      pitch: {
        frames: [{ time: 0.0, f0: 220.0 }],
      },
      tessitura: {
        histogram: [0.2, 0.5, 0.3],
      },
      calibration: {
        summary: {
          reference_sample_count: 5,
          reference_frequency_min_hz: 100.0,
          reference_frequency_max_hz: 300.0,
          frequency_bin_count: 2,
          populated_frequency_bin_count: 2,
          mean_pitch_bias_cents: -0.2,
          max_abs_pitch_bias_cents: 2.0,
          mean_pitch_variance_cents2: 6.0,
          pitch_error_mean_cents: 0.5,
          pitch_error_std_cents: 0.8165,
          mean_frame_uncertainty_midi: 0.15,
          voiced_frame_count: 5,
        },
      },
    };

    render(
      <AnalysisResults
        results={results}
        status={{ status: "completed" }}
        isFetchingResults={false}
        onDownloadCsv={vi.fn()}
        onDownloadJson={vi.fn()}
        onDownloadPdf={vi.fn()}
      />
    );

    const analysisTab = screen.getByRole("tab", { name: "General analysis" });
    const calibrationTab = screen.getByRole("tab", { name: "Reference calibration" });

    expect(analysisTab).toHaveAttribute("aria-selected", "true");
    expect(calibrationTab).toHaveAttribute("aria-selected", "false");

    await user.click(calibrationTab);

    const referenceSamplesItem = screen.getByText("Reference samples (N)").closest(".summary-list__item");

    expect(calibrationTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Reference calibration summary" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "These metrics come from reference dataset calibration (ground-truth generated data) and are not derived from uploaded or example track runtime behavior."
      )
    ).toBeInTheDocument();
    expect(screen.getByText("100.00 to 300.00")).toBeInTheDocument();
    expect(screen.getByText("-0.20")).toBeInTheDocument();
    expect(referenceSamplesItem).not.toBeNull();
    expect(within(referenceSamplesItem).getByText("5")).toBeInTheDocument();
  });

  it("renders reference calibration values from analysis.calibration.summary payload shape", async () => {
    const user = userEvent.setup();
    const actualApi = await vi.importActual("../api");
    const normalized = actualApi.normalizeAnalysisResult({
      analysis: {
        summary: {
          duration_seconds: 8,
        },
        calibration: {
          summary: {
            reference_sample_count: 7,
            voiced_frame_count: 9,
          },
        },
      },
    });

    render(
      <AnalysisResults
        results={normalized}
        status={{ status: "completed" }}
        isFetchingResults={false}
        onDownloadCsv={vi.fn()}
        onDownloadJson={vi.fn()}
        onDownloadPdf={vi.fn()}
      />
    );

    await user.click(screen.getByRole("tab", { name: "Reference calibration" }));

    const sampleCountItem = screen.getByText("Reference samples (N)").closest(".summary-list__item");
    const voicedFramesItem = screen.getByText("Voiced frame count").closest(".summary-list__item");

    expect(sampleCountItem).not.toBeNull();
    expect(voicedFramesItem).not.toBeNull();
    expect(within(sampleCountItem).getByText("7")).toBeInTheDocument();
    expect(within(voicedFramesItem).getByText("9")).toBeInTheDocument();
  });

  it("handles partial calibration summary values gracefully", async () => {
    const user = userEvent.setup();
    const results = {
      summary: {
        duration_seconds: 7.0,
      },
      calibration: {
        summary: {
          reference_sample_count: 2,
          voiced_frame_count: null,
        },
      },
    };

    render(
      <AnalysisResults
        results={results}
        status={{ status: "completed" }}
        isFetchingResults={false}
        onDownloadCsv={vi.fn()}
        onDownloadJson={vi.fn()}
        onDownloadPdf={vi.fn()}
      />
    );

    await user.click(screen.getByRole("tab", { name: "Reference calibration" }));

    const sampleCountItem = screen.getByText("Reference samples (N)").closest(".summary-list__item");
    const frequencyRangeItem = screen
      .getByText("Reference frequency range (Hz)")
      .closest(".summary-list__item");
    const voicedFramesItem = screen.getByText("Voiced frame count").closest(".summary-list__item");

    expect(sampleCountItem).not.toBeNull();
    expect(frequencyRangeItem).not.toBeNull();
    expect(voicedFramesItem).not.toBeNull();

    expect(within(sampleCountItem).getByText("2")).toBeInTheDocument();
    expect(within(frequencyRangeItem).getByText("—")).toBeInTheDocument();
    expect(within(voicedFramesItem).getByText("—")).toBeInTheDocument();
  });
});

describe("App example gallery wiring", () => {
  it("uses relative example API paths compatible with Vite dev proxy", async () => {
    normalizeJobStatus.mockImplementation((payload) => payload);
    const actualApi = await vi.importActual("../api");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ examples: [] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job_id: "job-demo" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      );

    vi.stubGlobal("fetch", fetchMock);

    await actualApi.fetchExampleTracks();
    await actualApi.submitExampleAnalysisJob("demo-1");

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/examples", { method: "GET" });
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/analyze/example?example_id=demo-1", {
      method: "POST",
    });
  });

  it("uses gallery as selector-only input and runs processing in main tab", async () => {
    const user = userEvent.setup();

    fetchExampleTracks.mockResolvedValue([
      {
        id: "demo-1",
        display_name: "Demo Example",
        artist: "Demo Artist",
      },
    ]);
    submitExampleAnalysisJob.mockResolvedValue({ job_id: "job-demo" });
    fetchJobStatus.mockResolvedValue({ status: "completed" });
    fetchJobResults.mockResolvedValue({
      metadata: { duration_seconds: 10 },
      summary: { duration_seconds: 10, confidence: 0.9 },
      pitch: { frames: [] },
      tessitura: {},
    });

    render(<App />);

    await user.click(screen.getByRole("tab", { name: "Example gallery" }));

    expect(screen.queryByRole("heading", { name: "Analysis status" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Analysis results" })).not.toBeInTheDocument();

    const selectButton = await screen.findByRole("button", {
      name: "Select example track: Demo Example by Demo Artist",
    });
    await user.click(selectButton);

    await waitFor(() => {
      expect(submitExampleAnalysisJob).toHaveBeenCalledWith("demo-1");
    });

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Upload audio" })).toHaveAttribute("aria-selected", "true");
    });

    expect(screen.queryByRole("heading", { name: "Example gallery" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Upload audio" })).toBeInTheDocument();
  });

  it("stops polling after first status failure", async () => {
    vi.useFakeTimers();

    fetchExampleTracks.mockResolvedValue([]);
    submitAnalysisJob.mockResolvedValue({ job_id: "job-fail" });
    fetchJobStatus.mockRejectedValue(new Error("status down"));

    render(<App />);

    const input = screen.getByLabelText("Audio file");
    const file = new File(["wave"], "sample.wav", { type: "audio/wav" });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Start analysis" }));

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(fetchJobStatus).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText("status down").length).toBeGreaterThan(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(fetchJobStatus).toHaveBeenCalledTimes(1);
  });

  it("shows reference calibration tab in the upload workflow after results are available", async () => {
    fetchExampleTracks.mockResolvedValue([]);
    submitAnalysisJob.mockResolvedValue({ job_id: "job-calibration" });
    fetchJobStatus.mockResolvedValue({ status: "completed" });
    fetchJobResults.mockResolvedValue({
      summary: {
        duration_seconds: 10,
      },
      pitch: {
        frames: [{ time: 0, f0: 220 }],
      },
      tessitura: {
        histogram: [0.5],
      },
      calibration: {
        summary: {
          reference_sample_count: 3,
          voiced_frame_count: 4,
        },
      },
    });

    render(<App />);

    const input = screen.getByLabelText("Audio file");
    const file = new File(["wave"], "sample.wav", { type: "audio/wav" });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Start analysis" }));

    await waitFor(() => {
      expect(fetchJobResults).toHaveBeenCalledWith("job-calibration", "json");
    });

    const calibrationTab = await screen.findByRole("tab", { name: "Reference calibration" });
    fireEvent.click(calibrationTab);

    expect(screen.getByRole("heading", { name: "Reference calibration summary" })).toBeInTheDocument();
  });

  it("renders release metadata when VITE_APP_VERSION is semantic", () => {
    fetchExampleTracks.mockResolvedValue([]);
    vi.stubEnv("VITE_APP_VERSION", "1.2.3");

    render(<App />);

    expect(screen.getByText("Release 1.2.3")).toBeInTheDocument();
  });

  it("hides release metadata when VITE_APP_VERSION is missing or non-semantic", () => {
    fetchExampleTracks.mockResolvedValue([]);
    vi.stubEnv("VITE_APP_VERSION", "build-main");

    render(<App />);

    expect(screen.queryByText(/^Release\s+/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Minimal mock session report used across ComparisonResults tests
// ---------------------------------------------------------------------------
const mockSessionReport = {
  session_id: "sess-001",
  reference_id: "ref-001",
  duration_s: 60.0,
  comparison: {
    pitch: {
      frame_deviations_cents: [],
      frame_times_s: [],
      mean_absolute_pitch_error_cents: 0,
      pitch_accuracy_ratio: 1.0,
      pitch_bias_cents: 0,
      pitch_stability_cents: 0,
      voiced_frame_count: 0,
    },
    rhythm: {
      onset_deviations_ms: [],
      duration_ratios: [],
      mean_onset_error_ms: 0,
      rhythmic_consistency_ms: 0,
      note_hit_rate: 0,
      matched_note_count: 0,
      reference_note_count: 0,
    },
    range: {
      user_range_min_midi: null,
      user_range_max_midi: null,
      reference_range_min_midi: null,
      reference_range_max_midi: null,
      range_overlap_semitones: 0,
      range_coverage_ratio: 0,
      tessitura_center_offset_semitones: null,
      out_of_range_note_fraction: 0,
      strain_zone_incursion_ratio: 0,
    },
    formants: {
      mean_f1_deviation_hz: null,
      mean_f2_deviation_hz: null,
      spectral_centroid_deviation_hz: null,
      formant_data_available: false,
    },
  },
};

// ---------------------------------------------------------------------------
// ReferenceTrackSelector tests
// ---------------------------------------------------------------------------
describe("ReferenceTrackSelector", () => {
  it("renders reference selector with tabs", () => {
    render(
      <ReferenceTrackSelector
        exampleTracks={[]}
        onReferenceReady={vi.fn()}
        isLoading={false}
        error={null}
      />
    );

    expect(screen.getByRole("tab", { name: "From Library" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Upload Reference" })).toBeInTheDocument();
  });

  it("renders example tracks in library tab", () => {
    const tracks = [
      { id: "t1", display_name: "Track One", artist: "Artist A" },
      { id: "t2", display_name: "Track Two", artist: "Artist B" },
    ];

    render(
      <ReferenceTrackSelector
        exampleTracks={tracks}
        onReferenceReady={vi.fn()}
        isLoading={false}
        error={null}
      />
    );

    expect(screen.getByText("Track One")).toBeInTheDocument();
    expect(screen.getByText("Track Two")).toBeInTheDocument();
  });

  it("renders loading state", () => {
    render(
      <ReferenceTrackSelector
        exampleTracks={[]}
        onReferenceReady={vi.fn()}
        isLoading={true}
        error={null}
      />
    );

    expect(screen.getByText(/Preparing reference track/i)).toBeInTheDocument();
  });

  it("renders error message", () => {
    render(
      <ReferenceTrackSelector
        exampleTracks={[]}
        onReferenceReady={vi.fn()}
        isLoading={false}
        error="Test error"
      />
    );

    expect(screen.getByText("Test error")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ComparisonMetricsPanel tests
// ---------------------------------------------------------------------------
describe("ComparisonMetricsPanel", () => {
  it("renders without data", () => {
    expect(() =>
      render(
        <ComparisonMetricsPanel
          runningSummary={null}
          latestFeedback={null}
          sessionElapsedS={0}
        />
      )
    ).not.toThrow();
  });

  it("renders running summary metrics", () => {
    const runningSummary = {
      session_elapsed_s: 30,
      voiced_chunk_count: 20,
      total_chunk_count: 25,
      mean_pitch_deviation_cents: 12.5,
      pitch_accuracy_ratio: 0.84,
    };

    render(
      <ComparisonMetricsPanel
        runningSummary={runningSummary}
        latestFeedback={null}
        sessionElapsedS={30}
      />
    );

    // pitch_accuracy_ratio 0.84 → "84%"
    expect(screen.getByText("84%")).toBeInTheDocument();
  });

  it("renders current note from feedback", () => {
    const latestFeedback = {
      user_note_name: "A4",
      reference_note_name: "A4",
      pitch_deviation_cents: -5.2,
      in_tune: true,
    };

    render(
      <ComparisonMetricsPanel
        runningSummary={null}
        latestFeedback={latestFeedback}
        sessionElapsedS={0}
      />
    );

    // "A4" should appear as the user note (and reference note)
    const a4Elements = screen.getAllByText("A4");
    expect(a4Elements.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// ComparisonResults tests
// ---------------------------------------------------------------------------
describe("ComparisonResults", () => {
  it("renders session complete", () => {
    render(
      <ComparisonResults
        sessionReport={mockSessionReport}
        onClose={vi.fn()}
        onStartNew={vi.fn()}
      />
    );

    expect(screen.getByRole("heading", { name: "Session Complete" })).toBeInTheDocument();
  });

  it("calls onClose when close button clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <ComparisonResults
        sessionReport={mockSessionReport}
        onClose={onClose}
        onStartNew={vi.fn()}
      />
    );

    await user.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onStartNew when start new session clicked", async () => {
    const user = userEvent.setup();
    const onStartNew = vi.fn();

    render(
      <ComparisonResults
        sessionReport={mockSessionReport}
        onClose={vi.fn()}
        onStartNew={onStartNew}
      />
    );

    await user.click(screen.getByRole("button", { name: /start new session/i }));
    expect(onStartNew).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// api.js comparison function export tests
// ---------------------------------------------------------------------------
describe("api.js comparison function exports", () => {
  it("prepareReferenceFromExample is exported", async () => {
    const actualApi = await vi.importActual("../api");
    expect(actualApi.prepareReferenceFromExample).toBeDefined();
  });

  it("prepareReferenceFromUpload is exported", async () => {
    const actualApi = await vi.importActual("../api");
    expect(actualApi.prepareReferenceFromUpload).toBeDefined();
  });
});
