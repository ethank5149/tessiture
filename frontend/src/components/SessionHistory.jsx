/**
 * SessionHistory — Track progress across analysis sessions.
 *
 * Uses localStorage to save key metrics from each analysis and shows
 * how the singer is improving over time. This is critical for beginner
 * retention — people come back when they can see progress.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { hzToMidi } from "./VoiceTypeClassifier";

const STORAGE_KEY = "tessiture_session_history";
const MAX_SESSIONS = 50;

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

function midiToNote(midi) {
  if (!Number.isFinite(midi)) return "—";
  const rounded = Math.round(midi);
  const pc = ((rounded % 12) + 12) % 12;
  const octave = Math.floor(rounded / 12) - 1;
  return `${NOTE_NAMES[pc]}${octave}`;
}

function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveHistory(sessions) {
  try {
    const trimmed = sessions.slice(-MAX_SESSIONS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // localStorage full or unavailable — silently fail
  }
}

function extractSessionMetrics(results) {
  if (!results || typeof results !== "object") return null;

  const f0Min = results?.pitch?.f0_min ?? results?.summary?.f0_min;
  const f0Max = results?.pitch?.f0_max ?? results?.summary?.f0_max;
  const comfortCenter = results?.tessitura?.metrics?.comfort_center;
  const pitchError = results?.inferential_statistics?.metrics?.pitch_error_mean_cents?.estimate;
  const duration = results?.metadata?.duration_seconds ?? results?.summary?.duration_seconds;
  const key = results?.keys?.best_key ?? results?.keys?.trajectory?.[0]?.label;

  if (!Number.isFinite(f0Min) || !Number.isFinite(f0Max)) return null;

  const midiMin = hzToMidi(f0Min);
  const midiMax = hzToMidi(f0Max);

  return {
    timestamp: new Date().toISOString(),
    f0MinHz: f0Min,
    f0MaxHz: f0Max,
    midiMin,
    midiMax,
    rangeSemitones: Number.isFinite(midiMin) && Number.isFinite(midiMax) ? Math.round(midiMax - midiMin) : null,
    comfortCenter: Number.isFinite(comfortCenter) ? comfortCenter : null,
    pitchErrorCents: Number.isFinite(pitchError) ? pitchError : null,
    durationS: Number.isFinite(duration) ? duration : null,
    key: key || null,
  };
}

function computeProgress(current, previous) {
  const insights = [];

  if (current.rangeSemitones !== null && previous.rangeSemitones !== null) {
    const diff = current.rangeSemitones - previous.rangeSemitones;
    if (diff > 0) {
      insights.push({ type: "positive", text: `Your range grew by ${diff} note${diff > 1 ? "s" : ""} since last session.` });
    } else if (diff < 0) {
      insights.push({ type: "neutral", text: `Your range was ${Math.abs(diff)} note${Math.abs(diff) > 1 ? "s" : ""} narrower than last session — that's normal day-to-day variation.` });
    } else {
      insights.push({ type: "neutral", text: "Your range is consistent with last session." });
    }
  }

  if (current.pitchErrorCents !== null && previous.pitchErrorCents !== null) {
    const diff = Math.abs(current.pitchErrorCents) - Math.abs(previous.pitchErrorCents);
    if (diff < -3) {
      insights.push({ type: "positive", text: "Your pitch accuracy improved since last time." });
    } else if (diff > 5) {
      insights.push({ type: "neutral", text: "Pitch accuracy shifted a bit — try a slower tempo next session." });
    }
  }

  if (current.midiMax !== null && previous.midiMax !== null) {
    const highDiff = Math.round(current.midiMax - previous.midiMax);
    if (highDiff >= 1) {
      insights.push({
        type: "positive",
        text: `New high note! You reached ${midiToNote(current.midiMax)} — ${highDiff} note${highDiff > 1 ? "s" : ""} higher than last time.`,
      });
    }
  }

  if (current.midiMin !== null && previous.midiMin !== null) {
    const lowDiff = Math.round(previous.midiMin - current.midiMin);
    if (lowDiff >= 1) {
      insights.push({
        type: "positive",
        text: `New low note! You reached ${midiToNote(current.midiMin)} — ${lowDiff} note${lowDiff > 1 ? "s" : ""} lower than last time.`,
      });
    }
  }

  return insights;
}

function SessionHistory({ results }) {
  const [history, setHistory] = useState(() => loadHistory());
  const [saved, setSaved] = useState(false);

  const currentMetrics = useMemo(() => extractSessionMetrics(results), [results]);

  // Save current session to history (once per result set)
  const saveSession = useCallback(() => {
    if (!currentMetrics || saved) return;
    const updated = [...history, currentMetrics];
    setHistory(updated);
    saveHistory(updated);
    setSaved(true);
  }, [currentMetrics, history, saved]);

  // Auto-save when results arrive
  useEffect(() => {
    if (currentMetrics && !saved) {
      saveSession();
    }
  }, [currentMetrics, saved, saveSession]);

  // Reset saved flag when results change
  useEffect(() => {
    setSaved(false);
  }, [results]);

  const progress = useMemo(() => {
    if (!currentMetrics || history.length < 2) return [];
    const previous = history[history.length - 2]; // second-to-last (last is current)
    if (!previous) return [];
    return computeProgress(currentMetrics, previous);
  }, [currentMetrics, history]);

  const sessionCount = history.length;

  if (!currentMetrics) return null;

  return (
    <section className="session-history" aria-label="Session progress">
      <h3 className="session-history__title">
        Session #{sessionCount}
      </h3>

      {sessionCount === 1 && (
        <p className="session-history__first">
          This is your first session! Come back after your next practice to see how you've improved.
        </p>
      )}

      {progress.length > 0 && (
        <ul className="session-history__insights">
          {progress.map((insight, idx) => (
            <li
              key={idx}
              className={`session-history__insight session-history__insight--${insight.type}`}
            >
              <span aria-hidden="true">{insight.type === "positive" ? "🎉" : "📊"}</span>
              <span>{insight.text}</span>
            </li>
          ))}
        </ul>
      )}

      {sessionCount >= 3 && (
        <details className="results__disclosure">
          <summary>View session history ({sessionCount} sessions)</summary>
          <div className="results__disclosure__body">
            <table className="session-history__table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Date</th>
                  <th>Range</th>
                  <th>Span</th>
                </tr>
              </thead>
              <tbody>
                {[...history].reverse().slice(0, 10).map((session, idx) => {
                  const date = new Date(session.timestamp);
                  const dateStr = date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
                  return (
                    <tr key={idx}>
                      <td>{sessionCount - idx}</td>
                      <td>{dateStr}</td>
                      <td>
                        {midiToNote(session.midiMin)}–{midiToNote(session.midiMax)}
                      </td>
                      <td>{session.rangeSemitones ?? "—"} st</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}

export default SessionHistory;
