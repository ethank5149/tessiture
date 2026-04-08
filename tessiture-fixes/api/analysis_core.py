from __future__ import annotations

import base64
import logging
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional
from uuid import uuid4

import numpy as np

# Import from analysis modules
from analysis.advanced.formants import estimate_formants_from_audio
from analysis.advanced.phrase_segmentation import segment_phrases_from_audio
from analysis.advanced.vibrato import detect_vibrato
from analysis.chords.key_detector import detect_key, detect_key_trajectory
from analysis.dsp.peak_detection import detect_harmonics
from analysis.dsp.preprocessing import preprocess_audio
from analysis.dsp.stft import compute_stft
from analysis.dsp.vocal_separation import is_available as _vocal_separation_available
from analysis.pitch.estimator import estimate_pitch_frames
from analysis.pitch.midi_converter import convert_f0_to_midi
from analysis.pitch.path_optimizer import optimize_lead_voice
from analysis.tessitura.analyzer import analyze_tessitura
from calibration.monte_carlo.uncertainty_analyzer import summarize_uncertainty
from reporting import generate_csv_report, generate_json_report, generate_pdf_report

# Import from api modules
from api import config, logging_config
from api.evidence import _build_chord_timeline, _build_evidence_payload
from api.pitch_utils import (
    _build_note_events,
    _build_pitch_payload,
    _extract_pitch_frame_diagnostics,
    _summarize_pitch_method_diagnostics,
)
from api.serializers import (
    _build_summary,
    _serialize_tessitura_payload,
    _summarize_formants,
    _summarize_phrases,
)
from api.stats import (
    _build_calibration_summary,
    _build_inferential_statistics,
    _build_reference_calibration_uncertainty,
)
from api.utils import _ensure_output_dir, _is_voiced_frame, _safe_float

# Re-export config constants used by the pipeline
TARGET_SAMPLE_RATE = config.TARGET_SAMPLE_RATE
STFT_NFFT = config.STFT_NFFT
STFT_HOP = config.STFT_HOP
OUTPUT_DIR = config.OUTPUT_DIR
_VOCAL_SEPARATION_MODE = config._VOCAL_SEPARATION_MODE
_STEM_CACHE_DIR = config._STEM_CACHE_DIR
_SPECT_FREQ_MIN_HZ = config._SPECT_FREQ_MIN_HZ
_SPECT_FREQ_MAX_HZ = config._SPECT_FREQ_MAX_HZ

logger = logging.getLogger(__name__)


def _decode_audio_file(file_path: str) -> tuple[np.ndarray, int]:
    try:
        import librosa
    except Exception as exc:  # pragma: no cover - dependency/environment guard
        raise RuntimeError("librosa is required for audio decoding.") from exc

    suffix = Path(file_path).suffix.lower()
    try:
        audio, sample_rate = librosa.load(file_path, sr=None, mono=False)
    except Exception as exc:
        if suffix == ".opus":
            raise RuntimeError(
                "Failed to decode Opus audio. Ensure FFmpeg or libsndfile with Opus support is "
                "installed and the input is a valid Opus stream."
            ) from exc
        raise RuntimeError(f"Failed to decode audio file '{Path(file_path).name}'.") from exc

    return np.asarray(audio), int(sample_rate)


def _noop_progress_update(
    _progress: int,
    _stage: Optional[str] = None,
    _message: Optional[str] = None,
) -> None:
    return


def _resolve_progress_update(
    metadata: Optional[Mapping[str, Any]],
) -> Callable[[int, Optional[str], Optional[str]], None]:
    callback = metadata.get("_progress_callback") if isinstance(metadata, Mapping) else None
    if not callable(callback):
        return _noop_progress_update

    log_context = {
        "filename": metadata.get("filename") if isinstance(metadata, Mapping) else None,
        "source": metadata.get("source") if isinstance(metadata, Mapping) else None,
        "example_id": metadata.get("example_id") if isinstance(metadata, Mapping) else None,
    }

    def _safe_progress_update(
        progress: int, stage: Optional[str] = None, message: Optional[str] = None
    ) -> None:
        logger.info(
            "analysis_progress_emit progress=%s stage=%s message=%s context=%s",
            progress,
            stage,
            message,
            log_context,
        )
        try:
            callback(progress, stage, message)
        except Exception:
            logger.debug("progress_update_callback_failed", exc_info=True)

    return _safe_progress_update


def _run_analysis_pipeline(
    file_path: str, metadata: Optional[Mapping[str, Any]] = None
) -> Dict[str, Any]:
    _ensure_output_dir()
    warnings: List[str] = []
    report_progress = _resolve_progress_update(metadata)
    report_progress(5, "starting", "Initializing analysis pipeline.")

    # Get job logger if job_id is in metadata
    job_id = metadata.get("job_id") if metadata else None
    job_logger = logging_config.get_job_logger(job_id) if job_id else None

    if job_logger:
        job_logger.info(
            "Analysis pipeline starting: file_path=%s, filename=%s, source=%s",
            file_path,
            metadata.get("filename") if isinstance(metadata, Mapping) else None,
            metadata.get("source") if isinstance(metadata, Mapping) else None,
        )

    logger.info(
        "analysis_pipeline_start file_path=%s filename=%s source=%s example_id=%s",
        file_path,
        metadata.get("filename") if isinstance(metadata, Mapping) else None,
        metadata.get("source") if isinstance(metadata, Mapping) else None,
        metadata.get("example_id") if isinstance(metadata, Mapping) else None,
    )
    report_progress(15, "decoding", "Decoding audio.")
    if job_logger:
        job_logger.debug("Stage: decoding audio file")
    audio, sample_rate = _decode_audio_file(file_path)

    # Optional vocal source separation — gated by audio_type
    # Determine audio_type from metadata
    _audio_type_requested = "isolated"
    _force_vocal_separation = False
    if isinstance(metadata, Mapping):
        _audio_type_requested = str(metadata.get("audio_type") or "isolated").lower().strip()
        _force_vocal_separation = bool(metadata.get("force_vocal_separation", False))
        # Example gallery tracks and reference uploads default to "mixed"
        _source = str(metadata.get("source") or "").lower()
        if _audio_type_requested == "isolated" and _source in ("example", "reference"):
            _audio_type_requested = "mixed"

    # Resolve effective audio type
    if _audio_type_requested == "auto" and _vocal_separation_available():
        from analysis.dsp.vocal_separation import detect_audio_type as _detect_audio_type

        _detected_audio_type = _detect_audio_type(audio, sample_rate)
    elif _audio_type_requested == "auto":
        _detected_audio_type = "isolated"  # can't detect without library
    else:
        _detected_audio_type = _audio_type_requested

    # Only apply separation when audio is identified as mixed and Demucs is available
    # OR when force_vocal_separation is enabled
    _separation_enabled = _VOCAL_SEPARATION_MODE != "off"
    _do_separate = (
        (_detected_audio_type == "mixed" or _force_vocal_separation)
        and _separation_enabled
        and _vocal_separation_available()
    )

    separation_info: dict = {
        "audio_type_requested": _audio_type_requested,
        "audio_type_detected": _detected_audio_type,
        "force_vocal_separation": _force_vocal_separation,
        "applied": False,
    }
    if _do_separate:
        try:
            from analysis.dsp.vocal_separation import separate_vocals as _separate_vocals

            report_progress(20, "vocal_separation", "Separating vocals.")
            if job_logger:
                job_logger.debug("Stage: vocal separation")
            sep_result = _separate_vocals(
                audio,
                sample_rate,
                file_path=file_path,
                cache_dir=_STEM_CACHE_DIR,
            )
            audio = sep_result.vocals
            sample_rate = sep_result.sample_rate
            separation_info["model"] = sep_result.model_name
            separation_info["separation_time_s"] = sep_result.separation_time_s
            separation_info["cache_hit"] = sep_result.cache_hit
            separation_info["applied"] = True
            logger.info(
                "vocal_separation_applied model=%s separation_time_s=%.2f cache_hit=%s",
                sep_result.model_name,
                sep_result.separation_time_s,
                sep_result.cache_hit,
            )
        except Exception as exc:
            warnings.append(f"Vocal separation unavailable: {exc}")
            logger.warning("vocal_separation_failed error=%s", exc, exc_info=True)

    preprocessed = preprocess_audio(
        audio,
        sample_rate=int(sample_rate),
        target_sr=TARGET_SAMPLE_RATE,
        mono=True,
        normalize=True,
        pre_emphasis_alpha=0.97,
    )
    mono_audio = preprocessed.audio
    sample_rate = int(preprocessed.sample_rate)

    report_progress(35, "pitch_extraction", "Extracting pitch.")
    if job_logger:
        job_logger.debug("Stage: pitch extraction")
    stft_result = compute_stft(
        mono_audio,
        sample_rate=sample_rate,
        n_fft=STFT_NFFT,
        hop_length=STFT_HOP,
    )
    report_progress(40, "stft", "Computing spectrogram.")
    harmonic_frames = detect_harmonics(
        stft_result.spectrum,
        stft_result.frequencies,
        n_harmonics=4,
        freq_tolerance=50.0,
        min_db=-40.0,
        max_candidates=6,
    )
    report_progress(46, "harmonics", "Detecting harmonics.")
    pitch_candidates = estimate_pitch_frames(
        stft_result.spectrum,
        stft_result.frequencies,
        harmonic_frames,
        audio=mono_audio,
        sample_rate=sample_rate,
        hop_length=STFT_HOP,
        n_fft=STFT_NFFT,
    )
    report_progress(54, "pitch_frames", "Estimating pitch frames.")
    pitch_frame_diagnostics = _extract_pitch_frame_diagnostics(pitch_candidates)
    pitch_method_diagnostics = _summarize_pitch_method_diagnostics(pitch_frame_diagnostics)
    optimized = optimize_lead_voice(pitch_candidates)
    report_progress(60, "pitch_optimization", "Optimizing pitch path.")

    if optimized.f0_hz.size:
        sigma_f = np.interp(
            np.clip(optimized.f0_hz, stft_result.frequencies[0], stft_result.frequencies[-1]),
            stft_result.frequencies,
            stft_result.sigma_f,
            left=float(stft_result.sigma_f[0]),
            right=float(stft_result.sigma_f[-1]),
        )
    else:
        sigma_f = np.asarray([], dtype=float)

    midi_values, midi_sigma = convert_f0_to_midi(optimized.f0_hz, sigma_f=sigma_f)
    pitch_builder_name = "_build_pitch_payload"
    pitch_builder_obj = globals().get(pitch_builder_name)
    available_builders = sorted(
        name for name, obj in globals().items() if name.startswith("_build_") and callable(obj)
    )
    logger.info(
        "analysis_metric_inference_builder_check present=%s callable=%s builder_count=%s builder_sample=%s",
        pitch_builder_name in globals(),
        callable(pitch_builder_obj),
        len(available_builders),
        available_builders[:20],
    )
    pitch_frames = _build_pitch_payload(
        optimized.f0_hz,
        optimized.salience,
        midi_values,
        midi_sigma,
        sample_rate=sample_rate,
        hop_length=STFT_HOP,
        frame_diagnostics=pitch_frame_diagnostics,
    )
    note_events = _build_note_events(pitch_frames)
    chord_timeline = _build_chord_timeline(note_events)
    report_progress(63, "note_events", "Building note and chord data.")

    # Spectrogram data is served via the dedicated GET /spectrogram/{job_id} endpoint;
    # the legacy stft_raw is kept as an empty dict for backward compatibility with any
    # consuming code that reads analysis_payload["spectrogram"] or ["spectrum"].
    stft_raw: Dict[str, Any] = {}
    voiced_pitch_frames = [frame for frame in pitch_frames if _is_voiced_frame(frame)]
    voiced_midi = [
        float(frame["midi"])
        for frame in voiced_pitch_frames
        if _safe_float(frame.get("midi")) is not None
    ]
    voiced_f0 = [float(frame["f0_hz"]) for frame in voiced_pitch_frames]
    pitch_errors = [
        float(frame["cents"])
        for frame in pitch_frames
        if _safe_float(frame.get("cents")) is not None
    ]
    frame_confidences = [
        float(frame["confidence"])
        for frame in voiced_pitch_frames
        if _safe_float(frame.get("confidence")) is not None
    ]
    frame_uncertainties = [
        float(frame["uncertainty"])
        for frame in voiced_pitch_frames
        if _safe_float(frame.get("uncertainty")) is not None
    ]
    duration_seconds = float(mono_audio.shape[-1] / max(sample_rate, 1))

    report_progress(65, "key_detection", "Detecting musical key.")
    key_detection_result = detect_key(voiced_midi, input_unit="midi") if voiced_midi else None
    key_trajectory: List[Dict[str, Any]] = []
    key_probabilities: Dict[str, float] = {}
    if key_detection_result is not None:
        key_probabilities = {
            str(label): float(probability)
            for label, probability in key_detection_result.probabilities.items()
        }
        # Attempt windowed key trajectory with Viterbi smoothing.
        # Falls back to a single global key entry when there aren't enough
        # observations or when the trajectory function is unavailable.
        voiced_timestamps = [
            float(frame.get("time", 0.0))
            for frame in voiced_pitch_frames
            if _safe_float(frame.get("time")) is not None
        ]
        if len(voiced_midi) >= 10 and len(voiced_timestamps) == len(voiced_midi):
            try:
                traj_entries = detect_key_trajectory(
                    voiced_midi,
                    voiced_timestamps,
                    input_unit="midi",
                    window_s=8.0,
                    hop_s=4.0,
                )
                if traj_entries:
                    key_trajectory = [
                        {
                            "start": entry.start_s,
                            "end": entry.end_s,
                            "label": entry.label,
                            "confidence": entry.confidence,
                        }
                        for entry in traj_entries
                    ]
            except Exception as exc:
                logger.debug("key_trajectory_failed error=%s", exc)

        # Fall back to single global key if trajectory is empty.
        if not key_trajectory and key_detection_result.best_key:
            key_trajectory.append(
                {
                    "start": 0.0,
                    "end": duration_seconds,
                    "label": key_detection_result.best_key,
                    "confidence": float(key_detection_result.confidence),
                }
            )

    report_progress(72, "tessitura", "Analyzing vocal range.")
    if job_logger:
        job_logger.debug("Stage: tessitura analysis")
    tessitura_payload: Dict[str, Any] = {}
    if voiced_midi:
        try:
            tessitura_result = analyze_tessitura(
                voiced_midi,
                confidences=frame_confidences if frame_confidences else None,
                uncertainties=frame_uncertainties if frame_uncertainties else None,
                return_pdf=True,
            )
            tessitura_payload = _serialize_tessitura_payload(tessitura_result)
        except Exception as exc:
            warnings.append(f"Tessitura analysis unavailable: {exc}")

    report_progress(79, "vibrato", "Analyzing vibrato.")
    if job_logger:
        job_logger.debug("Stage: vibrato analysis")
    advanced_payload: Dict[str, Any] = {}
    try:
        vibrato = detect_vibrato(
            voiced_f0,
            sample_rate=sample_rate,
            hop_length=STFT_HOP,
        )
        advanced_payload["vibrato"] = {
            "valid": bool(vibrato.valid),
            "rate_hz": _safe_float(vibrato.rate_hz),
            "depth_cents": _safe_float(vibrato.depth_cents),
            "peak_power": _safe_float(vibrato.peak_power),
            "power_ratio": _safe_float(vibrato.power_ratio),
            "start_index": int(vibrato.start_index),
            "n_frames": int(vibrato.n_frames),
        }
    except Exception as exc:
        warnings.append(f"Vibrato analysis unavailable: {exc}")

    report_progress(86, "formants", "Analyzing formants.")
    if job_logger:
        job_logger.debug("Stage: formant analysis")
    try:
        formant_track = estimate_formants_from_audio(
            mono_audio,
            sample_rate=sample_rate,
            hop_length=STFT_HOP,
        )
        advanced_payload["formants"] = _summarize_formants(formant_track)
    except Exception as exc:
        warnings.append(f"Formant analysis unavailable: {exc}")

    report_progress(92, "phrases", "Segmenting phrases.")
    if job_logger:
        job_logger.debug("Stage: phrase segmentation")
    try:
        phrase_result = segment_phrases_from_audio(
            mono_audio,
            sample_rate=sample_rate,
            hop_length=STFT_HOP,
        )
        advanced_payload["phrases"] = _summarize_phrases(phrase_result)
    except Exception as exc:
        warnings.append(f"Phrase segmentation unavailable: {exc}")

    analysis_uncertainty = summarize_uncertainty(
        [
            {
                "metadata": {"note_frequencies_hz": voiced_f0},
                "pitch_error_cents": pitch_errors,
            }
        ]
    )
    reference_uncertainty = _build_reference_calibration_uncertainty()
    inferential_statistics = _build_inferential_statistics(
        voiced_f0=voiced_f0,
        voiced_midi=voiced_midi,
        pitch_errors=pitch_errors,
        metadata=metadata,
    )
    calibration_summary = _build_calibration_summary(
        reference_uncertainty,
    )
    evidence_payload = _build_evidence_payload(
        pitch_frames,
        note_events=note_events,
        duration_seconds=duration_seconds,
    )

    metadata_payload: Dict[str, Any] = {
        "sample_rate": sample_rate,
        "hop_length": STFT_HOP,
        "frame_rate": float(sample_rate) / float(max(STFT_HOP, 1)),
        "duration_seconds": duration_seconds,
        "spectrogram": stft_raw,
    }
    if separation_info:
        metadata_payload["vocal_separation"] = separation_info
    if isinstance(metadata, Mapping):
        for key, value in metadata.items():
            if str(key).startswith("_"):
                continue
            metadata_payload[str(key)] = value
    # Store the original file path so the spectrogram endpoint can recover it
    # from the job result even after a server restart (_job_file_paths eviction).
    metadata_payload["_original_file_path"] = file_path

    analysis_payload: Dict[str, Any] = {
        "metadata": metadata_payload,
        "pitch": {
            "frames": pitch_frames,
            "f0_min": float(np.min(voiced_f0)) if voiced_f0 else None,
            "f0_max": float(np.max(voiced_f0)) if voiced_f0 else None,
        },
        "spectrum": stft_raw,
    }
    analysis_payload["pitch_frames"] = pitch_frames
    analysis_payload["note_events"] = note_events
    analysis_payload["notes"] = {"events": note_events}
    analysis_payload["chords"] = {"timeline": chord_timeline}
    analysis_payload["keys"] = {
        "trajectory": key_trajectory,
        "probabilities": key_probabilities,
        "best_key": key_detection_result.best_key if key_detection_result else None,
    }
    analysis_payload["tessitura"] = tessitura_payload
    analysis_payload["advanced"] = advanced_payload
    analysis_payload["uncertainty"] = analysis_uncertainty
    analysis_payload["inferential_statistics"] = inferential_statistics
    analysis_payload["calibration"] = {
        "summary": calibration_summary,
    }
    analysis_payload["diagnostics"] = {
        "pitch_analysis_methods": pitch_method_diagnostics,
    }
    analysis_payload["evidence"] = evidence_payload

    # Build summary with note notation (f0_min_note, f0_max_note)
    analysis_payload["summary"] = _build_summary(analysis_payload, duration_seconds)

    report_progress(96, "export", "Generating export files.")
    if job_logger:
        job_logger.debug("Stage: generating export files")
    export_files: Dict[str, str] = {}
    export_stem = f"{Path(file_path).stem}_{uuid4().hex[:8]}"
    export_json_path = OUTPUT_DIR / f"{export_stem}.json"
    export_csv_path = OUTPUT_DIR / f"{export_stem}.csv"
    export_pdf_path = OUTPUT_DIR / f"{export_stem}.pdf"

    try:
        generate_json_report(analysis_payload, output_path=str(export_json_path))
        export_files["json"] = str(export_json_path)
    except Exception as exc:
        warnings.append(f"JSON export unavailable: {exc}")
        logger.warning("analysis_export_json_failed file_path=%s error=%s", file_path, exc)

    try:
        generate_csv_report(analysis_payload, output_path=str(export_csv_path))
        export_files["csv"] = str(export_csv_path)
    except Exception as exc:
        warnings.append(f"CSV export unavailable: {exc}")
        logger.warning("analysis_export_csv_failed file_path=%s error=%s", file_path, exc)

    try:
        generate_pdf_report(analysis_payload, output_path=str(export_pdf_path))
        export_files["pdf"] = str(export_pdf_path)
    except Exception as exc:
        warnings.append(f"PDF export unavailable: {exc}")
        logger.warning("analysis_export_pdf_failed file_path=%s error=%s", file_path, exc)

    if export_files:
        analysis_payload["files"] = dict(export_files)
        if export_files.get("json"):
            analysis_payload["result_path"] = export_files["json"]

    if warnings:
        analysis_payload["warnings"] = warnings

    response_payload: Dict[str, Any] = {
        "analysis": analysis_payload,
    }
    if export_files:
        response_payload["files"] = dict(export_files)
        if export_files.get("json"):
            response_payload["result_path"] = export_files["json"]

    return response_payload


def _build_spectrogram_payload(
    file_path: str,
    *,
    vocal_cache_key: Optional[str] = None,
    audio_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Build spectrogram payload with base64-encoded mix and optional vocal stem data.

    Args:
        file_path: Path to the audio file
        vocal_cache_key: Optional cache key for vocal-separated stem
        audio_type: Optional audio type hint (isolated/mixed/auto)

    Returns:
        Dictionary with mix.frames_b64, n_time, n_freq and vocals.available
    """
    import base64
    from pathlib import Path

    # Load audio
    audio, sample_rate = _decode_audio_file(file_path)

    # Ensure mono
    if audio.ndim > 1:
        audio = np.mean(audio, axis=0)

    # Compute STFT for mix
    stft_result = compute_stft(
        audio,
        sample_rate=sample_rate,
        n_fft=STFT_NFFT,
        hop_length=STFT_HOP,
    )

    # Convert spectrum to dB and clip for visualization
    S_db = 20 * np.log10(np.maximum(stft_result.spectrum, 1e-10))
    S_db_clipped = np.clip(S_db, -80, 0)

    # Normalize for uint8 encoding
    S_normalized = ((S_db_clipped + 80) / 80 * 255).astype(np.uint8)

    # Encode as base64
    mix_b64 = base64.b64encode(S_normalized.tobytes()).decode("ascii")

    payload = {
        "audio_type": audio_type,
        "mix": {
            "frames_b64": mix_b64,
            "n_time": int(S_normalized.shape[1]),
            "n_freq": int(S_normalized.shape[0]),
            "sample_rate": int(sample_rate),
            "hop_length": int(STFT_HOP),
            "n_fft": int(STFT_NFFT),
            "freq_min_hz": float(_SPECT_FREQ_MIN_HZ),
            "freq_max_hz": float(_SPECT_FREQ_MAX_HZ),
        },
        "vocals": {
            "available": False,
        },
    }

    # Try to load cached vocal stem if available
    if vocal_cache_key and _vocal_separation_available() and _STEM_CACHE_DIR:
        try:
            from analysis.dsp.vocal_separation import load_cached_vocals

            cached = load_cached_vocals(vocal_cache_key, _STEM_CACHE_DIR)
            if cached is not None:
                vocals_audio, vocals_sr = cached
                if vocals_audio.ndim > 1:
                    vocals_audio = np.mean(vocals_audio, axis=0)
                vocals_stft = compute_stft(
                    vocals_audio,
                    sample_rate=vocals_sr,
                    n_fft=STFT_NFFT,
                    hop_length=STFT_HOP,
                )
                S_v_db = 20 * np.log10(np.maximum(vocals_stft.spectrum, 1e-10))
                S_v_db_clipped = np.clip(S_v_db, -80, 0)
                S_v_normalized = ((S_v_db_clipped + 80) / 80 * 255).astype(np.uint8)
                vocals_b64 = base64.b64encode(S_v_normalized.tobytes()).decode("ascii")
                payload["vocals"] = {
                    "available": True,
                    "frames_b64": vocals_b64,
                    "n_time": int(S_v_normalized.shape[1]),
                    "n_freq": int(S_v_normalized.shape[0]),
                }
        except Exception as exc:
            logger.debug(
                "spectrogram_vocals_load_failed vocal_cache_key=%s error=%s", vocal_cache_key, exc
            )

    return payload
