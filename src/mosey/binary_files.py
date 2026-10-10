"""The patterns that ignore binary files, like images, archives and documents.

`BINARY_FILE_PATTERNS` is exported by the `mosey` package, so import it from there
rather than this module.
"""

from typing import Final

BINARY_FILE_PATTERNS: Final[tuple[str, ...]] = (
    # Archives
    "*.7z",
    "*.7Z",
    "*.bz2",
    "*.BZ2",
    "*.gz",
    "*.GZ",
    "*.rar",
    "*.RAR",
    "*.tar",
    "*.TAR",
    "*.tgz",
    "*.TGZ",
    "*.xz",
    "*.XZ",
    "*.zip",
    "*.ZIP",
    "*.zst",
    "*.ZST",
    # Documents
    "*.doc",
    "*.DOC",
    "*.docx",
    "*.DOCX",
    "*.epub",
    "*.EPUB",
    "*.odp",
    "*.ODP",
    "*.ods",
    "*.ODS",
    "*.odt",
    "*.ODT",
    "*.pdf",
    "*.PDF",
    "*.ppt",
    "*.PPT",
    "*.pptx",
    "*.PPTX",
    "*.xls",
    "*.XLS",
    "*.xlsx",
    "*.XLSX",
    # Images
    "*.avif",
    "*.AVIF",
    "*.bmp",
    "*.BMP",
    "*.gif",
    "*.GIF",
    "*.heic",
    "*.HEIC",
    "*.ico",
    "*.ICO",
    "*.jpeg",
    "*.JPEG",
    "*.jpg",
    "*.JPG",
    "*.png",
    "*.PNG",
    "*.tif",
    "*.TIF",
    "*.tiff",
    "*.TIFF",
    "*.webp",
    "*.WEBP",
    # Audio and video
    "*.aac",
    "*.AAC",
    "*.avi",
    "*.AVI",
    "*.flac",
    "*.FLAC",
    "*.m4a",
    "*.M4A",
    "*.m4v",
    "*.M4V",
    "*.mkv",
    "*.MKV",
    "*.mov",
    "*.MOV",
    "*.mp3",
    "*.MP3",
    "*.mp4",
    "*.MP4",
    "*.mpeg",
    "*.MPEG",
    "*.mpg",
    "*.MPG",
    "*.ogg",
    "*.OGG",
    "*.opus",
    "*.OPUS",
    "*.wav",
    "*.WAV",
    "*.webm",
    "*.WEBM",
    # Applications
    "*.exe",
    "*.EXE",
    # Whole names
    ".DS_Store",
)
"""The patterns that ignore binary files.

[`Mosey.ignore_binary_files`][mosey.Mosey.ignore_binary_files] adds them. Each is
written like a line of an [ignore-file][ignore-files].

Which files they match is documented at [binary files][binary-files].
"""
