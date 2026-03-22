/**
 * GlossaryTerm - Tooltip component for technical terms
 * Wraps text with a hover/tap popover showing a definition
 */

import { useState, useRef, useEffect } from "react";

const GLOSSARY = {
  tessitura: {
    label: "Tessitura",
    definition:
      "The range of pitches where your voice is most comfortable and resonant — not your absolute highest or lowest note, but where you sing most naturally.",
  },
  f0: {
    label: "F0 / Fundamental Frequency",
    definition:
      "The basic pitch of your voice, measured in Hz (cycles per second). Middle C is about 262 Hz.",
  },
  cents: {
    label: "Cents",
    definition:
      "A unit for measuring tiny pitch differences. 100 cents = 1 semitone (one piano key). Being within ±25 cents is considered good tuning.",
  },
  formant: {
    label: "Formant",
    definition:
      "Resonant frequencies in your vocal tract that give your voice its unique timbre (tone color). F1 and F2 are the two most important.",
  },
  vibrato: {
    label: "Vibrato",
    definition:
      "A natural, regular wavering of pitch that adds warmth and expression to sustained notes.",
  },
  inferential_statistics: {
    label: "Inferential Statistics",
    definition:
      "Mathematical tools that estimate how reliable a measurement is. They help distinguish real patterns from random variation.",
  },
  confidence_interval: {
    label: "Confidence Interval",
    definition:
      "A range of values that likely contains the true measurement. A 95% CI means we are 95% sure the true value falls in this range.",
  },
  p_value: {
    label: "p-value",
    definition:
      "A number between 0 and 1 indicating whether a difference is statistically meaningful. Values below 0.05 are typically considered significant.",
  },
  vocal_separation: {
    label: "AI Vocal Separation",
    definition:
      "An AI process that isolates your voice from background music or instruments before analysis, improving accuracy.",
  },
  dtw: {
    label: "DTW Alignment",
    definition:
      "Dynamic Time Warping — a technique that aligns two recordings even if they have slightly different tempos, for fair comparison.",
  },
  spectral_centroid: {
    label: "Spectral Centroid",
    definition:
      "The 'center of mass' of the sound's frequency content. A higher value means a brighter, more forward tone.",
  },
};

function GlossaryTerm({ term, children }) {
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const buttonRef = useRef(null);
  const tooltipRef = useRef(null);

  const glossaryEntry = GLOSSARY[term];
  if (!glossaryEntry) {
    return <>{children}</>;
  }

  const tooltipId = `glossary-tooltip-${term}`;

  useEffect(() => {
    if (!isOpen || !buttonRef.current || !tooltipRef.current) return;

    const buttonRect = buttonRef.current.getBoundingClientRect();
    const tooltipRect = tooltipRef.current.getBoundingClientRect();

    // Position tooltip above the button, centered
    let top = buttonRect.top - tooltipRect.height - 8;
    let left = buttonRect.left + buttonRect.width / 2 - tooltipRect.width / 2;

    // Clamp to viewport
    if (left < 8) left = 8;
    if (left + tooltipRect.width > window.innerWidth - 8) {
      left = window.innerWidth - tooltipRect.width - 8;
    }
    if (top < 8) {
      top = buttonRect.bottom + 8;
    }

    setPosition({ top: Math.round(top), left: Math.round(left) });
  }, [isOpen]);

  const handleKeyDown = (e) => {
    if (e.key === "Escape") {
      setIsOpen(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen]);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="glossary-term"
        onClick={() => setIsOpen(!isOpen)}
        onBlur={() => setTimeout(() => setIsOpen(false), 100)}
        aria-describedby={tooltipId}
        aria-expanded={isOpen}
      >
        {children}
      </button>

      {isOpen && (
        <div
          ref={tooltipRef}
          id={tooltipId}
          className="glossary-tooltip"
          role="tooltip"
          style={{
            position: "fixed",
            top: `${position.top}px`,
            left: `${position.left}px`,
            zIndex: 1000,
          }}
          onClick={() => setIsOpen(false)}
        >
          <p className="glossary-tooltip__label">{glossaryEntry.label}</p>
          <p className="glossary-tooltip__definition">{glossaryEntry.definition}</p>
        </div>
      )}
    </>
  );
}

export default GlossaryTerm;
