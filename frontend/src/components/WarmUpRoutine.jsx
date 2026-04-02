/**
 * WarmUpRoutine — Personalized warm-up generator.
 *
 * Takes the singer's detected range and comfort zone and generates
 * a short, actionable warm-up routine they can do before their next
 * practice session. Beginners don't know how to warm up — this tells
 * them exactly what to do.
 */

import { useMemo } from "react";
import { hzToMidi } from "./VoiceTypeClassifier";

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

function midiToNote(midi) {
  if (!Number.isFinite(midi)) return "—";
  const rounded = Math.round(midi);
  const pc = ((rounded % 12) + 12) % 12;
  const octave = Math.floor(rounded / 12) - 1;
  return `${NOTE_NAMES[pc]}${octave}`;
}

function generateSteps(comfortCenter, midiMin, midiMax, rangeSpan) {
  const steps = [];
  const centerNote = midiToNote(comfortCenter);
  const lowNote = midiToNote(midiMin);
  const highNote = midiToNote(midiMax);
  const halfStepBelow = midiToNote(comfortCenter - 3);
  const halfStepAbove = midiToNote(comfortCenter + 3);
  const gentleLow = midiToNote(Math.max(midiMin + 2, comfortCenter - 7));
  const gentleHigh = midiToNote(Math.min(midiMax - 2, comfortCenter + 7));

  // Step 1: Breathing (always)
  steps.push({
    title: "Breathing reset",
    duration: "1 minute",
    instruction: "Breathe in for 4 counts, hold for 4, breathe out for 8. Repeat 4 times. Keep your shoulders relaxed and let your belly expand.",
    why: "Activates your diaphragm and calms your nervous system before singing.",
  });

  // Step 2: Humming at comfort center
  steps.push({
    title: "Gentle humming",
    duration: "1 minute",
    instruction: `Hum on a comfortable note around ${centerNote}. Feel the vibration in your lips and nose. Slide gently up to ${halfStepAbove} and back down to ${halfStepBelow}. Keep it easy.`,
    why: "Warms your vocal cords without strain. The vibration loosens tension.",
  });

  // Step 3: Lip trills / slides
  steps.push({
    title: "Lip trills",
    duration: "1 minute",
    instruction: `Do lip trills (motor-boat lips) starting at ${centerNote}, sliding up to ${gentleHigh} and back down to ${gentleLow}. If lip trills are hard, use "brrr" or "vvv" instead.`,
    why: "Lip trills balance airflow and vocal cord tension — the single best warm-up exercise.",
  });

  // Step 4: Range-dependent step
  if (rangeSpan >= 12) {
    // Wide range: work the extremes gently
    steps.push({
      title: "Gentle range exploration",
      duration: "1 minute",
      instruction: `Sing a slow 5-note scale (do-re-mi-fa-sol) starting at ${gentleLow}, then move it up by one step each time until you reach ${gentleHigh}. Stay relaxed — stop before anything feels tight.`,
      why: "You have a wide range. This step activates your full voice without pushing the edges.",
    });
  } else {
    // Narrow range: focus on centering
    steps.push({
      title: "Centering exercise",
      duration: "1 minute",
      instruction: `Sing the vowel "ah" on ${centerNote} and hold it for 5 seconds. Then try ${halfStepAbove} and ${halfStepBelow}. Focus on keeping the sound steady and even.`,
      why: "Building stability in your comfort zone is more valuable than pushing range right now.",
    });
  }

  // Step 5: Closing phrase
  steps.push({
    title: "Phrase practice",
    duration: "1 minute",
    instruction: `Sing "ma-me-mi-mo-mu" on a single comfortable note (${centerNote}), then repeat it sliding up 2 notes and back. Finish by humming quietly for 10 seconds.`,
    why: "Connects your warm-up to actual singing. The vowel changes exercise your mouth and tongue.",
  });

  return steps;
}

function WarmUpRoutine({ results }) {
  const routine = useMemo(() => {
    const f0Min = results?.pitch?.f0_min ?? results?.summary?.f0_min;
    const f0Max = results?.pitch?.f0_max ?? results?.summary?.f0_max;
    const comfortCenter = results?.tessitura?.metrics?.comfort_center;

    if (!Number.isFinite(f0Min) || !Number.isFinite(f0Max)) return null;

    const midiMin = hzToMidi(f0Min);
    const midiMax = hzToMidi(f0Max);
    if (midiMin === null || midiMax === null) return null;

    const center = Number.isFinite(comfortCenter) ? comfortCenter : (midiMin + midiMax) / 2;
    const rangeSpan = midiMax - midiMin;

    return {
      steps: generateSteps(center, midiMin, midiMax, rangeSpan),
      totalMinutes: 5,
    };
  }, [results]);

  if (!routine) return null;

  return (
    <section className="warmup-routine" aria-label="Personalized warm-up routine">
      <h3 className="warmup-routine__title">Your 5-minute warm-up</h3>
      <p className="warmup-routine__subtitle">
        Do this before your next practice session. Each step builds on the last.
      </p>
      <ol className="warmup-routine__steps">
        {routine.steps.map((step, idx) => (
          <li key={idx} className="warmup-routine__step">
            <div className="warmup-routine__step-header">
              <span className="warmup-routine__step-number">{idx + 1}</span>
              <div>
                <strong className="warmup-routine__step-title">{step.title}</strong>
                <span className="warmup-routine__step-duration">{step.duration}</span>
              </div>
            </div>
            <p className="warmup-routine__step-instruction">{step.instruction}</p>
            <p className="warmup-routine__step-why"><em>Why:</em> {step.why}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

export default WarmUpRoutine;
