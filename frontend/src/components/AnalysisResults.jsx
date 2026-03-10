import { useEffect, useId, useMemo, useRef, useState } from "react";
import ReportExporter from "./ReportExporter";

const SESSION_SEGMENTS = ["Start", "Middle", "End"];

const RESULTS_VIEWS = {
  analysis: "analysis",
  calibration: "calibration",
};

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

const isPlainObject = (value) =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const formatMidiNote = (midiValue) => {
  if (!Number.isFinite(midiValue)) {
    return "—";
  }
  const rounded = Math.round(midiValue);
  const pitchClass = ((rounded % 12) + 12) % 12;
  const octave = Math.floor(rounded / 12) - 1;
  return `${NOTE_NAMES[pitchClass]}${octave} (${midiValue.toFixed(1)} MIDI)`;
};

const formatValue = (value) => {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toFixed(2) : "—";
  }
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  return String(value);
};

const formatPValue = (value) => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  if (value < 0.001) {
    return "<0.001";
  }
  return value.toFixed(3);
};

const formatCountValue = (value) => {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(Math.round(value)) : "—";
  }
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return String(Math.round(numeric));
  }
  return String(value);
};

const prettifyMetricName = (name) =>
  String(name || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

const formatRangeValue = (value) => {
  if (Array.isArray(value) && value.length >= 2) {
    const [low, high] = value;
    return `${formatValue(low)} to ${formatValue(high)}`;
  }
  return formatValue(value);
};

const formatMinMaxRange = (minValue, maxValue) => {
  if (
    (minValue === null || minValue === undefined || minValue === "") &&
    (maxValue === null || maxValue === undefined || maxValue === "")
  ) {
    return "—";
  }
  return `${formatValue(minValue)} to ${formatValue(maxValue)}`;
};

const formatPitchWithNote = (value, note) => {
  const renderedValue = formatValue(value);
  if (typeof note === "string" && note.trim()) {
    return renderedValue === "—" ? note : `${renderedValue} (${note})`;
  }
  return renderedValue;
};

const formatRangeWithNotes = (range, notes) => {
  const renderedRange = formatRangeValue(range);
  if (Array.isArray(notes) && notes.length >= 2 && notes[0] && notes[1]) {
    return `${renderedRange} (${notes[0]} to ${notes[1]})`;
  }
  return renderedRange;
};

const formatConfidenceIntervalWithNotes = (ci) => {
  const rendered = `[${formatValue(ci?.low)}, ${formatValue(ci?.high)}]`;
  if (
    typeof ci?.low_note === "string" &&
    ci.low_note.trim() &&
    typeof ci?.high_note === "string" &&
    ci.high_note.trim()
  ) {
    return `${rendered} (${ci.low_note} to ${ci.high_note})`;
  }
  return rendered;
};

const normalizeQualityWarnings = (warnings) => {
  if (!Array.isArray(warnings)) {
    return [];
  }
  return warnings
    .filter((warning) => typeof warning === "string" && warning.trim())
    .map((warning) => warning.trim());
};

const formatTimestampLabel = (seconds) => {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) {
    return "00:00";
  }
  const rounded = Math.floor(value);
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
};

const normalizeEvidencePayload = (evidence) => {
  if (!evidence || typeof evidence !== "object") {
    return {
      events: [],
      guidance: [],
      lowest_voiced_note_ref: null,
      highest_voiced_note_ref: null,
    };
  }

  const events = Array.isArray(evidence.events)
    ? evidence.events.filter((event) => event && typeof event === "object")
    : [];

  const guidance = Array.isArray(evidence.guidance)
    ? evidence.guidance.filter((item) => item && typeof item === "object")
    : [];

  return {
    events,
    guidance,
    lowest_voiced_note_ref:
      typeof evidence.lowest_voiced_note_ref === "string" ? evidence.lowest_voiced_note_ref : null,
    highest_voiced_note_ref:
      typeof evidence.highest_voiced_note_ref === "string" ? evidence.highest_voiced_note_ref : null,
  };
};

const hzToMidi = (hz) => {
  if (!Number.isFinite(hz) || hz <= 0) {
    return null;
  }
  return 69 + 12 * Math.log2(hz / 440);
};

const extractTessituraHistogramBins = (results) => {
  const bins =
    results?.tessitura?.histogram ??
    results?.tessitura?.heatmap ??
    results?.tessitura?.pdf?.density ??
    results?.tessitura_histogram ??
    results?.histogram ??
    [];

  if (!Array.isArray(bins)) {
    return [];
  }

  return bins
    .map((bin) => {
      if (typeof bin === "number") {
        return bin;
      }
      if (bin && typeof bin === "object") {
        const numeric = Number(bin.value ?? bin.count ?? bin.intensity);
        return Number.isFinite(numeric) ? numeric : null;
      }
      return null;
    })
    .filter((value) => Number.isFinite(value) && value >= 0);
};

const summarizeTimeEffort = (results) => {
  const frames = extractPitchFramesForGuidance(results);
  if (!frames.length) {
    return null;
  }

  const minTime = Math.min(...frames.map((frame) => frame.time));
  const maxTime = Math.max(...frames.map((frame) => frame.time));
  const minMidi = Math.min(...frames.map((frame) => frame.midi));
  const maxMidi = Math.max(...frames.map((frame) => frame.midi));

  const timeSpan = Math.max(maxTime - minTime, 1e-6);
  const totalWeight = frames.reduce((sum, frame) => sum + frame.weight, 0);

  const segments = SESSION_SEGMENTS.map((label, index) => {
    const start = index / SESSION_SEGMENTS.length;
    const end = (index + 1) / SESSION_SEGMENTS.length;
    const usage = frames.reduce((sum, frame) => {
      const normalizedTime = Math.min(Math.max((frame.time - minTime) / timeSpan, 0), 1);
      const inSegment =
        index === SESSION_SEGMENTS.length - 1
          ? normalizedTime >= start && normalizedTime <= end
          : normalizedTime >= start && normalizedTime < end;
      return sum + (inSegment ? frame.weight : 0);
    }, 0);

    return {
      label,
      usage,
      ratio: totalWeight > 0 ? usage / totalWeight : 0,
    };
  });

  const mostActiveSegment = segments.reduce((best, segment) =>
    segment.usage > best.usage ? segment : best
  , segments[0]);

  return {
    mostActiveSegment,
    minMidi,
    maxMidi,
  };
};

const summarizeRangeEffort = (results) => {
  const bins = extractTessituraHistogramBins(results);
  if (!bins.length) {
    return null;
  }

  const labels = ["lower range", "middle range", "upper range"];
  const total = bins.reduce((sum, value) => sum + value, 0);
  const bandSize = Math.ceil(bins.length / labels.length);

  const bands = labels
    .map((label, bandIndex) => {
      const start = bandIndex * bandSize;
      const end = Math.min(bins.length, start + bandSize);
      const slice = bins.slice(start, end);
      const usage = slice.reduce((sum, value) => sum + value, 0);
      return {
        label,
        usage,
        ratio: total > 0 ? usage / total : 0,
      };
    })
    .filter((band) => band.usage > 0 || total === 0);

  if (!bands.length) {
    return null;
  }

  const mostUsedBand = bands.reduce((best, band) => (band.usage > best.usage ? band : best), bands[0]);
  const leastUsedBand = bands.reduce((lowest, band) => (band.usage < lowest.usage ? band : lowest), bands[0]);
  const upperBandRatio = bands.find((band) => band.label === "upper range")?.ratio ?? 0;

  return {
    mostUsedBand,
    leastUsedBand,
    upperBandRatio,
  };
};

const summarizePitchControl = (results) => {
  const frames = extractPitchFramesForGuidance(results);
  const values = frames.map((frame) => frame.midi);
  if (values.length < 2) {
    return null;
  }

  const buckets = {
    Start: [],
    Middle: [],
    End: [],
  };

  values.forEach((value, index) => {
    const ratio = values.length <= 1 ? 0 : index / (values.length - 1);
    if (ratio < 1 / 3) {
      buckets.Start.push(value);
    } else if (ratio < 2 / 3) {
      buckets.Middle.push(value);
    } else {
      buckets.End.push(value);
    }
  });

  const mean = (bucket) =>
    bucket.length ? bucket.reduce((sum, value) => sum + value, 0) / bucket.length : null;

  const startMean = mean(buckets.Start);
  const endMean = mean(buckets.End);
  const drift = Number.isFinite(startMean) && Number.isFinite(endMean) ? endMean - startMean : null;

  const stepDiffs = values.slice(1).map((value, index) => Math.abs(value - values[index]));
  const averageStep = stepDiffs.length
    ? stepDiffs.reduce((sum, value) => sum + value, 0) / stepDiffs.length
    : 0;

  const trendLabel =
    !Number.isFinite(drift) || Math.abs(drift) < 0.5
      ? "steady"
      : drift > 0
        ? "rising"
        : "falling";

  return {
    trendLabel,
    averageStep,
  };
};

const calculateSemitoneSpan = (minHz, maxHz) => {
  if (!Number.isFinite(minHz) || !Number.isFinite(maxHz) || minHz <= 0 || maxHz <= 0 || maxHz < minHz) {
    return null;
  }
  return 12 * Math.log2(maxHz / minHz);
};

function VocalSeparationStatus({ vocalSeparation }) {
  if (!vocalSeparation || typeof vocalSeparation !== "object") {
    return null;
  }

  const { applied, audio_type_requested, model } = vocalSeparation;

  if (applied === true) {
    return (
      <p className="vocal-separation-status vocal-separation-status--applied" role="status">
        <span className="vocal-separation-status__badge">AI vocal extraction applied</span>
        <span className="vocal-separation-status__detail">
          Vocals were separated from the mix using {model ?? "htdemucs"} before analysis
        </span>
      </p>
    );
  }

  if (applied === false && audio_type_requested === "mixed") {
    return (
      <p className="vocal-separation-status vocal-separation-status--warn" role="status">
        Vocal extraction unavailable — analyzed as uploaded
      </p>
    );
  }

  if (applied === false && (audio_type_requested === "isolated" || !audio_type_requested)) {
    return (
      <p className="vocal-separation-status vocal-separation-status--isolated" role="status">
        Analyzed as isolated vocals
      </p>
    );
  }

  return null;
}

const extractPitchFramesForGuidance = (results) => {
  const frames = results?.pitch?.frames ?? results?.pitch_frames ?? [];
  if (!Array.isArray(frames)) {
    return [];
  }

  return frames
    .map((frame, index) => {
      if (!frame || typeof frame !== "object") {
        return null;
      }

      const rawTime = frame.time ?? frame.t ?? index;
      const rawMidi = frame.midi ?? frame.note_midi ?? frame.pitch_midi ?? null;
      const rawHz = frame.f0_hz ?? frame.f0 ?? frame.frequency_hz ?? null;

      const time = Number(rawTime);
      const parsedMidi = Number(rawMidi);
      const hasRawMidi = rawMidi !== null && rawMidi !== undefined && rawMidi !== "";
      const midi = hasRawMidi && Number.isFinite(parsedMidi) ? parsedMidi : hzToMidi(Number(rawHz));
      if (!Number.isFinite(time) || !Number.isFinite(midi)) {
        return null;
      }

      const confidence = Number(frame.confidence ?? frame.weight ?? frame.probability);
      const weight = Number.isFinite(confidence) && confidence > 0 ? confidence : 1;

      return { time, midi, weight };
    })
    .filter(Boolean);
};

function AnalysisResults({
  results = null,
  status = null,
  error = null,
  isFetchingResults = false,
  onDownloadCsv,
  onDownloadJson,
  onDownloadPdf,
  audioSourceUrl = null,
  audioSourceLabel = null,
}) {
  const titleId = useId();
  const [activeResultsView, setActiveResultsView] = useState(RESULTS_VIEWS.analysis);
  const hasResults = Boolean(results && Object.keys(results).length > 0);
  const audioRef = useRef(null);
  const snippetTimeoutRef = useRef(null);

  const summary = results?.summary ?? results?.stats ?? results?.tessitura ?? null;
  const duration = results?.metadata?.duration_seconds ?? results?.duration_seconds ?? summary?.duration_seconds;
  const f0Min = results?.pitch?.f0_min ?? summary?.f0_min ?? summary?.min_f0;
  const f0Max = results?.pitch?.f0_max ?? summary?.f0_max ?? summary?.max_f0;
  const tessitura = summary?.tessitura_range ?? summary?.range;
  const f0MinNote = summary?.f0_min_note ?? results?.pitch?.f0_min_note ?? null;
  const f0MaxNote = summary?.f0_max_note ?? results?.pitch?.f0_max_note ?? null;
  const tessituraNotes =
    summary?.tessitura_range_notes ?? results?.tessitura?.metrics?.tessitura_band_notes ?? null;
  const inferentialStatistics =
    results?.inferential_statistics && typeof results.inferential_statistics === "object"
      ? results.inferential_statistics
      : null;
  const inferentialMetrics =
    inferentialStatistics?.metrics && typeof inferentialStatistics.metrics === "object"
      ? Object.entries(inferentialStatistics.metrics)
      : [];
  const hasPitchFrames =
    (Array.isArray(results?.pitch?.frames) && results.pitch.frames.length > 0) ||
    (Array.isArray(results?.pitch_frames) && results.pitch_frames.length > 0);
  const hasNoteEvents =
    (Array.isArray(results?.note_events) && results.note_events.length > 0) ||
    (Array.isArray(results?.notes?.events) && results.notes.events.length > 0);
  const hasTessituraHistogram =
    (Array.isArray(results?.tessitura?.histogram) && results.tessitura.histogram.length > 0) ||
    (Array.isArray(results?.tessitura?.pdf?.density) && results.tessitura.pdf.density.length > 0);
  const hasInferentialMetrics = inferentialMetrics.length > 0;
  const isSparseCompletedResults =
    status?.status === "completed" &&
    hasResults &&
    !hasPitchFrames &&
    !hasNoteEvents &&
    !hasTessituraHistogram &&
    !hasInferentialMetrics;
  const qualityWarnings = normalizeQualityWarnings(results?.warnings);
  const timeEffortSummary = useMemo(() => summarizeTimeEffort(results), [results]);
  const rangeEffortSummary = useMemo(() => summarizeRangeEffort(results), [results]);
  const pitchControlSummary = useMemo(() => summarizePitchControl(results), [results]);
  const semitoneSpan = calculateSemitoneSpan(Number(f0Min), Number(f0Max));
  const evidence = useMemo(() => normalizeEvidencePayload(results?.evidence), [results]);
  const evidenceEventMap = useMemo(() => {
    const map = new Map();
    evidence.events.forEach((event) => {
      if (typeof event.id === "string" && event.id.trim()) {
        map.set(event.id, event);
      }
    });
    return map;
  }, [evidence]);
  const lowestEvidenceEvent = evidence.lowest_voiced_note_ref
    ? evidenceEventMap.get(evidence.lowest_voiced_note_ref)
    : null;
  const highestEvidenceEvent = evidence.highest_voiced_note_ref
    ? evidenceEventMap.get(evidence.highest_voiced_note_ref)
    : null;
  const hasAudioReference = typeof audioSourceUrl === "string" && audioSourceUrl.trim().length > 0;

  const guidanceCards = useMemo(() => {
    const defaultPractice =
      "Practice the section that felt hardest at a slower tempo (about 70%) and repeat it three times.";

    let practiceNextAnswer = defaultPractice;
    if (pitchControlSummary?.averageStep >= 1.5) {
      practiceNextAnswer =
        "Practice smooth note-to-note slides for 5 minutes, then repeat your hardest phrase slowly to reduce sudden pitch jumps.";
    } else if (pitchControlSummary?.trendLabel === "rising" || pitchControlSummary?.trendLabel === "falling") {
      practiceNextAnswer =
        `Your pitch trend was ${pitchControlSummary.trendLabel}. Repeat one phrase at a comfortable key and keep the final note centered.`;
    } else if (timeEffortSummary?.mostActiveSegment?.label) {
      practiceNextAnswer =
        `Start with the ${timeEffortSummary.mostActiveSegment.label.toLowerCase()} of the recording, since that section carried most of your effort.`;
    }

    let effortAnswer =
      "We could not detect enough pitch activity to map effort by time or range in this recording.";
    if (timeEffortSummary?.mostActiveSegment?.label) {
      const effortPct = Math.round((timeEffortSummary.mostActiveSegment.ratio ?? 0) * 100);
      effortAnswer =
        `Most effort was in the ${timeEffortSummary.mostActiveSegment.label.toLowerCase()} of the recording (${effortPct}% of detected voiced time).`;
    } else if (rangeEffortSummary?.mostUsedBand?.label) {
      const effortPct = Math.round((rangeEffortSummary.mostUsedBand.ratio ?? 0) * 100);
      effortAnswer =
        `Most effort was in your ${rangeEffortSummary.mostUsedBand.label} (${effortPct}% of detected range usage).`;
    }

    let effortDetail = null;
    if (timeEffortSummary) {
      effortDetail =
        `Detected pitch span in this take: ${formatMidiNote(timeEffortSummary.minMidi)} to ${formatMidiNote(timeEffortSummary.maxMidi)}.`;
    }

    let adjustmentAnswer =
      "Use one small adjustment next time: take a full breath before each phrase and keep volume comfortable.";
    if (Number.isFinite(semitoneSpan) && semitoneSpan >= 12) {
      adjustmentAnswer =
        "Add one recovery reset after each high phrase (easy middle-range hum, then continue) to reduce fatigue in wide-range passages.";
    } else if (rangeEffortSummary?.upperBandRatio >= 0.35) {
      adjustmentAnswer =
        "Alternate each high phrase with one easy middle-range phrase so your voice can reset between upper-range efforts.";
    } else if (Number.isFinite(semitoneSpan) && semitoneSpan < 7) {
      adjustmentAnswer =
        "Add one gentle higher pass and one gentle lower pass to expand control beyond today’s narrow range.";
    } else if (pitchControlSummary?.averageStep >= 1.5) {
      adjustmentAnswer =
        "Reduce tempo by about 10% on the hardest phrase to smooth transitions between notes.";
    }

    return [
      {
        question: "What should I practice next?",
        answer: practiceNextAnswer,
      },
      {
        question: "Where did I spend most effort?",
        answer: effortAnswer,
        detail: effortDetail,
      },
      {
        question: "What one adjustment should I make next session?",
        answer: adjustmentAnswer,
      },
    ];
  }, [pitchControlSummary, rangeEffortSummary, semitoneSpan, timeEffortSummary]);

  const calibrationSummary = isPlainObject(results?.calibration?.summary)
    ? results.calibration.summary
    : null;
  const hasCalibrationSummary = Boolean(
    calibrationSummary && Object.keys(calibrationSummary).length > 0
  );
  const showResultsViewTabs = hasCalibrationSummary;

  useEffect(() => {
    if (!hasCalibrationSummary && activeResultsView === RESULTS_VIEWS.calibration) {
      setActiveResultsView(RESULTS_VIEWS.analysis);
    }
  }, [activeResultsView, hasCalibrationSummary]);

  const readableStatus = (status?.status ?? "waiting").replace(/_/g, " ");
  const analysisTabId = `${titleId}-tab-analysis`;
  const analysisPanelId = `${titleId}-panel-analysis`;
  const calibrationTabId = `${titleId}-tab-calibration`;
  const calibrationPanelId = `${titleId}-panel-calibration`;

  useEffect(() => () => {
    if (snippetTimeoutRef.current) {
      window.clearTimeout(snippetTimeoutRef.current);
      snippetTimeoutRef.current = null;
    }
  }, []);

  const jumpToEvidence = (event) => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    const timestamp = Number(event?.timestamp_s ?? event?.start_s);
    if (!Number.isFinite(timestamp) || timestamp < 0) {
      return;
    }
    audio.currentTime = timestamp;
  };

  const playEvidenceSnippet = (event) => {
    if (!hasAudioReference) {
      return;
    }
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    const timestamp = Number(event?.timestamp_s ?? event?.start_s);
    if (!Number.isFinite(timestamp) || timestamp < 0) {
      return;
    }

    const snippetDurationSeconds = 3;
    const start = Math.max(0, timestamp - 1.5);
    audio.currentTime = start;

    const playPromise = audio.play?.();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch(() => {});
    }

    if (snippetTimeoutRef.current) {
      window.clearTimeout(snippetTimeoutRef.current);
    }
    snippetTimeoutRef.current = window.setTimeout(() => {
      audio.pause?.();
      snippetTimeoutRef.current = null;
    }, snippetDurationSeconds * 1000);
  };

  return (
    <section className="card results" aria-labelledby={titleId} aria-busy={isFetchingResults}>
      <header className="card__header results__header">
        <div className="results__header-row">
          <h2 id={titleId} className="card__title">Analysis results</h2>
          <p className={`results__status results__status--${status?.status ?? "idle"}`}>{readableStatus}</p>
        </div>
        <p className="card__meta">Key outcomes are shown first, followed by plain-language practice guidance and supporting statistics.</p>
      </header>

      {error ? <p className="results__error" role="alert">{error}</p> : null}

      {!hasResults ? (
        <p className="results__empty">Results will appear here after the job completes.</p>
      ) : (
        <>
          {hasCalibrationSummary ? (
            <div className="results__view-tabs" role="tablist" aria-label="Analysis result views">
              <button
                id={analysisTabId}
                className="button results__view-tab"
                type="button"
                role="tab"
                aria-selected={activeResultsView === RESULTS_VIEWS.analysis}
                aria-controls={analysisPanelId}
                onClick={() => setActiveResultsView(RESULTS_VIEWS.analysis)}
              >
                General analysis
              </button>
              <button
                id={calibrationTabId}
                className="button results__view-tab"
                type="button"
                role="tab"
                aria-selected={activeResultsView === RESULTS_VIEWS.calibration}
                aria-controls={calibrationPanelId}
                onClick={() => setActiveResultsView(RESULTS_VIEWS.calibration)}
              >
                Reference calibration
              </button>
            </div>
          ) : null}

          {activeResultsView === RESULTS_VIEWS.analysis ? (
            <div
              id={showResultsViewTabs ? analysisPanelId : undefined}
              role={showResultsViewTabs ? "tabpanel" : undefined}
              aria-labelledby={showResultsViewTabs ? analysisTabId : undefined}
            >
              {isSparseCompletedResults ? (
                <p className="results__empty" role="status">
                  Analysis completed, but the file did not contain enough detectable pitch activity for detailed personalized guidance.
                </p>
              ) : null}

              <section className="results__section" aria-label="How to interpret analysis results">
                <h3 className="results__section-title">Interpretation help</h3>
                <p className="results__section-copy">
                  Use summary metrics as your quick snapshot, then follow the guidance cards below to pick one clear practice action.
                </p>
              </section>

              {qualityWarnings.length ? (
                <section className="results__section" aria-label="Analysis quality warnings">
                  <h3 className="results__section-title">Analysis quality notes</h3>
                  <ul>
                    {qualityWarnings.map((warning, index) => (
                      <li key={`${warning}-${index}`}>{warning}</li>
                    ))}
                  </ul>
                </section>
              ) : null}

              <section className="results__section results__section--summary" aria-label="Summary metrics">
                <h3 className="results__section-title">Summary</h3>
                <p className="results__summary-intro">
                  This overview highlights duration, pitch limits, and tessitura range.
                </p>
                <VocalSeparationStatus vocalSeparation={results?.metadata?.vocal_separation} />
                <dl className="summary-list">
                  <div className="summary-list__item">
                    <dt>Recording length (seconds)</dt>
                    <dd>{formatValue(duration)}</dd>
                  </div>
                  <div className="summary-list__item">
                    <dt>Lowest detected pitch (F0, Hz)</dt>
                    <dd>{formatPitchWithNote(f0Min, f0MinNote)}</dd>
                  </div>
                  <div className="summary-list__item">
                    <dt>Highest detected pitch (F0, Hz)</dt>
                    <dd>{formatPitchWithNote(f0Max, f0MaxNote)}</dd>
                  </div>
                  <div className="summary-list__item">
                    <dt>Comfortable singing range (tessitura)</dt>
                    <dd>{formatRangeWithNotes(tessitura, tessituraNotes)}</dd>
                  </div>
                </dl>
              </section>

              <section className="results__section results__section--evidence" aria-label="Evidence references">
                <div className="results__section-header">
                  <h3 className="results__section-title">Evidence references</h3>
                  <p className="results__section-meta">
                    Each diagnostic is linked to timestamped track moments so you can jump and listen without using charts.
                  </p>
                </div>

                {hasAudioReference ? (
                  <audio
                    ref={audioRef}
                    className="results__evidence-audio"
                    controls
                    preload="metadata"
                    src={audioSourceUrl}
                    aria-label={
                      audioSourceLabel
                        ? `Evidence playback source: ${audioSourceLabel}`
                        : "Evidence playback source"
                    }
                  />
                ) : (
                  <p className="evidence-actions__fallback">
                    Audio playback is unavailable for this result. Use timestamp references to locate moments manually.
                  </p>
                )}

                <ul className="results__evidence-list">
                  {[
                    { key: "lowest", title: "Lowest voiced note", event: lowestEvidenceEvent },
                    { key: "highest", title: "Highest voiced note", event: highestEvidenceEvent },
                  ].map((row) => {
                    if (!row.event) {
                      return null;
                    }

                    const timestampLabel =
                      row.event.timestamp_label ?? formatTimestampLabel(row.event.timestamp_s ?? row.event.start_s);
                    const noteLabel = row.event.note ?? "Unknown note";

                    return (
                      <li key={row.key} className="evidence-row">
                        <div className="evidence-row__meta">
                          <p className="guidance-card__question">{row.title}</p>
                          <p className="guidance-card__detail">
                            {noteLabel} at {timestampLabel}
                          </p>
                        </div>
                        <div className="evidence-actions" role="group" aria-label={`${row.title} actions`}>
                          <button
                            type="button"
                            className="button button--secondary"
                            onClick={() => jumpToEvidence(row.event)}
                            disabled={!hasAudioReference}
                          >
                            Jump to {timestampLabel}
                          </button>
                          {hasAudioReference ? (
                            <button
                              type="button"
                              className="button"
                              onClick={() => playEvidenceSnippet(row.event)}
                            >
                              Listen snippet
                            </button>
                          ) : null}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>

              <section className="results__section results__section--guidance" aria-label="Practice guidance cards">
                <div className="results__section-header">
                  <h3 className="results__section-title">Practice guidance</h3>
                  <p className="results__section-meta">
                    This on-screen analysis is text-only with no plots or graphs; use these plain-language coaching steps for next-session decisions. Detailed plots remain available only in PDF export.
                  </p>
                </div>
                <ol className="results__guidance-list" aria-label="Practice action steps">
                  {evidence.guidance.length
                    ? evidence.guidance.map((item, index) => {
                        const refs = Array.isArray(item.evidence_refs)
                          ? item.evidence_refs.filter((ref) => typeof ref === "string")
                          : [];
                        return (
                          <li key={item.id ?? `evidence-guidance-${index}`} className="guidance-card">
                            <h4 className="guidance-card__question">Guidance {index + 1}</h4>
                            <p className="guidance-card__answer"><strong>Claim:</strong> {item.claim ?? "—"}</p>
                            <p className="guidance-card__detail"><strong>Why:</strong> {item.why ?? "—"}</p>
                            <p className="guidance-card__detail"><strong>Action:</strong> {item.action ?? "—"}</p>
                            {refs.length ? (
                              <ul className="guidance-card__evidence" aria-label="Evidence references">
                                {refs.map((ref) => {
                                  const event = evidenceEventMap.get(ref);
                                  const timestampLabel = event?.timestamp_label ?? formatTimestampLabel(event?.timestamp_s);
                                  return (
                                    <li key={ref} className="guidance-card__evidence-item">
                                      <span>
                                        {event?.label ?? ref} ({timestampLabel})
                                      </span>
                                      <span className="evidence-actions">
                                        <button
                                          type="button"
                                          className="button button--secondary"
                                          onClick={() => jumpToEvidence(event)}
                                          disabled={!hasAudioReference || !event}
                                        >
                                          Jump to {timestampLabel}
                                        </button>
                                        {hasAudioReference && event ? (
                                          <button
                                            type="button"
                                            className="button"
                                            onClick={() => playEvidenceSnippet(event)}
                                          >
                                            Listen snippet
                                          </button>
                                        ) : null}
                                      </span>
                                    </li>
                                  );
                                })}
                              </ul>
                            ) : null}
                          </li>
                        );
                      })
                    : guidanceCards.map((card) => (
                        <li key={card.question} className="guidance-card">
                          <h4 className="guidance-card__question">{card.question}</h4>
                          <p className="guidance-card__answer">{card.answer}</p>
                          {card.detail ? <p className="guidance-card__detail">{card.detail}</p> : null}
                        </li>
                      ))}
                </ol>
              </section>

              {inferentialMetrics.length ? (
                <section className="results__section results__inferential" aria-label="Inferential statistics">
                  <div className="results__section-header">
                    <h3 className="results__section-title">How consistent each metric is (inferential statistics)</h3>
                    <p className="results__inferential-meta">
                      Analysis preset: {inferentialStatistics?.preset ?? "unknown"} · Confidence interval level: {formatValue(inferentialStatistics?.confidence_level)}
                    </p>
                  </div>
                  <p className="results__section-copy">
                    In the table below, “Estimate” is the best single value, “Confidence interval” is a likely range,
                    “p-value” helps indicate whether a difference is meaningful, and “Samples (N)” is how many data points were used.
                  </p>
                  <div className="results__inferential-table-wrap">
                    <table className="results__inferential-table">
                      <thead>
                        <tr>
                          <th scope="col">Metric</th>
                          <th scope="col">Estimate</th>
                          <th scope="col">Confidence interval (95%)</th>
                          <th scope="col">p-value (significance)</th>
                          <th scope="col">Samples (N)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {inferentialMetrics.map(([metricName, metricPayload]) => {
                          const ci = metricPayload?.confidence_interval ?? null;
                          return (
                            <tr key={metricName}>
                              <th scope="row">{prettifyMetricName(metricName)}</th>
                              <td>{formatPitchWithNote(metricPayload?.estimate, metricPayload?.estimate_note)}</td>
                              <td>{formatConfidenceIntervalWithNotes(ci)}</td>
                              <td>{formatPValue(metricPayload?.p_value)}</td>
                              <td>{formatValue(metricPayload?.n_samples)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </section>
              ) : null}
            </div>
          ) : null}

          {hasCalibrationSummary && activeResultsView === RESULTS_VIEWS.calibration ? (
            <section
              id={calibrationPanelId}
              className="results__section results__section--calibration"
              role="tabpanel"
              aria-labelledby={calibrationTabId}
              aria-label="Reference calibration summary"
            >
              <div className="results__section-header">
                <h3 className="results__section-title">Reference calibration summary</h3>
                <p className="results__section-meta">
                  These metrics come from reference dataset calibration (ground-truth generated data) and are not derived from uploaded or example track runtime behavior.
                </p>
              </div>
              <dl className="summary-list">
                <div className="summary-list__item">
                  <dt>Reference samples (N)</dt>
                  <dd>{formatCountValue(calibrationSummary?.reference_sample_count)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Reference frequency range (Hz)</dt>
                  <dd>
                    {formatMinMaxRange(
                      calibrationSummary?.reference_frequency_min_hz,
                      calibrationSummary?.reference_frequency_max_hz
                    )}
                  </dd>
                </div>
                <div className="summary-list__item">
                  <dt>Frequency bins (total)</dt>
                  <dd>{formatCountValue(calibrationSummary?.frequency_bin_count)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Frequency bins (populated)</dt>
                  <dd>{formatCountValue(calibrationSummary?.populated_frequency_bin_count)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Mean pitch bias (cents)</dt>
                  <dd>{formatValue(calibrationSummary?.mean_pitch_bias_cents)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Max absolute pitch bias (cents)</dt>
                  <dd>{formatValue(calibrationSummary?.max_abs_pitch_bias_cents)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Mean pitch variance (cents²)</dt>
                  <dd>{formatValue(calibrationSummary?.mean_pitch_variance_cents2)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Pitch error mean (cents)</dt>
                  <dd>{formatValue(calibrationSummary?.pitch_error_mean_cents)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Pitch error standard deviation (cents)</dt>
                  <dd>{formatValue(calibrationSummary?.pitch_error_std_cents)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Mean frame uncertainty (MIDI)</dt>
                  <dd>{formatValue(calibrationSummary?.mean_frame_uncertainty_midi)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Voiced frame count</dt>
                  <dd>{formatCountValue(calibrationSummary?.voiced_frame_count)}</dd>
                </div>
              </dl>
            </section>
          ) : null}

          <ReportExporter
            disabled={isFetchingResults}
            onDownloadCsv={onDownloadCsv}
            onDownloadJson={onDownloadJson}
            onDownloadPdf={onDownloadPdf}
          />
        </>
      )}
    </section>
  );
}

export default AnalysisResults;
