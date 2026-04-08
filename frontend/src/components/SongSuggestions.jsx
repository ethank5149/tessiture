/**
 * SongSuggestions — Recommends songs that fit the singer's range.
 *
 * Now powered by a 150+ song database with genre and difficulty filters.
 * Replaces the old inline 25-song list.
 */

import { useMemo, useState } from "react";
import { hzToMidi } from "./VoiceTypeClassifier";
import SONG_DATABASE, { ALL_GENRES, DIFFICULTY_LABELS } from "./songDatabase";

function scoreSong(song, userMidiMin, userMidiMax) {
  const overlapLow = Math.max(song.midiLow, userMidiMin);
  const overlapHigh = Math.min(song.midiHigh, userMidiMax);
  const overlap = Math.max(0, overlapHigh - overlapLow);
  const songSpan = song.midiHigh - song.midiLow;
  if (songSpan <= 0) return 0;

  const coverage = overlap / songSpan;
  const overshootLow = Math.max(0, userMidiMin - song.midiLow);
  const overshootHigh = Math.max(0, song.midiHigh - userMidiMax);
  const overshootPenalty = (overshootLow + overshootHigh) / songSpan;

  return Math.max(0, coverage - overshootPenalty * 0.5);
}

function SongSuggestions({ results, maxSuggestions = 10 }) {
  const [genreFilter, setGenreFilter] = useState("all");
  const [difficultyFilter, setDifficultyFilter] = useState("all");
  const [showAll, setShowAll] = useState(false);

  const { userMidiMin, userMidiMax } = useMemo(() => {
    const f0Min = results?.pitch?.f0_min ?? results?.summary?.f0_min;
    const f0Max = results?.pitch?.f0_max ?? results?.summary?.f0_max;
    if (!Number.isFinite(f0Min) || !Number.isFinite(f0Max)) return { userMidiMin: null, userMidiMax: null };
    return { userMidiMin: hzToMidi(f0Min), userMidiMax: hzToMidi(f0Max) };
  }, [results]);

  const allSuggestions = useMemo(() => {
    if (userMidiMin === null || userMidiMax === null) return [];

    return SONG_DATABASE
      .map((song) => ({ ...song, score: scoreSong(song, userMidiMin, userMidiMax) }))
      .filter((s) => s.score >= 0.5)
      .sort((a, b) => b.score - a.score);
  }, [userMidiMin, userMidiMax]);

  const filteredSuggestions = useMemo(() => {
    let list = allSuggestions;
    if (genreFilter !== "all") {
      list = list.filter((s) => s.genre === genreFilter);
    }
    if (difficultyFilter !== "all") {
      list = list.filter((s) => s.difficulty === Number(difficultyFilter));
    }
    return list;
  }, [allSuggestions, genreFilter, difficultyFilter]);

  const displayedSuggestions = showAll
    ? filteredSuggestions
    : filteredSuggestions.slice(0, maxSuggestions);

  // Only show genres that have matches
  const availableGenres = useMemo(() => {
    const genres = new Set(allSuggestions.map((s) => s.genre));
    return ALL_GENRES.filter((g) => genres.has(g));
  }, [allSuggestions]);

  if (allSuggestions.length === 0) return null;

  return (
    <section className="song-suggestions" aria-label="Song suggestions based on your range">
      <h3 className="song-suggestions__title">Songs that fit your voice</h3>
      <p className="song-suggestions__subtitle">
        Based on your detected range — {allSuggestions.length} songs match.
        {allSuggestions.length > maxSuggestions && " Filter by genre or difficulty to narrow down."}
      </p>

      <div className="song-suggestions__filters">
        <label className="song-suggestions__filter">
          <span className="song-suggestions__filter-label">Genre</span>
          <select
            value={genreFilter}
            onChange={(e) => setGenreFilter(e.target.value)}
            className="song-suggestions__select"
          >
            <option value="all">All genres</option>
            {availableGenres.map((g) => (
              <option key={g} value={g}>{g}</option>
            ))}
          </select>
        </label>
        <label className="song-suggestions__filter">
          <span className="song-suggestions__filter-label">Difficulty</span>
          <select
            value={difficultyFilter}
            onChange={(e) => setDifficultyFilter(e.target.value)}
            className="song-suggestions__select"
          >
            <option value="all">Any</option>
            <option value="1">Beginner</option>
            <option value="2">Intermediate</option>
            <option value="3">Advanced</option>
          </select>
        </label>
      </div>

      {filteredSuggestions.length === 0 ? (
        <p className="song-suggestions__empty">No matches for these filters. Try broadening your search.</p>
      ) : (
        <>
          <ul className="song-suggestions__list">
            {displayedSuggestions.map((song) => {
              const fitPct = Math.round(song.score * 100);
              return (
                <li key={`${song.title}-${song.artist}`} className="song-suggestions__item">
                  <div className="song-suggestions__info">
                    <span className="song-suggestions__song-title">{song.title}</span>
                    <span className="song-suggestions__artist">{song.artist}</span>
                  </div>
                  <div className="song-suggestions__meta">
                    <span className="song-suggestions__genre">{song.genre}</span>
                    <span className="song-suggestions__difficulty" data-level={song.difficulty}>
                      {DIFFICULTY_LABELS[song.difficulty]}
                    </span>
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
          {!showAll && filteredSuggestions.length > maxSuggestions && (
            <button
              type="button"
              className="button song-suggestions__show-more"
              onClick={() => setShowAll(true)}
            >
              Show all {filteredSuggestions.length} matches
            </button>
          )}
        </>
      )}
    </section>
  );
}

export default SongSuggestions;
