/**
 * VocalProfileCard — Visual summary of the singer's voice.
 *
 * Turns raw analysis data into identity, context, and encouragement.
 * Designed to be screenshot-worthy — the first thing a beginner
 * wants to show a friend is "look what my voice is."
 */

import { useMemo } from "react";
import { hzToMidi, classifyVoiceType } from "./VoiceTypeClassifier";

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

function midiToNoteName(midi) {
  if (!Number.isFinite(midi)) return "—";
  const rounded = Math.round(midi);
  const pc = ((rounded % 12) + 12) % 12;
  const octave = Math.floor(rounded / 12) - 1;
  return `${NOTE_NAMES[pc]}${octave}`;
}

// Famous singers by voice type — gives beginners immediate context
const VOICE_TYPE_CONTEXT = {
  Bass: { icon: "🎸", examples: "Johnny Cash, Barry White, Avi Kaplan", color: "#8b6f47" },
  Baritone: { icon: "🎤", examples: "Frank Sinatra, Elvis Presley, Hozier", color: "#a0826d" },
  Tenor: { icon: "🎶", examples: "Freddie Mercury, Sam Smith, Ed Sheeran", color: "#60a5fa" },
  Alto: { icon: "🎵", examples: "Amy Winehouse, Tracy Chapman, Annie Lennox", color: "#c084fc" },
  "Mezzo-Soprano": { icon: "✨", examples: "Adele, Lady Gaga, Beyoncé", color: "#f472b6" },
  Soprano: { icon: "🌟", examples: "Ariana Grande, Mariah Carey, Whitney Houston", color: "#fb923c" },
  Unknown: { icon: "🎤", examples: "", color: "#8d9ab8" },
};

function computeRangeSpan(f0Min, f0Max) {
  if (!Number.isFinite(f0Min) || !Number.isFinite(f0Max)) return null;
  const midiMin = hzToMidi(f0Min);
  const midiMax = hzToMidi(f0Max);
  if (midiMin === null || midiMax === null) return null;
  const semitones = Math.round(midiMax - midiMin);
  const octaves = Math.floor(semitones / 12);
  const remaining = semitones % 12;
  if (octaves >= 1 && remaining > 0) return `${octaves} octave${octaves > 1 ? "s" : ""} and ${remaining} note${remaining > 1 ? "s" : ""}`;
  if (octaves >= 1) return `${octaves} octave${octaves > 1 ? "s" : ""}`;
  return `${semitones} semitone${semitones !== 1 ? "s" : ""}`;
}

function computeStabilityLabel(results) {
  const pitchError = results?.inferential_statistics?.metrics?.pitch_error_mean_cents?.estimate;
  if (!Number.isFinite(pitchError)) return null;
  const abs = Math.abs(pitchError);
  if (abs < 10) return { label: "Very steady", emoji: "🎯", detail: "Your pitch stayed close to center throughout." };
  if (abs < 25) return { label: "Steady", emoji: "👍", detail: "Good pitch control with minor drift." };
  if (abs < 50) return { label: "Developing", emoji: "📈", detail: "Some pitch wandering — focus on sustaining notes longer." };
  return { label: "Expressive range", emoji: "🌊", detail: "Wide pitch variation — great for stylistic singing, practice centering for accuracy work." };
}

function VocalProfileCard({ results }) {
  const profile = useMemo(() => {
    const f0Min = results?.pitch?.f0_min ?? results?.summary?.f0_min;
    const f0Max = results?.pitch?.f0_max ?? results?.summary?.f0_max;
    const f0MinNote = results?.summary?.f0_min_note;
    const f0MaxNote = results?.summary?.f0_max_note;
    const duration = results?.metadata?.duration_seconds ?? results?.summary?.duration_seconds;
    const key = results?.keys?.best_key ?? results?.keys?.trajectory?.[0]?.label;

    if (!Number.isFinite(f0Min) || !Number.isFinite(f0Max)) return null;

    const voiceType = classifyVoiceType(f0Min, f0Max);
    const context = VOICE_TYPE_CONTEXT[voiceType.label] || VOICE_TYPE_CONTEXT.Unknown;
    const rangeSpan = computeRangeSpan(f0Min, f0Max);
    const stability = computeStabilityLabel(results);

    // Comfort center note
    const comfortCenter = results?.tessitura?.metrics?.comfort_center;
    const comfortNote = Number.isFinite(comfortCenter) ? midiToNoteName(comfortCenter) : null;

    return {
      voiceType,
      context,
      rangeSpan,
      stability,
      f0MinNote: f0MinNote || midiToNoteName(hzToMidi(f0Min)),
      f0MaxNote: f0MaxNote || midiToNoteName(hzToMidi(f0Max)),
      comfortNote,
      key,
      duration,
    };
  }, [results]);

  if (!profile) return null;

  const { voiceType, context, rangeSpan, stability, f0MinNote, f0MaxNote, comfortNote, key } = profile;

  return (
    <div className="vocal-profile-card" style={{ "--profile-accent": context.color }}>
      <div className="vocal-profile-card__header">
        <span className="vocal-profile-card__icon">{context.icon}</span>
        <div>
          <h3 className="vocal-profile-card__voice-type">{voiceType.label}</h3>
          <p className="vocal-profile-card__confidence">{voiceType.confidence}</p>
        </div>
      </div>

      {context.examples && (
        <p className="vocal-profile-card__context">
          Same voice type as {context.examples}
        </p>
      )}

      <div className="vocal-profile-card__stats">
        <div className="vocal-profile-card__stat">
          <span className="vocal-profile-card__stat-value">{f0MinNote} – {f0MaxNote}</span>
          <span className="vocal-profile-card__stat-label">Your range</span>
        </div>
        {rangeSpan && (
          <div className="vocal-profile-card__stat">
            <span className="vocal-profile-card__stat-value">{rangeSpan}</span>
            <span className="vocal-profile-card__stat-label">Span</span>
          </div>
        )}
        {comfortNote && (
          <div className="vocal-profile-card__stat">
            <span className="vocal-profile-card__stat-value">{comfortNote}</span>
            <span className="vocal-profile-card__stat-label">Sweet spot</span>
          </div>
        )}
        {key && (
          <div className="vocal-profile-card__stat">
            <span className="vocal-profile-card__stat-value">{key}</span>
            <span className="vocal-profile-card__stat-label">Detected key</span>
          </div>
        )}
      </div>

      {stability && (
        <div className="vocal-profile-card__stability">
          <span>{stability.emoji}</span>
          <div>
            <strong>{stability.label}</strong>
            <p>{stability.detail}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default VocalProfileCard;
