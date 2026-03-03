import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
import ExampleGallery from "./ExampleGallery";

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
});
