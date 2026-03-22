/**
 * VocalRangeBar - SVG visualization of vocal range
 * Shows detected range, tessitura band, and voice type zones
 */

import { useMemo } from "react";

const VOICE_TYPE_ZONES = [
  { name: "Bass", midiLow: 40, midiHigh: 64, color: "#6b4423" },
  { name: "Baritone", midiLow: 43, midiHigh: 67, color: "#8b5a2b" },
  { name: "Tenor", midiLow: 48, midiHigh: 72, color: "#a0826d" },
  { name: "Alto", midiLow: 53, midiHigh: 77, color: "#c9a876" },
  { name: "Mezzo-Soprano", midiLow: 57, midiHigh: 81, color: "#d4a574" },
  { name: "Soprano", midiLow: 60, midiHigh: 84, color: "#e8c4a0" },
];

const FULL_RANGE_LOW = 40; // E2
const FULL_RANGE_HIGH = 84; // C6
const FULL_RANGE_SPAN = FULL_RANGE_HIGH - FULL_RANGE_LOW;

function hzToMidi(hz) {
  if (!Number.isFinite(hz) || hz <= 0) return null;
  return 69 + 12 * Math.log2(hz / 440);
}

function midiToPercent(midi) {
  return ((midi - FULL_RANGE_LOW) / FULL_RANGE_SPAN) * 100;
}

function VocalRangeBar({
  f0MinHz,
  f0MaxHz,
  tessituraLow,
  tessituraHigh,
  f0MinNote = "—",
  f0MaxNote = "—",
}) {
  const data = useMemo(() => {
    const midiMin = hzToMidi(f0MinHz);
    const midiMax = hzToMidi(f0MaxHz);

    if (midiMin === null || midiMax === null) {
      return null;
    }

    const tessLow = tessituraLow ? midiToPercent(tessituraLow) : midiToPercent(midiMin);
    const tessHigh = tessituraHigh ? midiToPercent(tessituraHigh) : midiToPercent(midiMax);

    return {
      rangeStart: midiToPercent(midiMin),
      rangeEnd: midiToPercent(midiMax),
      tessStart: Math.max(0, tessLow),
      tessEnd: Math.min(100, tessHigh),
    };
  }, [f0MinHz, f0MaxHz, tessituraLow, tessituraHigh]);

  if (!data) {
    return (
      <div className="vocal-range-bar">
        <p className="vocal-range-bar__error">Unable to display vocal range.</p>
      </div>
    );
  }

  const svgHeight = 120;
  const barHeight = 40;
  const barY = (svgHeight - barHeight) / 2;

  return (
    <div className="vocal-range-bar">
      <svg
        className="vocal-range-bar__svg"
        viewBox={`0 0 100 ${svgHeight}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Your vocal range spans from ${f0MinNote} to ${f0MaxNote}, with your comfortable tessitura between these notes.`}
      >
        {/* Voice type zones as background bands */}
        {VOICE_TYPE_ZONES.map((zone) => {
          const zoneStart = midiToPercent(zone.midiLow);
          const zoneEnd = midiToPercent(zone.midiHigh);
          const zoneWidth = zoneEnd - zoneStart;

          return (
            <rect
              key={zone.name}
              x={zoneStart}
              y={barY}
              width={zoneWidth}
              height={barHeight}
              fill={zone.color}
              opacity="0.15"
            />
          );
        })}

        {/* Full range background */}
        <rect
          x={0}
          y={barY}
          width={100}
          height={barHeight}
          fill="none"
          stroke="var(--text-soft)"
          strokeWidth="0.5"
        />

        {/* Tessitura band (comfortable range) */}
        <rect
          x={data.tessStart}
          y={barY}
          width={data.tessEnd - data.tessStart}
          height={barHeight}
          fill="var(--brand)"
          opacity="0.3"
        />

        {/* Detected range bar */}
        <rect
          x={data.rangeStart}
          y={barY + 8}
          width={data.rangeEnd - data.rangeStart}
          height={barHeight - 16}
          fill="var(--brand)"
          opacity="0.8"
        />

        {/* Low note marker */}
        <line
          x1={data.rangeStart}
          y1={barY - 4}
          x2={data.rangeStart}
          y2={barY + barHeight + 4}
          stroke="var(--text-primary)"
          strokeWidth="1"
        />

        {/* High note marker */}
        <line
          x1={data.rangeEnd}
          y1={barY - 4}
          x2={data.rangeEnd}
          y2={barY + barHeight + 4}
          stroke="var(--text-primary)"
          strokeWidth="1"
        />

        {/* Low note label */}
        <text
          x={data.rangeStart}
          y={barY - 8}
          textAnchor="middle"
          fontSize="10"
          fill="var(--text-primary)"
          fontWeight="600"
        >
          {f0MinNote}
        </text>

        {/* High note label */}
        <text
          x={data.rangeEnd}
          y={barY - 8}
          textAnchor="middle"
          fontSize="10"
          fill="var(--text-primary)"
          fontWeight="600"
        >
          {f0MaxNote}
        </text>
      </svg>

      <div className="vocal-range-bar__legend">
        <div className="vocal-range-bar__legend-item">
          <span className="vocal-range-bar__legend-swatch" style={{ backgroundColor: "var(--brand)" }} />
          <span className="vocal-range-bar__legend-label">Your detected range</span>
        </div>
        <div className="vocal-range-bar__legend-item">
          <span
            className="vocal-range-bar__legend-swatch"
            style={{ backgroundColor: "var(--brand)", opacity: 0.3 }}
          />
          <span className="vocal-range-bar__legend-label">Comfortable tessitura</span>
        </div>
      </div>
    </div>
  );
}

export default VocalRangeBar;
