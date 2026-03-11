/**
 * VocalSeparationStatus - Displays the status of vocal separation processing
 */

function VocalSeparationStatus({ vocalSeparation }) {
  if (!vocalSeparation || typeof vocalSeparation !== "object") {
    return null;
  }

  const { applied, audio_type_requested, model } = vocalSeparation;

  if (applied === true) {
    return (
      <p className="vocal-separation-status vocal-separation-status--applied" role="status">
        <span className="vocal-separation-status__badge">AI vocal extraction applied</span>
        <span className="vocal-separation-status__detail">
          Vocals were separated from the mix using {model ?? "htdemucs"} before analysis
        </span>
      </p>
    );
  }

  if (applied === false && audio_type_requested === "mixed") {
    return (
      <p className="vocal-separation-status vocal-separation-status--warn" role="status">
        Vocal extraction unavailable — analyzed as uploaded
      </p>
    );
  }

  if (applied === false && (audio_type_requested === "isolated" || !audio_type_requested)) {
    return (
      <p className="vocal-separation-status vocal-separation-status--isolated" role="status">
        Analyzed as isolated vocals
      </p>
    );
  }

  return null;
}

export default VocalSeparationStatus;
