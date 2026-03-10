const extractNotes = (results) => {
  const notes =
    results?.notes?.events ??
    results?.note_events ??
    results?.notes ??
    results?.pitch?.notes ??
    results?.pitch_notes ??
    [];
  if (!Array.isArray(notes)) {
    return [];
  }
  return notes
    .map((note) => {
      if (!note || typeof note !== "object") {
        return null;
      }
      const start = note.start ?? note.onset ?? note.t0 ?? 0;
      const end = note.end ?? note.offset ?? note.t1 ?? start;
      const pitch = note.pitch ?? note.midi ?? note.note ?? null;
      return Number.isFinite(pitch)
        ? {
            start: Number(start),
            end: Number(end),
            pitch: Number(pitch),
            duration: Math.max(Number(end) - Number(start), 0.05),
          }
        : null;
    })
    .filter(Boolean);
};

const fallbackFrames = (results) => {
  const frames = results?.pitch?.frames ?? results?.pitch_frames ?? [];
  if (!Array.isArray(frames)) {
    return [];
  }
  return frames
    .map((frame, index) => {
      if (typeof frame === "number") {
        return { time: index, pitch: frame };
      }
      if (frame && typeof frame === "object") {
        return {
          time: frame.time ?? frame.t ?? index,
          pitch: frame.midi ?? frame.f0_hz ?? frame.f0 ?? frame.value ?? frame.pitch ?? null,
        };
      }
      return null;
    })
    .filter((frame) => frame && Number.isFinite(frame.pitch));
};

function PianoRoll({ results }) {
  const notes = extractNotes(results);
  const frames = notes.length === 0 ? fallbackFrames(results) : [];
  const hasNotes = notes.length > 0;
  const hasFrames = frames.length > 0;
  const pitchValues = hasNotes
    ? notes.map((note) => note.pitch)
    : hasFrames
      ? frames.map((frame) => frame.pitch)
      : [];

  const summaryText = pitchValues.length
    ? `Detected ${hasNotes ? `${notes.length} note events` : `${frames.length} pitch frames`} spanning ${Math.min(...pitchValues).toFixed(1)} to ${Math.max(...pitchValues).toFixed(1)}.`
    : "No note or frame data is available in this payload.";

  return (
    <section className="results-helper" aria-label="Pitch activity text summary">
      <h3 className="results-helper__title">Pitch activity summary</h3>
      <p className="results-helper__copy">{summaryText}</p>
      <p className="results-helper__copy">
        On-screen piano-roll graphics are disabled in analysis views; use exported PDF reports when detailed plots are needed.
      </p>
    </section>
  );
}

export default PianoRoll;
