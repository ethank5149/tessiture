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

  const width = 600;
  const height = 240;
  const yPadding = 16;
  const pitchValues = hasNotes
    ? notes.map((note) => note.pitch)
    : hasFrames
      ? frames.map((frame) => frame.pitch)
      : [0, 1];
  const minPitch = Math.min(...pitchValues, 0);
  const maxPitch = Math.max(...pitchValues, 1);
  const pitchRange = maxPitch - minPitch || 1;

  const timeValues = hasNotes
    ? notes.map((note) => note.end)
    : hasFrames
      ? frames.map((frame) => frame.time)
      : [0, 1];
  const maxTime = Math.max(...timeValues, 1);

  return (
    <section className="card chart">
      <header className="card__header">
        <h3 className="card__title">Piano roll</h3>
        <p className="card__meta">Note-level pitch activity</p>
      </header>
      <div className="chart__body" role="img" aria-label="Piano roll visualization">
        {(hasNotes || hasFrames) ? (
          <svg className="chart__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            <rect width={width} height={height} fill="transparent" />
            {hasNotes
              ? notes.map((note, index) => {
                  const x = (note.start / maxTime) * width;
                  const noteWidth = (note.duration / maxTime) * width;
                  const y =
                    height -
                    yPadding -
                    ((note.pitch - minPitch) / pitchRange) * (height - yPadding * 2);
                  return (
                    <rect
                      key={`${note.start}-${index}`}
                      x={x}
                      y={y}
                      width={Math.max(noteWidth, 2)}
                      height={6}
                      fill="currentColor"
                      opacity="0.7"
                    />
                  );
                })
              : frames.map((frame, index) => {
                  const x = (frame.time / maxTime) * width;
                  const y =
                    height -
                    yPadding -
                    ((frame.pitch - minPitch) / pitchRange) * (height - yPadding * 2);
                  return (
                    <circle key={`${frame.time}-${index}`} cx={x} cy={y} r={2} fill="currentColor" />
                  );
                })}
          </svg>
        ) : (
          <p className="chart__placeholder">No note or frame data available in results.</p>
        )}
      </div>
      <footer className="chart__footer">
        <span>Pitch range: {minPitch.toFixed(1)}–{maxPitch.toFixed(1)}</span>
        <span>{hasNotes ? "Notes" : "Frames"}</span>
      </footer>
    </section>
  );
}

export default PianoRoll;
