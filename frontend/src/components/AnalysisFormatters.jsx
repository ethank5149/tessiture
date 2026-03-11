/**
 * AnalysisFormatters - Utility functions for formatting analysis results
 * Contains all formatting logic for the AnalysisResults component
 */

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

export const formatMidiNote = (midiValue) => {
  if (!Number.isFinite(midiValue)) {
    return "—";
  }
  const rounded = Math.round(midiValue);
  const pitchClass = ((rounded % 12) + 12) % 12;
  const octave = Math.floor(rounded / 12) - 1;
  return `${NOTE_NAMES[pitchClass]}${octave} (${midiValue.toFixed(1)} MIDI)`;
};

export const formatValue = (value) => {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toFixed(2) : "—";
  }
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  return String(value);
};

export const formatPValue = (value) => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  if (value < 0.001) {
    return "<0.001";
  }
  return value.toFixed(3);
};

export const formatCountValue = (value) => {
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

export const prettifyMetricName = (name) =>
  String(name || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

export const formatRangeValue = (value) => {
  if (Array.isArray(value) && value.length >= 2) {
    const [low, high] = value;
    return `${formatValue(low)} to ${formatValue(high)}`;
  }
  return formatValue(value);
};

export const formatMinMaxRange = (minValue, maxValue) => {
  if (
    (minValue === null || minValue === undefined || minValue === "") &&
    (maxValue === null || maxValue === undefined || maxValue === "")
  ) {
    return "—";
  }
  return `${formatValue(minValue)} to ${formatValue(maxValue)}`;
};

export const formatPitchWithNote = (value, note) => {
  const renderedValue = formatValue(value);
  if (typeof note === "string" && note.trim()) {
    return renderedValue === "—" ? note : `${renderedValue} (${note})`;
  }
  return renderedValue;
};

export const formatRangeWithNotes = (range, notes) => {
  const renderedRange = formatRangeValue(range);
  if (Array.isArray(notes) && notes.length >= 2 && notes[0] && notes[1]) {
    return `${renderedRange} (${notes[0]} to ${notes[1]})`;
  }
  return renderedRange;
};

export const formatConfidenceIntervalWithNotes = (ci) => {
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

export const normalizeQualityWarnings = (warnings) => {
  if (!Array.isArray(warnings)) {
    return [];
  }
  return warnings
    .filter((warning) => typeof warning === "string" && warning.trim())
    .map((warning) => warning.trim());
};

export const formatTimestampLabel = (seconds) => {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) {
    return "00:00";
  }
  const rounded = Math.floor(value);
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
};

export const normalizeEvidencePayload = (evidence) => {
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

export const hzToMidi = (hz) => {
  if (!Number.isFinite(hz) || hz <= 0) {
    return null;
  }
  return 69 + 12 * Math.log2(hz / 440);
};

export const extractTessituraHistogramBins = (results) => {
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

const SESSION_SEGMENTS = ["Start", "Middle", "End"];

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

export const summarizeTimeEffort = (results) => {
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

export const summarizeRangeEffort = (results) => {
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

export const summarizePitchControl = (results) => {
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

export const calculateSemitoneSpan = (minHz, maxHz) => {
  if (!Number.isFinite(minHz) || !Number.isFinite(maxHz) || minHz <= 0 || maxHz <= 0 || maxHz < minHz) {
    return null;
  }
  return 12 * Math.log2(maxHz / minHz);
};

export const isPlainObject = (value) =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);
