"""PDF report composition for Phase 6.4 using reportlab."""

from __future__ import annotations

from collections import Counter
import math
from typing import Any, Mapping, MutableMapping, Optional, Sequence

try:  # pragma: no cover - exercised in environments with reportlab installed
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError as exc:  # pragma: no cover
    _REPORTLAB_AVAILABLE = False
    _REPORTLAB_IMPORT_ERROR = exc
else:
    _REPORTLAB_AVAILABLE = True
    _REPORTLAB_IMPORT_ERROR = None

from reporting._helpers import (
    _safe_float,
    _ensure_mapping,
    _coerce_sequence,
    _first_float,
    _format_number,
    _format_band,
    _extract_frames,
)


def _frame_time(frame: Mapping[str, Any], index: int, metadata: Mapping[str, Any]) -> float:
    for key in ("time", "timestamp", "time_s", "t"):
        value = _safe_float(frame.get(key))
        if value is not None:
            return value
    frame_rate = _safe_float(metadata.get("frame_rate"))
    if frame_rate and frame_rate > 0:
        return float(index / frame_rate)
    sample_rate = _safe_float(metadata.get("sample_rate"))
    hop_length = _first_float(metadata, ("hop_length", "frame_hop"))
    if sample_rate and hop_length:
        return float(index * hop_length / sample_rate)
    return float(index)


def _estimate_duration(result: Mapping[str, Any]) -> Optional[float]:
    metadata = _ensure_mapping(result.get("metadata") if isinstance(result, Mapping) else {})
    for key in ("duration", "duration_s", "audio_duration", "length_s"):
        value = _safe_float(metadata.get(key))
        if value is not None:
            return value
    frames = _extract_frames(result if isinstance(result, Mapping) else {})
    if not frames:
        return None
    last_time = _frame_time(frames[-1], len(frames) - 1, metadata)
    return last_time


def _extract_events(result: Mapping[str, Any], *path: str) -> list[Mapping[str, Any]]:
    current: Any = result
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return []
        current = current[key]
    if not isinstance(current, Sequence) or isinstance(current, (str, bytes)):
        return []
    return [item for item in current if isinstance(item, Mapping)]


def _event_label(event: Mapping[str, Any]) -> Optional[str]:
    label = event.get("label") or event.get("chord") or event.get("key") or event.get("name")
    return str(label) if label is not None else None


def _event_start(event: Mapping[str, Any]) -> Optional[float]:
    return _first_float(event, ("start", "time", "t"))


def _event_end(event: Mapping[str, Any]) -> Optional[float]:
    return _safe_float(event.get("end"))


def _event_confidence(event: Mapping[str, Any]) -> Optional[float]:
    return _first_float(event, ("confidence", "probability"))


def _summarize_timeline(events: Sequence[Mapping[str, Any]], *, label: str) -> tuple[str, list[list[str]]]:
    if not events:
        return f"No {label} data available.", [["No data", "", "", ""]]
    durations: dict[str, float] = {}
    counts: Counter[str] = Counter()
    rows: list[list[str]] = [["Start", "End", "Label", "Confidence"]]
    for event in events:
        event_label = _event_label(event)
        if event_label:
            counts[event_label] += 1
        start = _event_start(event)
        end = _event_end(event)
        if start is not None and end is not None and end >= start and event_label:
            durations[event_label] = durations.get(event_label, 0.0) + (end - start)
        rows.append(
            [
                _format_number(start),
                _format_number(end),
                event_label or "N/A",
                _format_number(_event_confidence(event)),
            ]
        )
    summary_parts: list[str] = []
    if durations:
        top = sorted(durations.items(), key=lambda item: item[1], reverse=True)[:5]
        summary_parts.append(
            "Longest duration: " + ", ".join(f"{name} ({_format_number(value)}s)" for name, value in top)
        )
    if counts:
        top_counts = counts.most_common(5)
        summary_parts.append(
            "Most frequent: " + ", ".join(f"{name} ({count})" for name, count in top_counts)
        )
    summary_text = " ".join(summary_parts) if summary_parts else f"{label.title()} data available."
    return summary_text, rows


def _extract_tessitura_metrics(result: Mapping[str, Any]) -> Mapping[str, Any]:
    tessitura = result.get("tessitura") if isinstance(result, Mapping) else None
    if not isinstance(tessitura, Mapping):
        return {}
    metrics = tessitura.get("metrics") if isinstance(tessitura, Mapping) else None
    if isinstance(metrics, Mapping):
        return metrics
    return tessitura


def _extract_uncertainty(result: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    bounds = result.get("uncertainty") or result.get("uncertainties") or result.get("uncertainty_bounds")
    if isinstance(bounds, Mapping):
        return bounds
    return {}


def _format_uncertainty_pitch(value: Any) -> str:
    if isinstance(value, Mapping):
        for low_key, high_key in (("min", "max"), ("low", "high"), ("lower", "upper")):
            if low_key in value or high_key in value:
                return f"{_format_number(value.get(low_key))} to {_format_number(value.get(high_key))}"
        return ", ".join(f"{key}: {_format_number(val)}" for key, val in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) >= 2:
            return f"{_format_number(value[0])} to {_format_number(value[1])}"
        if len(value) == 1:
            return _format_number(value[0])
    return _format_number(value)


def _build_table(data: list[list[str]]) -> Table:
    table = Table(data, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def generate_pdf_report(result: Mapping[str, Any], output_path: Optional[str] = None) -> str:
    """Generate Phase 6.4 PDF report and write it to disk."""
    if not _REPORTLAB_AVAILABLE:
        raise ImportError(
            "reportlab is required for PDF report composition. Install it with 'pip install reportlab'."
        ) from _REPORTLAB_IMPORT_ERROR
    if not output_path:
        raise ValueError("output_path is required to write a PDF report.")

    metadata = _ensure_mapping(result.get("metadata") if isinstance(result, Mapping) else {})
    tessitura_metrics = _extract_tessitura_metrics(result)
    chord_events = _extract_events(result, "chords", "timeline")
    key_events = _extract_events(result, "keys", "trajectory")
    uncertainty = _extract_uncertainty(result)

    duration = _estimate_duration(result)
    tessitura_band = tessitura_metrics.get("tessitura_band")
    comfort_band = tessitura_metrics.get("comfort_band")

    chord_summary, chord_rows = _summarize_timeline(chord_events, label="chord progression")
    key_summary, key_rows = _summarize_timeline(key_events, label="key trajectory")

    styles = getSampleStyleSheet()
    title_style: ParagraphStyle = styles["Title"]
    heading_style: ParagraphStyle = styles["Heading1"]
    subheading_style: ParagraphStyle = styles["Heading2"]
    body_style: ParagraphStyle = styles["BodyText"]

    story: list[Any] = []
    story.append(Paragraph("Vocal Analysis Report", title_style))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Executive Summary", heading_style))
    summary_rows = [
        ["Metric", "Value"],
        ["Source", str(metadata.get("source") or "N/A")],
        ["Analysis version", str(metadata.get("analysis_version") or "N/A")],
        ["Duration (s)", _format_number(duration)],
        ["Vocal range (MIDI)", _format_band((tessitura_metrics.get("range_min"), tessitura_metrics.get("range_max")))],
        ["Tessitura band (MIDI)", _format_band(tessitura_band)],
        ["Comfort band (MIDI)", _format_band(comfort_band)],
    ]
    story.append(_build_table(summary_rows))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Vocal Range & Tessitura", heading_style))
    tessitura_rows = [
        ["Metric", "Value"],
        ["Range min", _format_number(tessitura_metrics.get("range_min"))],
        ["Range max", _format_number(tessitura_metrics.get("range_max"))],
        ["Tessitura band", _format_band(tessitura_band)],
        ["Comfort band", _format_band(comfort_band)],
        ["Comfort center", _format_number(tessitura_metrics.get("comfort_center"))],
        ["Std dev", _format_number(tessitura_metrics.get("std_dev"))],
        ["Mean variance", _format_number(tessitura_metrics.get("mean_variance"))],
    ]
    story.append(_build_table(tessitura_rows))
    strain_zones = _coerce_sequence(tessitura_metrics.get("strain_zones"))
    if strain_zones:
        zones_text = "; ".join(
            f"{zone.get('label', 'zone')} ({_format_number(zone.get('low'))} to {_format_number(zone.get('high'))}): {zone.get('reason', '')}"
            if isinstance(zone, Mapping)
            else str(zone)
            for zone in strain_zones
        )
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Strain zones: {zones_text}", body_style))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Key Analysis", heading_style))
    story.append(Paragraph(key_summary, body_style))
    story.append(Spacer(1, 6))
    story.append(_build_table(key_rows[:12]))
    story.append(PageBreak())

    story.append(Paragraph("Chord Progression", heading_style))
    story.append(Paragraph(chord_summary, body_style))
    story.append(Spacer(1, 6))
    story.append(_build_table(chord_rows[:12]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Technical Appendix: Uncertainties", heading_style))
    pitch_bounds = (
        uncertainty.get("pitch")
        or uncertainty.get("midi")
        or uncertainty.get("f0")
        or uncertainty.get("pitch_bounds")
    )
    confidence_intervals = uncertainty.get("confidence_intervals") or uncertainty.get("ci")
    appendix_rows = [
        ["Metric", "Value"],
        ["Pitch bounds", _format_uncertainty_pitch(pitch_bounds)],
        ["Confidence intervals", _format_uncertainty_pitch(confidence_intervals)],
    ]
    story.append(_build_table(appendix_rows))

    doc = SimpleDocTemplate(output_path, pagesize=letter, title="Vocal Analysis Report")
    doc.build(story)
    return output_path


def generate_comparison_pdf_report(
    session_report: dict,
    output_path: str,
) -> str:
    """Generate a PDF vocal coaching comparison report from a session report.

    Sections:

    1. Session overview (reference track, duration, date)
    2. Pitch accuracy (mean error, accuracy ratio, bias, stability)
    3. Rhythm accuracy (note hit rate, mean onset error, rhythmic consistency)
    4. Range comparison (overlap, coverage, tessitura offset)
    5. Formant/timbre (if data available)
    6. Coaching recommendations (generated from metrics, quantitative statements only)

    Args:
        session_report: Dict from ``session_report_to_dict()`` or WS
            ``session_report`` message.
        output_path: Path to write the PDF.

    Returns:
        The *output_path* string.
    """
    if not _REPORTLAB_AVAILABLE:
        raise ImportError(
            "reportlab is required for PDF report composition. "
            "Install it with 'pip install reportlab'."
        ) from _REPORTLAB_IMPORT_ERROR

    from pathlib import Path

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    pitch = _ensure_mapping(session_report.get("pitch_comparison"))
    rhythm = _ensure_mapping(session_report.get("rhythm_comparison"))
    rng = _ensure_mapping(session_report.get("range_comparison"))
    formants = _ensure_mapping(session_report.get("formant_comparison"))

    styles = getSampleStyleSheet()
    title_style: ParagraphStyle = styles["Title"]
    heading_style: ParagraphStyle = styles["Heading1"]
    body_style: ParagraphStyle = styles["BodyText"]

    story: list[Any] = []

    # --- Title ---
    story.append(Paragraph("Vocal Comparison Report", title_style))
    story.append(Spacer(1, 12))

    # --- Section 1: Session Overview ---
    story.append(Paragraph("Session Overview", heading_style))
    ref_source = str(session_report.get("reference_source") or "N/A")
    ref_source_id = str(session_report.get("reference_source_id") or "N/A")
    ref_key = str(session_report.get("reference_key") or "N/A")
    started_at = str(session_report.get("session_started_at") or "N/A")
    duration_s = _safe_float(session_report.get("session_duration_s"))
    total_chunks = session_report.get("total_chunks_processed")
    voiced_chunks = session_report.get("voiced_chunks")

    overview_rows = [
        ["Field", "Value"],
        ["Reference source", ref_source],
        ["Reference file / ID", ref_source_id],
        ["Reference key", ref_key],
        ["Session started", started_at],
        ["Duration (s)", _format_number(duration_s)],
        ["Total chunks processed", str(total_chunks) if total_chunks is not None else "N/A"],
        ["Voiced chunks", str(voiced_chunks) if voiced_chunks is not None else "N/A"],
    ]
    story.append(_build_table(overview_rows))
    story.append(Spacer(1, 12))

    # --- Section 2: Pitch Accuracy ---
    story.append(Paragraph("Pitch Accuracy", heading_style))
    pitch_rows = [
        ["Metric", "Value"],
        ["Mean absolute pitch error (cents)", _format_number(pitch.get("mean_absolute_pitch_error_cents"))],
        ["Pitch accuracy ratio (within ±50 ct)", _format_number(pitch.get("pitch_accuracy_ratio"))],
        ["Pitch bias (cents, + = sharp)", _format_number(pitch.get("pitch_bias_cents"))],
        ["Pitch stability / std dev (cents)", _format_number(pitch.get("pitch_stability_cents"))],
        ["Voiced frame count", _format_number(pitch.get("voiced_frame_count"))],
    ]
    story.append(_build_table(pitch_rows))
    mape = _safe_float(pitch.get("mean_absolute_pitch_error_cents"))
    if mape is not None:
        if mape <= 25.0:
            pitch_feedback = f"Mean pitch error of {mape:.1f} cents — within target of ±25 cents."
        elif mape <= 50.0:
            pitch_feedback = f"Mean pitch error of {mape:.1f} cents — slightly above target of ±25 cents."
        else:
            pitch_feedback = f"Mean pitch error of {mape:.1f} cents — significantly above target of ±25 cents."
        story.append(Spacer(1, 6))
        story.append(Paragraph(pitch_feedback, body_style))
    story.append(Spacer(1, 12))

    # --- Section 3: Rhythm Accuracy ---
    story.append(Paragraph("Rhythm Accuracy", heading_style))
    hit_rate = _safe_float(rhythm.get("note_hit_rate"))
    matched = rhythm.get("matched_note_count")
    ref_notes = rhythm.get("reference_note_count")
    rhythm_rows = [
        ["Metric", "Value"],
        ["Note hit rate", _format_number(hit_rate)],
        ["Matched / reference notes",
         f"{matched} / {ref_notes}" if matched is not None and ref_notes is not None else "N/A"],
        ["Mean onset error (ms)", _format_number(rhythm.get("mean_onset_error_ms"))],
        ["Rhythmic consistency / std dev (ms)", _format_number(rhythm.get("rhythmic_consistency_ms"))],
    ]
    story.append(_build_table(rhythm_rows))
    if hit_rate is not None and ref_notes:
        moe_ms = _safe_float(rhythm.get("mean_onset_error_ms")) or 0.0
        tol = 150.0  # onset_tolerance_s * 1000
        within = "within" if moe_ms <= tol else "outside"
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"{hit_rate * 100:.1f}% of reference notes were matched. "
            f"Mean onset error {moe_ms:.1f} ms — {within} the {tol:.0f} ms onset tolerance.",
            body_style,
        ))
    story.append(Spacer(1, 12))

    # --- Section 4: Vocal Range ---
    story.append(Paragraph("Vocal Range Comparison", heading_style))
    range_rows = [
        ["Metric", "Value"],
        ["User range min (MIDI)", _format_number(rng.get("user_range_min_midi"))],
        ["User range max (MIDI)", _format_number(rng.get("user_range_max_midi"))],
        ["Reference range min (MIDI)", _format_number(rng.get("reference_range_min_midi"))],
        ["Reference range max (MIDI)", _format_number(rng.get("reference_range_max_midi"))],
        ["Range overlap (semitones)", _format_number(rng.get("range_overlap_semitones"))],
        ["Range coverage ratio", _format_number(rng.get("range_coverage_ratio"))],
        ["Tessitura center offset (semitones)", _format_number(rng.get("tessitura_center_offset_semitones"))],
        ["Out-of-range note fraction", _format_number(rng.get("out_of_range_note_fraction"))],
    ]
    story.append(_build_table(range_rows))
    coverage = _safe_float(rng.get("range_coverage_ratio"))
    if coverage is not None:
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"Your observed range covered {coverage * 100:.1f}% of the reference pitch range.",
            body_style,
        ))
    story.append(Spacer(1, 12))

    # --- Section 5: Formant / Timbre ---
    story.append(Paragraph("Formant / Timbre", heading_style))
    formant_available = formants.get("formant_data_available", False)
    if formant_available:
        formant_rows = [
            ["Metric", "Value"],
            ["Mean F1 deviation (Hz)", _format_number(formants.get("mean_f1_deviation_hz"))],
            ["Mean F2 deviation (Hz)", _format_number(formants.get("mean_f2_deviation_hz"))],
            ["Spectral centroid deviation (Hz)", _format_number(formants.get("spectral_centroid_deviation_hz"))],
        ]
        story.append(_build_table(formant_rows))
    else:
        story.append(Paragraph(
            "Formant comparison is unavailable in live streaming mode. "
            "Upload the recorded audio for a full formant/timbre analysis.",
            body_style,
        ))
    story.append(Spacer(1, 12))

    # --- Section 6: Coaching Recommendations ---
    story.append(Paragraph("Coaching Recommendations", heading_style))
    coaching_lines: list[str] = []
    if mape is not None:
        coaching_lines.append(
            f"• Pitch: Mean pitch error {mape:.1f} cents — "
            + ("within target range (±25 ct)." if mape <= 25.0 else
               "slightly above target (±25 ct); focus on intonation control." if mape <= 50.0 else
               "significantly above target (±25 ct); intensive pitch training recommended.")
        )
    if hit_rate is not None:
        coaching_lines.append(
            f"• Rhythm: {hit_rate * 100:.1f}% of reference notes matched — "
            + ("excellent rhythmic alignment." if hit_rate >= 0.8 else
               "adequate rhythmic alignment; work on note onset timing." if hit_rate >= 0.5 else
               "significant rhythmic misalignment; use a metronome and slow practice.")
        )
    if coverage is not None:
        coaching_lines.append(
            f"• Range: {coverage * 100:.1f}% reference range covered — "
            + ("good range match." if coverage >= 0.7 else
               "partial range coverage; work on extending into missed areas.")
        )
    for line in coaching_lines:
        story.append(Paragraph(line, body_style))

    doc = SimpleDocTemplate(output_path, pagesize=letter, title="Vocal Comparison Report")
    doc.build(story)
    return output_path


__all__ = ["generate_pdf_report", "generate_comparison_pdf_report"]