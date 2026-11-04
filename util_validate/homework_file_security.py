import codecs
import logging
import os
import uuid
import zipfile
import zlib
from pathlib import Path

from fastapi import HTTPException, UploadFile, status


logger = logging.getLogger(__name__)
MAX_HOMEWORK_FILE_SIZE = 20 * 1024 * 1024
HOMEWORK_UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads" / "homework"
FILE_TYPES = {
    ".pdf": ("application/pdf",),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".txt": ("text/plain",),
    ".jpg": ("image/jpeg",),
    ".jpeg": ("image/jpeg",),
    ".png": ("image/png",),
}
FILE_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain; charset=utf-8",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
CHUNK_SIZE = 64 * 1024


def _safe_original_filename(filename: str) -> str:
    cleaned = filename.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(
        character
        for character in cleaned
        if character.isprintable() and character not in {"/", "\\"}
    ).strip()
    if not cleaned or len(cleaned) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded filename is invalid.",
        )
    return cleaned


def _validate_signature(path: Path, extension: str, prefix: bytes) -> None:
    valid = {
        ".pdf": prefix.startswith(b"%PDF-"),
        ".jpg": prefix.startswith(b"\xff\xd8\xff"),
        ".jpeg": prefix.startswith(b"\xff\xd8\xff"),
        ".png": prefix.startswith(b"\x89PNG\r\n\x1a\n"),
        ".txt": b"\x00" not in prefix,
        ".docx": prefix.startswith(b"PK\x03\x04"),
    }[extension]
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file content does not match its allowed file type.",
        )

    if extension == ".txt":
        decoder = codecs.getincrementaldecoder("utf-8")()
        try:
            with path.open("rb") as text_file:
                for chunk in iter(lambda: text_file.read(CHUNK_SIZE), b""):
                    if b"\x00" in chunk:
                        raise UnicodeDecodeError(
                            "utf-8",
                            chunk,
                            chunk.index(b"\x00"),
                            chunk.index(b"\x00") + 1,
                            "NUL bytes are not allowed in text attachments",
                        )
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text attachments must use UTF-8 encoding.",
            ) from exc
    elif extension == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                expanded_size = sum(entry.file_size for entry in entries)
                if (
                    len(entries) > 1000
                    or expanded_size > 50 * 1024 * 1024
                    or "[Content_Types].xml" not in names
                    or "word/document.xml" not in names
                    or archive.testzip() is not None
                ):
                    raise ValueError("Invalid or oversized DOCX archive.")
        except (OSError, RuntimeError, zipfile.BadZipFile, ValueError, zlib.error) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The DOCX attachment is invalid or oversized.",
            ) from exc


def save_homework_upload(file: UploadFile) -> tuple[str, str, int]:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An attachment filename is required.",
        )
    original_filename = _safe_original_filename(file.filename)
    extension = Path(original_filename).suffix.lower()
    expected_mimes = FILE_TYPES.get(extension)
    if expected_mimes is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Allowed attachments are PDF, DOCX, UTF-8 TXT, JPEG, or PNG.",
        )
    if file.content_type not in (*expected_mimes, "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded content type does not match the allowed file extension.",
        )

    try:
        HOMEWORK_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Homework upload directory creation failed: %s.", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The attachment could not be stored.",
        ) from exc
    destination = HOMEWORK_UPLOAD_DIR / f"{uuid.uuid4().hex}{extension}"
    total_size = 0
    prefix = b""
    try:
        with destination.open("xb") as output:
            while chunk := file.file.read(CHUNK_SIZE):
                total_size += len(chunk)
                if total_size > MAX_HOMEWORK_FILE_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Homework attachments must not exceed 20 MB.",
                    )
                if len(prefix) < 16:
                    prefix += chunk[: 16 - len(prefix)]
                output.write(chunk)
        if total_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty attachments are not allowed.",
            )
        _validate_signature(destination, extension, prefix)
    except HTTPException:
        remove_homework_upload(str(destination))
        raise
    except OSError as exc:
        remove_homework_upload(str(destination))
        logger.error("Homework attachment storage failed: %s.", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The attachment could not be stored.",
        ) from exc

    return str(destination), original_filename, total_size


def resolve_homework_upload(file_path: str) -> Path:
    try:
        base = HOMEWORK_UPLOAD_DIR.resolve()
        requested = Path(file_path).resolve()
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The attachment was not found.",
        ) from exc
    try:
        inside_upload_dir = os.path.commonpath((str(base), str(requested))) == str(base)
    except ValueError:
        inside_upload_dir = False
    if not inside_upload_dir:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The attachment was not found.",
        )
    if not requested.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The attachment was not found.",
        )
    return requested


def remove_homework_upload(file_path: str | None) -> None:
    if not file_path:
        return
    try:
        path = resolve_homework_upload(file_path)
        path.unlink()
    except HTTPException:
        return
    except OSError as exc:
        logger.warning("Homework attachment cleanup failed: %s.", type(exc).__name__)
