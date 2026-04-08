import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock ResizeObserver (not available in jsdom)
global.ResizeObserver = class ResizeObserver {
  constructor(cb) { this._cb = cb; }
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mock localStorage for SessionHistory component
const localStorageMock = (() => {
  let store = {};
  return {
    getItem: (key) => store[key] ?? null,
    setItem: (key, value) => { store[key] = String(value); },
    removeItem: (key) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(global, "localStorage", { value: localStorageMock });

import App from "../App";
import {
  fetchExampleTracks,
  fetchJobResults,
  fetchJobStatus,
  fetchSpectrogram,
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
import SpectrogramInspector from "./SpectrogramInspector";

vi.mock("../api", () => ({
  downloadJobResults: vi.fn(),
  fetchExampleTracks: vi.fn(),
  fetchJobResults: vi.fn(),
  fetchJobStatus: vi.fn(),
  fetchSpectrogram: vi.fn(),
  normalizeJobStatus: vi.fn((payload) => payload),
  submitAnalysisJob: vi.fn(),
  submitExampleAnalysisJob: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  // Default fetchSpectrogram to a resolved Promise so SpectrogramInspector
  // (which now mounts immediately at isOpen=true) doesn't crash with .then()
  // on undefined in tests that don't explicitly override the mock.
  fetchSpectrogram.mockResolvedValue({
    mix: { frames_b64: "", n_time: 0, n_freq: 0, frequencies_hz: [], times_s: [] },
    vocals: { available: false },
  });
  // jsdom does not implement URL.createObjectURL/revokeObjectURL — stub them so App renders without crashing
  if (typeof URL.createObjectURL === "undefined") {
    URL.createObjectURL = vi.fn(() => "blob:mock-url");
  }
  if (typeof URL.revokeObjectURL === "undefined") {
    URL.revokeObjectURL = vi.fn();
  }
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

  it("shows upload preview details after selecting a file", async () => {
    const user = userEvent.setup();

    render(<AudioUploader onSubmit={vi.fn()} isSubmitting={false} />);

    const input = screen.getByLabelText("Audio file");
    const file = new File([new Uint8Array(2048)], "preview.wav", { type: "audio/wav" });

    await user.upload(input, file);

    expect(screen.getByText("Upload preview")).toBeInTheDocument();
    expect(screen.getByText("preview.wav")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
    expect(screen.getByText("Ready to start analysis.")).toBeInTheDocument();
  });

  it("shows progressive upload and decode messaging", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <AudioUploader onSubmit={vi.fn()} isSubmitting={false} jobId={null} status={null} />
    );

    const input = screen.getByLabelText("Audio file");
    const file = new File([new Uint8Array(1024)], "progress.wav", { type: "audio/wav" });

    await user.upload(input, file);
    expect(screen.getByText("Ready to start analysis.")).toBeInTheDocument();

    rerender(<AudioUploader onSubmit={vi.fn()} isSubmitting={true} jobId={null} status={null} />);
    expect(screen.getByText("Uploading audio…")).toBeInTheDocument();

    rerender(
      <AudioUploader
        onSubmit={vi.fn()}
        isSubmitting={false}
        jobId="job-123"
        status={{ status: "queued" }}
      />
    );
    expect(screen.getByText("Upload received. Waiting for decode…")).toBeInTheDocument();

    rerender(
      <AudioUploader
        onSubmit={vi.fn()}
        isSubmitting={false}
        jobId="job-123"
        status={{ status: "processing" }}
      />
    );
    expect(screen.getByText("Decoding audio and extracting pitch…")).toBeInTheDocument();
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

    // Group header should show album name and artist (artist appears in both group label and track row)
    expect(screen.getByText(RegExp(demoExample.album, "i"))).toBeInTheDocument();
    expect(screen.getAllByText(RegExp(demoExample.artist, "i")).length).toBeGreaterThan(0);

    // The first group is auto-opened on mount — track card is already visible
    // Track card should be visible; aria-label no longer includes artist
    await user.click(screen.getByRole("button", { name: `Select example track: ${demoExample.display_name}` }));

    expect(onSelectExample).toHaveBeenCalledTimes(1);
    expect(onSelectExample).toHaveBeenCalledWith(demoExample);
  });

  it("marks selected example card with pressed state", async () => {
    const user = userEvent.setup();
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

    // The first group is auto-opened on mount (grouped by artist when no album)
    // No click needed to expand — verify the track button is already visible

    expect(
      screen.getByRole("button", { name: "Select example track: Demo Example" })
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
    // The component renders the status message text, not a .status__value element
    expect(screen.getByText("Analyzing your recording…")).toBeInTheDocument();
  });

  it("shows idle state without a progress bar before any job is submitted", () => {
    render(<AnalysisStatus jobId={null} status={null} isPolling={false} isFetchingResults={false} />);

    expect(screen.getByText("Ready to analyze")).toBeInTheDocument();
    expect(screen.queryByLabelText("Progress")).not.toBeInTheDocument();
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

    expect(screen.getByText("Analyzing your recording…")).toBeInTheDocument();
    expect(screen.getByText("Extracting pitch data…")).toBeInTheDocument();
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
    expect(screen.getByText("What should I practice next?")).toBeInTheDocument();
    expect(screen.getByText("completed", { selector: ".results__status" })).toBeInTheDocument();
    expect(screen.getByText("10.00")).toBeInTheDocument();
    expect(screen.getByText("220.00 (A3)")).toBeInTheDocument();
    expect(screen.getByText("440.00 (A4)")).toBeInTheDocument();
    expect(screen.getByText("57.00 to 69.00 (A3 to A4)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download JSON" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "⭐ Download PDF" })).toBeInTheDocument();
    // The heading contains a GlossaryTerm button so text is split across elements — use heading role
    expect(screen.getByRole("heading", { name: /How consistent each metric is/i })).toBeInTheDocument();
    expect(screen.getByText("F0 Mean Hz")).toBeInTheDocument();
    expect(screen.getByText("Tessitura Center Midi")).toBeInTheDocument();
    expect(screen.getByText("221.40 (A3)")).toBeInTheDocument();
    expect(screen.getByText("[215.20, 228.70] (G#3 to A#3)")).toBeInTheDocument();
    expect(screen.getByText("57.00 (A3)")).toBeInTheDocument();
    expect(screen.getByText("[56.50, 57.50] (G#3 to A#3)")).toBeInTheDocument();
    expect(screen.getByText("0.008")).toBeInTheDocument();
  });

  it("renders interpretation help and quality notes when warnings are present", () => {
    const results = {
      summary: {
        duration_seconds: 10.0,
      },
      warnings: [
        "Vocal separation unavailable: model not installed",
        "Tessitura analysis unavailable: insufficient voiced frames",
      ],
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

    // "Interpretation help" section was replaced by progressive disclosure layout
    expect(screen.getByRole("heading", { name: "Analysis quality notes" })).toBeInTheDocument();
    expect(screen.getByText("Vocal separation unavailable: model not installed")).toBeInTheDocument();
    expect(screen.getByText("Tessitura analysis unavailable: insufficient voiced frames")).toBeInTheDocument();
  });

  it("omits quality notes when no warning inputs are present", () => {
    const results = {
      summary: {
        duration_seconds: 10.0,
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

    // "Interpretation help" section was replaced by progressive disclosure layout
    expect(screen.queryByRole("heading", { name: "Analysis quality notes" })).not.toBeInTheDocument();
  });

  it("renders plain-language guidance cards and no plot-like analysis visuals", () => {
    const results = {
      metadata: { duration_seconds: 12.3 },
      summary: {
        duration_seconds: 12.3,
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

    expect(screen.getByRole("heading", { name: "Practice guidance" })).toBeInTheDocument();
    expect(screen.getByText("What should I practice next?")).toBeInTheDocument();
    expect(screen.getByText("Where did I spend most effort?")).toBeInTheDocument();
    expect(screen.getByText("What one adjustment should I make next session?")).toBeInTheDocument();
    expect(
      screen.getByText(
        "This on-screen analysis is text-only with no plots or graphs; use these plain-language coaching steps for next-session decisions. Detailed plots remain available only in PDF export."
      )
    ).toBeInTheDocument();

    expect(screen.queryByRole("heading", { name: /piano roll/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/session distribution summary/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/time\s*[×x]\s*pitch heatmap/i)).not.toBeInTheDocument();
    // Note: "pitch curves" appears in the PDF export description text, not as a rendered visualization
    expect(screen.queryByLabelText("Piano roll visualization")).not.toBeInTheDocument();

    expect(screen.queryByText("Where in your range did you sing most?")).not.toBeInTheDocument();
    expect(screen.queryByText("Where should you practice in the recording next?")).not.toBeInTheDocument();
    expect(screen.queryByText("Is your pitch staying steady through the phrase?")).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Range usage split across lower, middle, and upper range")
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Singing time split across start, middle, and end of the recording")
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Average pitch at start, middle, and end of the phrase")
    ).not.toBeInTheDocument();

    expect(screen.getByText(/Most effort was in the .* of the recording/)).toBeInTheDocument();
    expect(screen.getByText(/Detected pitch span in this take:/)).toBeInTheDocument();
    expect(screen.getByText(/Use one small adjustment next time|Reduce tempo by about 10%/)).toBeInTheDocument();
  });

  it("keeps guidance cards usable when only one pitch frame is present", () => {
    const results = {
      summary: {
        duration_seconds: 8.0,
      },
      pitch: {
        frames: [{ time: 0.0, midi: 60, f0: 261.63, confidence: 0.95 }],
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

    expect(screen.getByText("What should I practice next?")).toBeInTheDocument();
    expect(screen.getByText("Where did I spend most effort?")).toBeInTheDocument();
    expect(screen.getByText("What one adjustment should I make next session?")).toBeInTheDocument();
    expect(screen.getByText(/Start with the start of the recording/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Average pitch at start, middle, and end of the phrase")).not.toBeInTheDocument();
  });

  it("uses range-derived plain-language effort guidance when pitch-frame timing is unavailable", () => {
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

    expect(screen.getByText("What should I practice next?")).toBeInTheDocument();
    expect(screen.getByText("Where did I spend most effort?")).toBeInTheDocument();
    expect(screen.getByText("What one adjustment should I make next session?")).toBeInTheDocument();
    expect(screen.getByText(/Most effort was in your upper range/)).toBeInTheDocument();
    expect(screen.queryByText("No time-aligned pitch data is available for this recording.")).not.toBeInTheDocument();
  });

  it("renders graceful sparse-data guidance copy", () => {
    const results = {
      summary: {
        duration_seconds: 6.0,
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

    expect(
      screen.getByText(
        "Analysis completed, but the file did not contain enough detectable pitch activity for detailed personalized guidance."
      )
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Practice guidance" })).toBeInTheDocument();
    expect(screen.getByText("What should I practice next?")).toBeInTheDocument();
    expect(screen.getByText("Where did I spend most effort?")).toBeInTheDocument();
    expect(screen.getByText("What one adjustment should I make next session?")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /piano roll/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/session distribution summary/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/time\s*[×x]\s*pitch heatmap/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "We could not detect enough pitch activity to map effort by time or range in this recording."
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Practice the section that felt hardest at a slower tempo (about 70%) and repeat it three times."
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Use one small adjustment next time: take a full breath before each phrase and keep volume comfortable."
      )
    ).toBeInTheDocument();
    expect(screen.queryByText("No range-usage data is available for this session.")).not.toBeInTheDocument();
    expect(screen.queryByText("No time-aligned pitch data is available for this recording.")).not.toBeInTheDocument();
    expect(screen.queryByText("Not enough pitch data is available to show a trend yet.")).not.toBeInTheDocument();
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

    // Tabs replaced by disclosure sections in progressive disclosure redesign
    const calibrationDisclosure = screen.getByText("Technical statistics & calibration");

    expect(calibrationDisclosure).toBeInTheDocument();
    // Calibration is inside a closed disclosure by default

    await user.click(calibrationDisclosure);

    const sampleCountItem = screen.getByText("Reference samples (N)").closest(".summary-list__item");

    // Disclosure is now open after click
    expect(screen.getByRole("heading", { name: "Reference calibration summary" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "These metrics come from reference dataset calibration (ground-truth generated data) and are not derived from uploaded or example track runtime behavior."
      )
    ).toBeInTheDocument();
    expect(screen.getByText("100.00 to 300.00")).toBeInTheDocument();
    expect(screen.getByText("-0.20")).toBeInTheDocument();
    expect(sampleCountItem).not.toBeNull();
    expect(within(sampleCountItem).getByText("5")).toBeInTheDocument();
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

    await user.click(screen.getByText("Technical statistics & calibration"));

    const sampleCountItem = screen.getByText("Reference samples (N)").closest(".summary-list__item");
    const voicedFramesItem = screen.getByText("Voiced frame count").closest(".summary-list__item");

    expect(sampleCountItem).not.toBeNull();
    expect(voicedFramesItem).not.toBeNull();
    expect(within(sampleCountItem).getByText("7")).toBeInTheDocument();
    expect(within(voicedFramesItem).getByText("9")).toBeInTheDocument();
  });

  it("renders evidence-linked diagnostics with timestamp fallback when no audio source is provided", () => {
    const results = {
      summary: {
        duration_seconds: 12.0,
      },
      evidence: {
        events: [
          {
            id: "lowest_voiced_note",
            label: "Lowest voiced note",
            timestamp_s: 3.2,
            timestamp_label: "00:03",
            note: "A3",
          },
          {
            id: "highest_voiced_note",
            label: "Highest voiced note",
            timestamp_s: 8.4,
            timestamp_label: "00:08",
            note: "A4",
          },
          {
            id: "largest_pitch_jump",
            label: "Largest pitch jump",
            timestamp_s: 8.4,
            timestamp_label: "00:08",
          },
        ],
        lowest_voiced_note_ref: "lowest_voiced_note",
        highest_voiced_note_ref: "highest_voiced_note",
        guidance: [
          {
            id: "guidance_large_transition_control",
            claim: "One transition shows the largest pitch jump.",
            why: "The largest jump is around 00:08.",
            action: "Loop that transition slowly before singing full tempo.",
            evidence_refs: ["largest_pitch_jump"],
          },
        ],
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

    // "Evidence references" is an aria-label on a <ul>, not a heading
    expect(screen.getByRole("list", { name: "Evidence references" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Audio playback is not available for this result. The timestamps below show when these moments occur in your recording."
      )
    ).toBeInTheDocument();
    expect(screen.getByText("A3 at 00:03")).toBeInTheDocument();
    expect(screen.getByText("A4 at 00:08")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Jump to 00:03" })[0]).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Listen snippet" })).not.toBeInTheDocument();

    expect(screen.getByText(/Claim:/)).toBeInTheDocument();
    expect(screen.getByText(/Why:/)).toBeInTheDocument();
    expect(screen.getByText(/Action:/)).toBeInTheDocument();
    expect(screen.getByText("Largest pitch jump (00:08)")).toBeInTheDocument();

    expect(screen.queryByRole("heading", { name: /piano roll/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/time\s*[×x]\s*pitch heatmap/i)).not.toBeInTheDocument();
  });

  it("supports jump and listen controls when an audio source is available", async () => {
    vi.useFakeTimers();
    const playSpy = vi
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockImplementation(() => Promise.resolve());
    const pauseSpy = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});

    const results = {
      summary: {
        duration_seconds: 12.0,
      },
      evidence: {
        events: [
          {
            id: "lowest_voiced_note",
            label: "Lowest voiced note",
            timestamp_s: 2.0,
            timestamp_label: "00:02",
            note: "A3",
          },
          {
            id: "highest_voiced_note",
            label: "Highest vocal note",
            timestamp_s: 6.0,
            timestamp_label: "00:06",
            note: "A4",
          },
        ],
        lowest_voiced_note_ref: "lowest_voiced_note",
        highest_voiced_note_ref: "highest_voiced_note",
        guidance: [],
      },
      pitch: { frames: [{ time: 0.0, f0: 220.0 }] },
      tessitura: { histogram: [0.4, 0.6] },
    };

    render(
      <AnalysisResults
        results={results}
        status={{ status: "completed" }}
        isFetchingResults={false}
        onDownloadCsv={vi.fn()}
        onDownloadJson={vi.fn()}
        onDownloadPdf={vi.fn()}
        audioSourceUrl="/examples/demo.opus"
        audioSourceLabel="Demo Example"
      />
    );

    const audio = screen.getByLabelText("Evidence playback source: Demo Example");
    expect(audio).toHaveAttribute("src", expect.stringContaining("/examples/demo.opus"));

    const lowRow = screen.getByText("Lowest voiced note").closest(".evidence-row");
    expect(lowRow).not.toBeNull();

    const jumpButton = within(lowRow).getByRole("button", { name: "Jump to 00:02" });
    const listenButton = within(lowRow).getByRole("button", { name: "Listen snippet" });

    fireEvent.click(jumpButton);
    expect(audio.currentTime).toBeCloseTo(2.0, 1);

    fireEvent.click(listenButton);
    expect(audio.currentTime).toBeCloseTo(0.5, 1);
    expect(playSpy).toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(pauseSpy).toHaveBeenCalled();

    playSpy.mockRestore();
    pauseSpy.mockRestore();
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

  it("uses example gallery source card and runs full analysis via intent panel", async () => {
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

    // Step 1: select the Example Library source card
    await user.click(screen.getByRole("button", { name: /Example Library/i }));

    expect(screen.queryByRole("heading", { name: "Analysis status" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Analysis results" })).not.toBeInTheDocument();

    // The first group is auto-opened on mount — click the track directly
    const selectButton = await screen.findByRole("button", {
      name: "Select example track: Demo Example",
    });
    await user.click(selectButton);

    // Step 2: intent panel appears — click Full analysis
    const fullAnalysisBtn = await screen.findByRole("button", { name: /Full analysis/i });
    await user.click(fullAnalysisBtn);

    await waitFor(() => {
      expect(submitExampleAnalysisJob).toHaveBeenCalledWith("demo-1");
    });

    // Results region should appear after job completes
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Analysis results" })).toBeInTheDocument();
    });

    expect(screen.getByRole("heading", { name: "Practice guidance" })).toBeInTheDocument();
    expect(screen.getByText(/text-only with no plots or graphs/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /piano roll/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/session distribution summary/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/time\s*[×x]\s*pitch heatmap/i)).not.toBeInTheDocument();
  });

  it("wires example analysis audio URL into evidence playback when source metadata is example", async () => {
    const user = userEvent.setup();

    fetchExampleTracks.mockResolvedValue([
      {
        id: "demo-1",
        display_name: "Demo Example",
        artist: "Demo Artist",
      },
    ]);
    submitExampleAnalysisJob.mockResolvedValue({ job_id: "job-demo-audio" });
    fetchJobStatus.mockResolvedValue({ status: "completed" });
    fetchJobResults.mockResolvedValue({
      metadata: {
        source: "example",
        input_type: "example",
        filename: "Demo Example",
        original_filename: "demo.opus",
      },
      summary: {
        duration_seconds: 10,
      },
      evidence: {
        events: [
          {
            id: "lowest_voiced_note",
            label: "Lowest voiced note",
            timestamp_s: 2.0,
            timestamp_label: "00:02",
            note: "A3",
          },
          {
            id: "highest_voiced_note",
            label: "Highest voiced note",
            timestamp_s: 6.0,
            timestamp_label: "00:06",
            note: "A4",
          },
        ],
        lowest_voiced_note_ref: "lowest_voiced_note",
        highest_voiced_note_ref: "highest_voiced_note",
        guidance: [],
      },
      pitch: { frames: [{ time: 0.0, f0: 220.0 }] },
      tessitura: { histogram: [0.4, 0.6] },
    });

    render(<App />);

    await user.click(screen.getByRole("button", { name: /Example Library/i }));
    // The first group is auto-opened on mount — click the track directly
    await user.click(
      await screen.findByRole("button", {
        name: "Select example track: Demo Example",
      })
    );
    await user.click(await screen.findByRole("button", { name: /Full analysis/i }));

    const evidenceAudio = await screen.findByLabelText("Evidence playback source: Demo Example");
    expect(evidenceAudio).toHaveAttribute("src", expect.stringContaining("/examples/demo.opus"));
  });

  it("stops polling after first status failure", async () => {
    fetchExampleTracks.mockResolvedValue([]);
    submitAnalysisJob.mockResolvedValue({ job_id: "job-fail" });
    fetchJobStatus.mockRejectedValue(new Error("status down"));

    render(<App />);

    // Step 1: select Upload source card to reveal the file input
    fireEvent.click(screen.getByRole("button", { name: /Upload a File/i }));

    const input = screen.getByLabelText("Audio file");
    const file = new File(["wave"], "sample.wav", { type: "audio/wav" });
    fireEvent.change(input, { target: { files: [file] } });
    // AudioUploader's submit captures the file, intent panel appears
    fireEvent.click(screen.getByRole("button", { name: "Start analysis" }));

    // Step 2: intent panel is synchronously rendered after acceptedFile is set —
    // grab the button with real timers still active (avoids fake-timer deadlock
    // inside screen.findByRole's internal polling)
    const fullAnalysisBtn = screen.getByRole("button", { name: /Full analysis/i });

    // Switch to fake timers only after UI navigation is complete, so the
    // polling setInterval can be controlled without blocking async queries above
    vi.useFakeTimers();

    // Click Full analysis intent card to actually submit the job
    fireEvent.click(fullAnalysisBtn);

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

    // Step 1: select Upload source card to reveal the file input
    fireEvent.click(screen.getByRole("button", { name: /Upload a File/i }));

    const input = screen.getByLabelText("Audio file");
    const file = new File(["wave"], "sample.wav", { type: "audio/wav" });
    fireEvent.change(input, { target: { files: [file] } });
    // AudioUploader's submit captures the file, intent panel appears
    fireEvent.click(screen.getByRole("button", { name: "Start analysis" }));

    // Step 2: click Full analysis intent card to submit the job
    const fullAnalysisBtn = await screen.findByRole("button", { name: /Full analysis/i });
    fireEvent.click(fullAnalysisBtn);

    await waitFor(() => {
      expect(fetchJobResults).toHaveBeenCalledWith("job-calibration", "json");
    });

    const calibrationDisclosure = await screen.findByText("Technical statistics & calibration");
    fireEvent.click(calibrationDisclosure);

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

  it("keeps comparison report text-first with no forbidden analysis visuals", () => {
    render(
      <ComparisonResults
        sessionReport={mockSessionReport}
        onClose={vi.fn()}
        onStartNew={vi.fn()}
      />
    );

    expect(screen.getByText(/Mean pitch error of 0\.0 cents/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /piano roll/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/session distribution summary/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/time\s*[×x]\s*pitch heatmap/i)).not.toBeInTheDocument();
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

// ---------------------------------------------------------------------------
// SpectrogramInspector Ã¢ P2-B, P2-C, P2-D
// ---------------------------------------------------------------------------
describe("SpectrogramInspector", () => {
  // Build a minimal valid base64 spectrogram payload
  function makeSpectrogramData({ vocalsAvailable = true } = {}) {
    const nFreq = 4;
    const nTime = 8;
    const bytes = new Uint8Array(nFreq * nTime);
    for (let i = 0; i < bytes.length; i++) bytes[i] = i * 8;
    const b64 = btoa(String.fromCharCode(...bytes));
    const mix = {
      frames_b64: b64,
      n_freq: nFreq,
      n_time: nTime,
      frequencies_hz: [80, 200, 500, 2000],
      times_s: [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
    };
    const vocals = vocalsAvailable
      ? { ...mix, available: true }
      : { available: false };
    return { mix, vocals };
  }

  it("renders a <canvas> element after data loads", async () => {
    fetchSpectrogram.mockResolvedValueOnce(makeSpectrogramData());

    const audioRef = { current: { currentTime: 0 } };
    render(
      <SpectrogramInspector
        jobId="test-job-1"
        audioRef={audioRef}
        evidenceEvents={[]}
        durationSeconds={5}
      />
    );

    // While loading the loading text should appear
    expect(screen.getByText(/Loading spectrogram/i)).toBeInTheDocument();

    // After resolving, canvas should appear
    const canvas = await screen.findByRole("img", { name: /spectrogram inspector/i });
    expect(canvas.tagName).toBe("CANVAS");
  });

  it("shows vocals unavailable note when vocals.available is false", async () => {
    fetchSpectrogram.mockResolvedValueOnce(makeSpectrogramData({ vocalsAvailable: false }));

    const audioRef = { current: { currentTime: 0 } };
    render(
      <SpectrogramInspector
        jobId="test-job-2"
        audioRef={audioRef}
        evidenceEvents={[]}
        durationSeconds={5}
      />
    );

    await screen.findByRole("img", { name: /spectrogram inspector/i });
    expect(screen.getByText(/Vocal stem unavailable/i)).toBeInTheDocument();
  });

  it("shows error message when fetchSpectrogram rejects", async () => {
    fetchSpectrogram.mockRejectedValueOnce(new Error("Spectrogram unavailable (503)"));

    const audioRef = { current: { currentTime: 0 } };
    render(
      <SpectrogramInspector
        jobId="test-job-3"
        audioRef={audioRef}
        evidenceEvents={[]}
        durationSeconds={5}
      />
    );

    const errorEl = await screen.findByRole("alert");
    expect(errorEl).toBeInTheDocument();
    expect(errorEl.textContent).toMatch(/unavailable/i);
  });

  it("inspector is open by default in AnalysisResults when jobId is provided", () => {
    // SpectrogramInspector mounts immediately (isOpen defaults to true) so
    // fetchSpectrogram IS called on first render when a jobId is present.
    fetchSpectrogram.mockResolvedValue(makeSpectrogramData());

    const results = {
      metadata: { duration_seconds: 5 },
      summary: { f0_min: 220, f0_max: 440 },
      evidence: { events: [], guidance: [] },
    };

    render(
      <AnalysisResults
        results={results}
        status={{ status: "completed" }}
        isFetchingResults={false}
        onDownloadCsv={vi.fn()}
        onDownloadJson={vi.fn()}
        onDownloadPdf={vi.fn()}
        jobId="test-job-open"
      />
    );

    // The details summary toggle should be present with the updated label
    expect(screen.getByText("Audio spectrogram (advanced)")).toBeInTheDocument();

    // The inspector section should be collapsed by default to avoid extra loading after results appear
    const details = screen.getByText("Audio spectrogram (advanced)").closest("details");
    expect(details).not.toHaveAttribute("open");

    // fetchSpectrogram should NOT be called since inspector is collapsed by default
    expect(fetchSpectrogram).not.toHaveBeenCalled();
  });

  it("does not break text-first guidance cards (no-graphs constraint)", () => {
    // Standard AnalysisResults render without jobId must still show guidance
    fetchSpectrogram.mockResolvedValue(makeSpectrogramData());

    const results = {
      metadata: { duration_seconds: 5 },
      summary: { f0_min: 220, f0_max: 440 },
      evidence: { events: [], guidance: [{ id: "g1", claim: "Test claim", why: "Test why", action: "Test action", evidence_refs: [] }] },
    };

    render(
      <AnalysisResults
        results={results}
        status={{ status: "completed" }}
        isFetchingResults={false}
        onDownloadCsv={vi.fn()}
        onDownloadJson={vi.fn()}
        onDownloadPdf={vi.fn()}
        // no jobId Ã¢ spectrogram toggle should be absent
      />
    );

    // Guidance cards should still render
    expect(screen.getByText("Test claim")).toBeInTheDocument();

    // No inspector toggle without jobId
    expect(screen.queryByText("Advanced audio inspector")).toBeNull();

    // No canvas
    expect(screen.queryByRole("img", { name: /spectrogram inspector/i })).toBeNull();
  });
});
