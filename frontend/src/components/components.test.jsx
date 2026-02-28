import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import {
  fetchExampleTracks,
  fetchJobResults,
  fetchJobStatus,
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
  submitAnalysisJob: vi.fn(),
  submitExampleAnalysisJob: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
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
    expect(screen.getByText("processing")).toBeInTheDocument();
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
        tessitura_range: [57.0, 69.0],
        confidence: 0.92,
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
    expect(screen.getByText("10.00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download JSON" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeInTheDocument();
  });
});

describe("App example gallery wiring", () => {
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
});
