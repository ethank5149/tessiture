/**
 * SongSuggestions — Recommends songs that fit the singer's range.
 *
 * This is the feature that makes "your range is D3–G4" meaningful
 * to a beginner. Instead of abstract note names, they see
 * "You could sing Hallelujah by Leonard Cohen."
 *
 * Song data is a curated static list — no API calls needed.
 * Songs are filtered by range overlap with the detected vocal range.
 */

import { useMemo } from "react";
import { hzToMidi } from "./VoiceTypeClassifier";

// Curated song database with approximate vocal ranges (MIDI values).
// Range represents the notes the singer needs to hit (melody range),
// not the full orchestral range.
const SONG_DATABASE = [
  // Low range (bass/baritone)
  { title: "Ring of Fire", artist: "Johnny Cash", midiLow: 43, midiHigh: 60, genre: "Country" },
  { title: "Hallelujah", artist: "Leonard Cohen", midiLow: 45, midiHigh: 62, genre: "Folk" },
  { title: "Can't Help Falling in Love", artist: "Elvis Presley", midiLow: 47, midiHigh: 64, genre: "Pop" },
  { title: "Stand By Me", artist: "Ben E. King", midiLow: 47, midiHigh: 62, genre: "Soul" },
  { title: "House of the Rising Sun", artist: "The Animals", midiLow: 45, midiHigh: 65, genre: "Rock" },
  { title: "Unchained Melody", artist: "The Righteous Brothers", midiLow: 47, midiHigh: 67, genre: "Pop" },

  // Mid range (baritone/tenor)
  { title: "Hey Jude", artist: "The Beatles", midiLow: 50, midiHigh: 67, genre: "Rock" },
  { title: "Wonderwall", artist: "Oasis", midiLow: 50, midiHigh: 66, genre: "Rock" },
  { title: "Let It Be", artist: "The Beatles", midiLow: 48, midiHigh: 65, genre: "Rock" },
  { title: "Thinking Out Loud", artist: "Ed Sheeran", midiLow: 50, midiHigh: 69, genre: "Pop" },
  { title: "Yesterday", artist: "The Beatles", midiLow: 52, midiHigh: 67, genre: "Pop" },
  { title: "Wish You Were Here", artist: "Pink Floyd", midiLow: 48, midiHigh: 64, genre: "Rock" },
  { title: "Hotel California", artist: "Eagles", midiLow: 50, midiHigh: 67, genre: "Rock" },
  { title: "Perfect", artist: "Ed Sheeran", midiLow: 47, midiHigh: 67, genre: "Pop" },
  { title: "Someone Like You", artist: "Adele", midiLow: 50, midiHigh: 68, genre: "Pop" },

  // Higher range (tenor/alto/mezzo)
  { title: "Bohemian Rhapsody", artist: "Queen", midiLow: 48, midiHigh: 76, genre: "Rock" },
  { title: "Take Me to Church", artist: "Hozier", midiLow: 50, midiHigh: 72, genre: "Alternative" },
  { title: "Creep", artist: "Radiohead", midiLow: 52, midiHigh: 72, genre: "Alternative" },
  { title: "Shallow", artist: "Lady Gaga & Bradley Cooper", midiLow: 50, midiHigh: 74, genre: "Pop" },
  { title: "Jolene", artist: "Dolly Parton", midiLow: 55, midiHigh: 74, genre: "Country" },
  { title: "Rolling in the Deep", artist: "Adele", midiLow: 53, midiHigh: 74, genre: "Pop" },
  { title: "I Will Always Love You", artist: "Whitney Houston", midiLow: 52, midiHigh: 77, genre: "Pop" },

  // High range (mezzo/soprano)
  { title: "Chandelier", artist: "Sia", midiLow: 55, midiHigh: 79, genre: "Pop" },
  { title: "No Tears Left to Cry", artist: "Ariana Grande", midiLow: 58, midiHigh: 80, genre: "Pop" },
  { title: "Wrecking Ball", artist: "Miley Cyrus", midiLow: 55, midiHigh: 77, genre: "Pop" },
  { title: "Halo", artist: "Beyoncé", midiLow: 55, midiHigh: 79, genre: "Pop" },
];

function scoreSong(song, userMidiMin, userMidiMax) {
  // How well does this song fit the singer's range?
  const overlapLow = Math.max(song.midiLow, userMidiMin);
  const overlapHigh = Math.min(song.midiHigh, userMidiMax);
  const overlap = Math.max(0, overlapHigh - overlapLow);
  const songSpan = song.midiHigh - song.midiLow;
  if (songSpan <= 0) return 0;

  // Fraction of the song's range covered by the singer
  const coverage = overlap / songSpan;

  // Penalize songs that require notes outside the singer's range
  const overshootLow = Math.max(0, userMidiMin - song.midiLow);
  const overshootHigh = Math.max(0, song.midiHigh - userMidiMax);
  const overshootPenalty = (overshootLow + overshootHigh) / songSpan;

  // Combined score: high coverage, low overshoot
  return Math.max(0, coverage - overshootPenalty * 0.5);
}

function SongSuggestions({ results, maxSuggestions = 5 }) {
  const suggestions = useMemo(() => {
    const f0Min = results?.pitch?.f0_min ?? results?.summary?.f0_min;
    const f0Max = results?.pitch?.f0_max ?? results?.summary?.f0_max;

    if (!Number.isFinite(f0Min) || !Number.isFinite(f0Max)) return [];

    const userMidiMin = hzToMidi(f0Min);
    const userMidiMax = hzToMidi(f0Max);
    if (userMidiMin === null || userMidiMax === null) return [];

    const scored = SONG_DATABASE
      .map((song) => ({ ...song, score: scoreSong(song, userMidiMin, userMidiMax) }))
      .filter((s) => s.score >= 0.6) // At least 60% coverage
      .sort((a, b) => b.score - a.score)
      .slice(0, maxSuggestions);

    return scored;
  }, [results, maxSuggestions]);

  if (suggestions.length === 0) return null;

  return (
    <section className="song-suggestions" aria-label="Song suggestions based on your range">
      <h3 className="song-suggestions__title">Songs that fit your voice</h3>
      <p className="song-suggestions__subtitle">
        Based on your detected range, these songs should sit comfortably in your voice.
      </p>
      <ul className="song-suggestions__list">
        {suggestions.map((song) => {
          const fitPct = Math.round(song.score * 100);
          return (
            <li key={`${song.title}-${song.artist}`} className="song-suggestions__item">
              <div className="song-suggestions__info">
                <span className="song-suggestions__song-title">{song.title}</span>
                <span className="song-suggestions__artist">{song.artist}</span>
              </div>
              <div className="song-suggestions__meta">
                <span className="song-suggestions__genre">{song.genre}</span>
                <span
                  className="song-suggestions__fit"
                  style={{ color: fitPct >= 90 ? "var(--success)" : fitPct >= 75 ? "#fbbf24" : "var(--text-muted)" }}
                >
                  {fitPct}% fit
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default SongSuggestions;
