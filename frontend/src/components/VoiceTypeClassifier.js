/**
 * VoiceTypeClassifier - Utility for classifying vocal range into voice types
 * Uses standard MIDI-based voice type ranges
 */

const VOICE_TYPES = [
  { name: "Bass", midiLow: 40, midiHigh: 64, noteLow: "E2", noteHigh: "E4" },
  { name: "Baritone", midiLow: 43, midiHigh: 67, noteLow: "G2", noteHigh: "G4" },
  { name: "Tenor", midiLow: 48, midiHigh: 72, noteLow: "C3", noteHigh: "C5" },
  { name: "Alto", midiLow: 53, midiHigh: 77, noteLow: "F3", noteHigh: "F5" },
  { name: "Mezzo-Soprano", midiLow: 57, midiHigh: 81, noteLow: "A3", noteHigh: "A5" },
  { name: "Soprano", midiLow: 60, midiHigh: 84, noteLow: "C4", noteHigh: "C6" },
];

/**
 * Convert Hz to MIDI note number
 * Formula: 69 + 12 * log2(f / 440)
 */
export const hzToMidi = (hz) => {
  if (!Number.isFinite(hz) || hz <= 0) return null;
  return 69 + 12 * Math.log2(hz / 440);
};

/**
 * Classify voice type based on detected pitch range
 * @param {number} f0MinHz - Lowest detected pitch in Hz
 * @param {number} f0MaxHz - Highest detected pitch in Hz
 * @returns {object} { label, confidence, description }
 */
export const classifyVoiceType = (f0MinHz, f0MaxHz) => {
  if (!Number.isFinite(f0MinHz) || !Number.isFinite(f0MaxHz) || f0MinHz >= f0MaxHz) {
    return {
      label: "Unknown",
      confidence: "insufficient data",
      description: "Not enough pitch data to classify voice type.",
    };
  }

  const midiMin = hzToMidi(f0MinHz);
  const midiMax = hzToMidi(f0MaxHz);

  if (midiMin === null || midiMax === null) {
    return {
      label: "Unknown",
      confidence: "insufficient data",
      description: "Could not convert pitch range to voice type.",
    };
  }

  // Score each voice type by overlap with detected range
  const scores = VOICE_TYPES.map((vt) => {
    // Calculate overlap between detected range and voice type range
    const overlapStart = Math.max(midiMin, vt.midiLow);
    const overlapEnd = Math.min(midiMax, vt.midiHigh);
    const overlap = Math.max(0, overlapEnd - overlapStart);

    // Detected range span
    const detectedSpan = midiMax - midiMin;

    // Score: how much of the detected range falls within this voice type
    const score = detectedSpan > 0 ? overlap / detectedSpan : 0;

    return { ...vt, score, overlap };
  });

  // Sort by score descending
  scores.sort((a, b) => b.score - a.score);

  const best = scores[0];
  const second = scores[1];

  // Determine confidence
  let confidence = "likely";
  if (best.score < 0.5) {
    confidence = "possibly";
  } else if (best.score > 0.8 && best.score - second.score > 0.2) {
    confidence = "very likely";
  }

  const description = `Based on your detected range ${best.noteLow}–${best.noteHigh}, you may be a ${best.name}.`;

  return {
    label: best.name,
    confidence,
    description,
  };
};

export default { classifyVoiceType, hzToMidi };
