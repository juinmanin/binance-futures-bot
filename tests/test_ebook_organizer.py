"""전자책 정리 모듈 테스트"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ebook_organizer.obsidian_writer import ObsidianWriter
from src.ebook_organizer.organizer import EbookOrganizer, OrganizerResult
from src.ebook_organizer.pdf_processor import BookMetadata, PdfProcessor


# ---------------------------------------------------------------------------
# BookMetadata
# ---------------------------------------------------------------------------


class TestBookMetadata:
    def test_display_title_uses_title_when_set(self, tmp_path: Path) -> None:
        pdf = tmp_path / "sample.pdf"
        meta = BookMetadata(file_path=pdf, title="파이썬 입문")
        assert meta.display_title == "파이썬 입문"

    def test_display_title_falls_back_to_stem(self, tmp_path: Path) -> None:
        pdf = tmp_path / "my_book.pdf"
        meta = BookMetadata(file_path=pdf)
        assert meta.display_title == "my_book"


# ---------------------------------------------------------------------------
# PdfProcessor
# ---------------------------------------------------------------------------


class TestPdfProcessor:
    def _make_mock_reader(
        self,
        title: str = "Test Book",
        author: str = "홍길동",
        subject: str = "Python",
        creator: str = "Word",
        creation_date: str = "2023-01-15",
        page_count: int = 200,
        first_page_text: str = "이 책은 파이썬 기초를 다룹니다.",
    ) -> MagicMock:
        doc_info = MagicMock()
        doc_info.title = title
        doc_info.author = author
        doc_info.subject = subject
        doc_info.creator = creator
        doc_info.creation_date = creation_date

        page = MagicMock()
        page.extract_text.return_value = first_page_text

        reader = MagicMock()
        reader.metadata = doc_info
        reader.pages = [page] * page_count
        return reader

    def test_process_extracts_metadata(self, tmp_path: Path) -> None:
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4")  # 최소한의 PDF 헤더

        processor = PdfProcessor()
        mock_reader = self._make_mock_reader(title="딥러닝", author="이순신")

        with patch("src.ebook_organizer.pdf_processor.PdfReader", return_value=mock_reader):
            metadata = processor.process(pdf)

        assert metadata.title == "딥러닝"
        assert metadata.author == "이순신"
        assert metadata.page_count == 200

    def test_process_returns_metadata_even_on_read_error(self, tmp_path: Path) -> None:
        from pypdf.errors import PyPdfError

        pdf = tmp_path / "corrupt.pdf"
        pdf.write_bytes(b"not a pdf")

        processor = PdfProcessor()
        with patch("src.ebook_organizer.pdf_processor.PdfReader", side_effect=PyPdfError("read error")):
            metadata = processor.process(pdf)

        assert metadata.file_path == pdf
        assert metadata.title == ""

    def test_process_infers_python_tag(self, tmp_path: Path) -> None:
        pdf = tmp_path / "python_book.pdf"
        pdf.write_bytes(b"%PDF")

        processor = PdfProcessor()
        mock_reader = self._make_mock_reader(subject="Python programming")

        with patch("src.ebook_organizer.pdf_processor.PdfReader", return_value=mock_reader):
            metadata = processor.process(pdf)

        assert "Python" in metadata.tags

    def test_process_always_includes_base_tags(self, tmp_path: Path) -> None:
        pdf = tmp_path / "generic.pdf"
        pdf.write_bytes(b"%PDF")

        processor = PdfProcessor()
        mock_reader = self._make_mock_reader(subject="", title="")

        with patch("src.ebook_organizer.pdf_processor.PdfReader", return_value=mock_reader):
            metadata = processor.process(pdf)

        assert "전자책" in metadata.tags
        assert "PDF" in metadata.tags

    def test_preview_truncated_to_max_chars(self, tmp_path: Path) -> None:
        pdf = tmp_path / "long.pdf"
        pdf.write_bytes(b"%PDF")

        long_text = "A" * 1000
        mock_reader = self._make_mock_reader(first_page_text=long_text)

        processor = PdfProcessor()
        with patch("src.ebook_organizer.pdf_processor.PdfReader", return_value=mock_reader):
            metadata = processor.process(pdf)

        assert len(metadata.preview_text) <= PdfProcessor.PREVIEW_MAX_CHARS


# ---------------------------------------------------------------------------
# ObsidianWriter
# ---------------------------------------------------------------------------


class TestObsidianWriter:
    def _sample_metadata(self, tmp_path: Path) -> BookMetadata:
        return BookMetadata(
            file_path=tmp_path / "파이썬_완전정복.pdf",
            title="파이썬 완전정복",
            author="김철수",
            subject="Python",
            creation_date="2022-05-10",
            page_count=350,
            preview_text="파이썬의 기초부터 심화까지 다룹니다.",
            tags=["전자책", "PDF", "Python"],
        )

    def test_write_creates_markdown_file(self, tmp_path: Path) -> None:
        writer = ObsidianWriter()
        vault = tmp_path / "vault"
        metadata = self._sample_metadata(tmp_path)

        note_path = writer.write(metadata, vault)

        assert note_path.exists()
        assert note_path.suffix == ".md"

    def test_markdown_contains_yaml_frontmatter(self, tmp_path: Path) -> None:
        writer = ObsidianWriter()
        vault = tmp_path / "vault"
        metadata = self._sample_metadata(tmp_path)

        note_path = writer.write(metadata, vault)
        content = note_path.read_text(encoding="utf-8")

        assert content.startswith("---")
        assert "title:" in content
        assert "author:" in content
        assert "tags:" in content

    def test_markdown_contains_preview(self, tmp_path: Path) -> None:
        writer = ObsidianWriter()
        vault = tmp_path / "vault"
        metadata = self._sample_metadata(tmp_path)

        note_path = writer.write(metadata, vault)
        content = note_path.read_text(encoding="utf-8")

        assert metadata.preview_text in content

    def test_safe_filename_strips_illegal_chars(self) -> None:
        writer = ObsidianWriter()
        assert "/" not in writer._safe_filename("A/B:C*D")
        assert ":" not in writer._safe_filename("A/B:C*D")

    def test_write_creates_vault_dir_if_missing(self, tmp_path: Path) -> None:
        writer = ObsidianWriter()
        vault = tmp_path / "new" / "vault"
        metadata = self._sample_metadata(tmp_path)

        writer.write(metadata, vault)
        assert vault.exists()


# ---------------------------------------------------------------------------
# EbookOrganizer
# ---------------------------------------------------------------------------


class TestEbookOrganizer:
    def test_organize_processes_pdfs(self, tmp_path: Path) -> None:
        ebook_dir = tmp_path / "전자책"
        ebook_dir.mkdir()
        vault_dir = tmp_path / "obsidian"

        # 샘플 PDF 파일 생성
        (ebook_dir / "book1.pdf").write_bytes(b"%PDF-1.4")
        (ebook_dir / "book2.pdf").write_bytes(b"%PDF-1.4")

        mock_metadata = BookMetadata(file_path=ebook_dir / "book1.pdf", title="테스트 책")
        mock_processor = MagicMock(spec=PdfProcessor)
        mock_processor.process.return_value = mock_metadata

        mock_writer = MagicMock(spec=ObsidianWriter)
        mock_writer.write.return_value = vault_dir / "테스트 책.md"

        organizer = EbookOrganizer(
            ebook_dir=ebook_dir,
            vault_dir=vault_dir,
            processor=mock_processor,
            writer=mock_writer,
        )
        result = organizer.organize()

        assert result.total_processed == 2
        assert result.total_skipped == 0
        assert mock_processor.process.call_count == 2

    def test_organize_empty_folder_returns_empty_result(self, tmp_path: Path) -> None:
        ebook_dir = tmp_path / "전자책"
        ebook_dir.mkdir()

        organizer = EbookOrganizer(ebook_dir=ebook_dir, vault_dir=tmp_path / "vault")
        result = organizer.organize()

        assert result.total_processed == 0
        assert result.total_skipped == 0

    def test_organize_missing_folder_returns_empty_result(self, tmp_path: Path) -> None:
        organizer = EbookOrganizer(
            ebook_dir=tmp_path / "없는폴더",
            vault_dir=tmp_path / "vault",
        )
        result = organizer.organize()

        assert result.total_processed == 0
        assert result.total_skipped == 0

    def test_organize_records_skipped_on_write_error(self, tmp_path: Path) -> None:
        ebook_dir = tmp_path / "전자책"
        ebook_dir.mkdir()
        (ebook_dir / "error.pdf").write_bytes(b"%PDF")

        mock_processor = MagicMock(spec=PdfProcessor)
        mock_processor.process.return_value = BookMetadata(file_path=ebook_dir / "error.pdf")
        mock_writer = MagicMock(spec=ObsidianWriter)
        mock_writer.write.side_effect = OSError("permission denied")

        organizer = EbookOrganizer(
            ebook_dir=ebook_dir,
            vault_dir=tmp_path / "vault",
            processor=mock_processor,
            writer=mock_writer,
        )
        result = organizer.organize()

        assert result.total_processed == 0
        assert result.total_skipped == 1
