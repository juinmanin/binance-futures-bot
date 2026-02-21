"""전자책 폴더를 스캔하여 옵시디언 노트를 생성하는 메인 오케스트레이터"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .obsidian_writer import ObsidianWriter
from .pdf_processor import BookMetadata, PdfProcessor


@dataclass
class OrganizerResult:
    """정리 작업 결과"""

    processed: list[Path]
    skipped: list[Path]
    notes: list[Path]

    @property
    def total_processed(self) -> int:
        return len(self.processed)

    @property
    def total_skipped(self) -> int:
        return len(self.skipped)


class EbookOrganizer:
    """전자책 폴더의 PDF를 스캔하여 옵시디언 볼트에 노트를 생성"""

    DEFAULT_EBOOK_DIR = "전자책"
    DEFAULT_VAULT_SUBDIR = "전자책 노트"

    def __init__(
        self,
        ebook_dir: str | Path | None = None,
        vault_dir: str | Path | None = None,
        processor: PdfProcessor | None = None,
        writer: ObsidianWriter | None = None,
    ) -> None:
        self.ebook_dir = Path(ebook_dir) if ebook_dir else Path.home() / self.DEFAULT_EBOOK_DIR
        self.vault_dir = Path(vault_dir) if vault_dir else Path.home() / "obsidian" / self.DEFAULT_VAULT_SUBDIR
        self._processor = processor or PdfProcessor()
        self._writer = writer or ObsidianWriter()

    def organize(self) -> OrganizerResult:
        """전자책 폴더를 스캔하고 옵시디언 노트를 생성한 후 결과를 반환"""
        pdf_files = self._collect_pdfs()

        processed: list[Path] = []
        skipped: list[Path] = []
        notes: list[Path] = []

        for pdf_path in pdf_files:
            try:
                metadata = self._processor.process(pdf_path)
                note_path = self._writer.write(metadata, self.vault_dir)
                processed.append(pdf_path)
                notes.append(note_path)
            except (OSError, ValueError, RuntimeError):
                skipped.append(pdf_path)

        return OrganizerResult(processed=processed, skipped=skipped, notes=notes)

    def _collect_pdfs(self) -> list[Path]:
        """전자책 폴더에서 모든 PDF 파일을 재귀적으로 수집"""
        if not self.ebook_dir.exists():
            return []
        return sorted(self.ebook_dir.rglob("*.pdf"))
