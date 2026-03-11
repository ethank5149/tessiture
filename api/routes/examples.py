# api/routes/examples.py
"""
Example gallery endpoints.

Endpoints for listing and serving example audio files from the gallery.
"""

from typing import Any, Dict

from fastapi import APIRouter

from api import api_router as main_routes

router = APIRouter()


@router.get("/examples")
def list_example_tracks() -> Dict[str, Any]:
    """List all available example tracks in the gallery.

    Returns:
        Dictionary containing list of example tracks with metadata.
    """
    examples = main_routes._list_available_example_tracks()
    main_routes.logger.info("example_gallery.endpoint_response available_examples=%d", len(examples))
    return {"examples": examples}


@router.get("/examples/{filename}/thumbnail")
def serve_example_thumbnail(filename: str) -> Any:
    """Extract and return embedded artwork from an example audio file via mutagen.

    Supports FLAC (native PICTURE blocks), Ogg/Opus (VorbisComment METADATA_BLOCK_PICTURE),
    MP3 (ID3 APIC frame), and MP4/M4A (covr atom).
    Returns 404 when no embedded artwork is present.
    """
    import base64
    import struct

    from fastapi import HTTPException
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3NoHeaderError
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.oggopus import OggOpus
    from mutagen.oggvorbis import OggVorbis

    candidate = main_routes._resolve_example_file(filename)
    extension = candidate.suffix.lower()
    if extension not in main_routes.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=404, detail="Example file not found.")

    picture_data: Any = None
    picture_mime: str = "image/jpeg"

    try:
        if extension == ".flac":
            audio = FLAC(str(candidate))
            if audio.pictures:
                pic = audio.pictures[0]
                picture_data = pic.data
                picture_mime = pic.mime or "image/jpeg"

        elif extension in (".opus", ".ogg"):
            audio = OggOpus(str(candidate)) if extension == ".opus" else OggVorbis(str(candidate))
            raw_list = audio.get("metadata_block_picture", [])
            if raw_list:
                raw = base64.b64decode(raw_list[0])
                offset = 0
                offset += 4  # picture type
                mime_len = struct.unpack_from(">I", raw, offset)[0]
                offset += 4
                mime_bytes = raw[offset : offset + mime_len]
                offset += mime_len
                desc_len = struct.unpack_from(">I", raw, offset)[0]
                offset += 4
                offset += desc_len  # description
                offset += 16  # width, height, color depth, colors used
                data_len = struct.unpack_from(">I", raw, offset)[0]
                offset += 4
                picture_data = raw[offset : offset + data_len]
                picture_mime = mime_bytes.decode("utf-8", errors="replace") or "image/jpeg"

        elif extension == ".mp3":
            try:
                from mutagen.id3 import APIC, ID3

                tags = ID3(str(candidate))
                apic_keys = [k for k in tags.keys() if k.startswith("APIC")]
                if apic_keys:
                    apic = tags[apic_keys[0]]
                    picture_data = apic.data
                    picture_mime = apic.mime or "image/jpeg"
            except ID3NoHeaderError:
                pass

        elif extension in (".m4a", ".mp4", ".aac"):
            audio = MP4(str(candidate))
            covr = audio.tags.get("covr") if audio.tags else None
            if covr:
                img = covr[0]
                picture_data = bytes(img)
                picture_mime = (
                    "image/png"
                    if getattr(img, "imageformat", None) == MP4Cover.FORMAT_PNG
                    else "image/jpeg"
                )

    except Exception:
        pass  # Mutagen parse failure — no artwork available.

    if not picture_data:
        raise HTTPException(status_code=404, detail="No embedded artwork found.")

    main_routes.logger.info(
        "example_gallery.serve_thumbnail filename=%s mime=%s size=%d",
        filename,
        picture_mime,
        len(picture_data),
    )
    from fastapi.responses import Response

    return Response(content=picture_data, media_type=picture_mime)


@router.get("/examples/{filename}")
def serve_example_file(filename: str) -> Any:
    """Serve an example audio file or image sidecar from EXAMPLES_DIR."""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    candidate = main_routes._resolve_example_file(filename)
    extension = candidate.suffix.lower()
    if extension not in main_routes.ALLOWED_EXTENSIONS and extension not in main_routes.EXAMPLE_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=404, detail="Example file not found.")

    content_type = main_routes.mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
    main_routes.logger.info("example_gallery.serve_example filename=%s mime=%s", filename, content_type)
    return FileResponse(
        str(candidate),
        media_type=content_type,
        headers={"Accept-Ranges": "bytes"},
    )
