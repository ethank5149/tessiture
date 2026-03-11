/**
 * PracticeGuidance - Displays practice guidance cards
 * Shows plain-language coaching steps for next-session decisions
 */

import { useMemo } from "react";
import {
  formatMidiNote,
  formatTimestampLabel,
  summarizeTimeEffort,
  summarizeRangeEffort,
  summarizePitchControl,
  calculateSemitoneSpan,
} from "./AnalysisFormatters";

function PracticeGuidance({ results, evidence }) {
  const guidanceCards = useMemo(() => {
    const defaultPractice =
      "Practice the section that felt hardest at a slower tempo (about 70%) and repeat it three times.";

    const timeEffortSummary = summarizeTimeEffort(results);
    const rangeEffortSummary = summarizeRangeEffort(results);
    const pitchControlSummary = summarizePitchControl(results);
    const f0Min = results?.pitch?.f0_min ?? results?.summary?.f0_min ?? results?.summary?.min_f0;
    const f0Max = results?.pitch?.f0_max ?? results?.summary?.f0_max ?? results?.summary?.max_f0;
    const semitoneSpan = calculateSemitoneSpan(Number(f0Min), Number(f0Max));

    let practiceNextAnswer = defaultPractice;
    if (pitchControlSummary?.averageStep >= 1.5) {
      practiceNextAnswer =
        "Practice smooth note-to-note slides for 5 minutes, then repeat your hardest phrase slowly to reduce sudden pitch jumps.";
    } else if (pitchControlSummary?.trendLabel === "rising" || pitchControlSummary?.trendLabel === "falling") {
      practiceNextAnswer =
        `Your pitch trend was ${pitchControlSummary.trendLabel}. Repeat one phrase at a comfortable key and keep the final note centered.`;
    } else if (timeEffortSummary?.mostActiveSegment?.label) {
      practiceNextAnswer =
        `Start with the ${timeEffortSummary.mostActiveSegment.label.toLowerCase()} of the recording, since that section carried most of your effort.`;
    }

    let effortAnswer =
      "We could not detect enough pitch activity to map effort by time or range in this recording.";
    if (timeEffortSummary?.mostActiveSegment?.label) {
      const effortPct = Math.round((timeEffortSummary.mostActiveSegment.ratio ?? 0) * 100);
      effortAnswer =
        `Most effort was in the ${timeEffortSummary.mostActiveSegment.label.toLowerCase()} of the recording (${effortPct}% of detected voiced time).`;
    } else if (rangeEffortSummary?.mostUsedBand?.label) {
      const effortPct = Math.round((rangeEffortSummary.mostUsedBand.ratio ?? 0) * 100);
      effortAnswer =
        `Most effort was in your ${rangeEffortSummary.mostUsedBand.label} (${effortPct}% of detected range usage).`;
    }

    let effortDetail = null;
    if (timeEffortSummary) {
      effortDetail =
        `Detected pitch span in this take: ${formatMidiNote(timeEffortSummary.minMidi)} to ${formatMidiNote(timeEffortSummary.maxMidi)}.`;
    }

    let adjustmentAnswer =
      "Use one small adjustment next time: take a full breath before each phrase and keep volume comfortable.";
    if (Number.isFinite(semitoneSpan) && semitoneSpan >= 12) {
      adjustmentAnswer =
        "Add one recovery reset after each high phrase (easy middle-range hum, then continue) to reduce fatigue in wide-range passages.";
    } else if (rangeEffortSummary?.upperBandRatio >= 0.35) {
      adjustmentAnswer =
        "Alternate each high phrase with one easy middle-range phrase so your voice can reset between upper-range efforts.";
    } else if (Number.isFinite(semitoneSpan) && semitoneSpan < 7) {
      adjustmentAnswer =
        "Add one gentle higher pass and one gentle lower pass to expand control beyond today's narrow range.";
    } else if (pitchControlSummary?.averageStep >= 1.5) {
      adjustmentAnswer =
        "Reduce tempo by about 10% on the hardest phrase to smooth transitions between notes.";
    }

    return [
      {
        question: "What should I practice next?",
        answer: practiceNextAnswer,
      },
      {
        question: "Where did I spend most effort?",
        answer: effortAnswer,
        detail: effortDetail,
      },
      {
        question: "What one adjustment should I make next session?",
        answer: adjustmentAnswer,
      },
    ];
  }, [results]);

  const evidenceEventMap = useMemo(() => {
    const map = new Map();
    (evidence.events || []).forEach((event) => {
      if (typeof event.id === "string" && event.id.trim()) {
        map.set(event.id, event);
      }
    });
    return map;
  }, [evidence]);

  const hasAudioReference = Boolean(results?.metadata?.audio_source_url);

  return (
    <section className="results__section results__section--guidance" aria-label="Practice guidance cards">
      <div className="results__section-header">
        <h3 className="results__section-title">Practice guidance</h3>
        <p className="results__section-meta">
          This on-screen analysis is text-only with no plots or graphs; use these plain-language coaching steps for next-session decisions. Detailed plots remain available only in PDF export.
        </p>
      </div>
      <ol className="results__guidance-list" aria-label="Practice action steps">
        {evidence.guidance.length
          ? evidence.guidance.map((item, index) => {
              const refs = Array.isArray(item.evidence_refs)
                ? item.evidence_refs.filter((ref) => typeof ref === "string")
                : [];
              return (
                <li key={item.id ?? `evidence-guidance-${index}`} className="guidance-card">
                  <h4 className="guidance-card__question">Guidance {index + 1}</h4>
                  <p className="guidance-card__answer"><strong>Claim:</strong> {item.claim ?? "—"}</p>
                  <p className="guidance-card__detail"><strong>Why:</strong> {item.why ?? "—"}</p>
                  <p className="guidance-card__detail"><strong>Action:</strong> {item.action ?? "—"}</p>
                  {refs.length ? (
                    <ul className="guidance-card__evidence" aria-label="Evidence references">
                      {refs.map((ref) => {
                        const event = evidenceEventMap.get(ref);
                        const timestampLabel = event?.timestamp_label ?? formatTimestampLabel(event?.timestamp_s);
                        return (
                          <li key={ref} className="guidance-card__evidence-item">
                            <span>
                              {event?.label ?? ref} ({timestampLabel})
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  ) : null}
                </li>
              );
            })
          : guidanceCards.map((card) => (
              <li key={card.question} className="guidance-card">
                <h4 className="guidance-card__question">{card.question}</h4>
                <p className="guidance-card__answer">{card.answer}</p>
                {card.detail ? <p className="guidance-card__detail">{card.detail}</p> : null}
              </li>
            ))}
      </ol>
    </section>
  );
}

export default PracticeGuidance;
