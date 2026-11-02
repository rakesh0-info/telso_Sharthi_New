import os
import uuid
from typing import Optional
from fastapi import UploadFile, HTTPException, status

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "video/mp4",
    "video/webm",
    "audio/mpeg",
    "audio/wav",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain"
}

MAX_FILE_SIZE_MB = 50
UPLOAD_DIR = "uploads/content_files"


def save_upload_file(file: Optional[UploadFile], language_label: str) -> Optional[str]:
    if not file or not file.filename:
        return None

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type for {language_label} version. Allowed types: PDF, MP4, MP3, DOCX."
        )

    # Check file size by seeking to the end
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)  # Reset cursor position

    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size for {language_label} version exceeds the maximum limit of {MAX_FILE_SIZE_MB}MB."
        )

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1].lower()
    unique_filename = f"{uuid.uuid4()}_{language_label}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    try:
        with open(file_path, "wb") as buffer:
            while chunk := file.file.read(1024 * 1024):
                buffer.write(chunk)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save {language_label} file to storage."
        ) from exc

    return file_path


def remove_file(file_path: Optional[str]) -> None:
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass