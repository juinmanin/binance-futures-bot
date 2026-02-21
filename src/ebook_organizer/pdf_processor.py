"""PDF 파일에서 메타데이터와 텍스트를 추출하는 모듈"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pypdf 라이브러리가 필요합니다. 'pip install pypdf>=5.3.1' 명령으로 설치하세요."
    ) from exc

# pypdf 내부 경고 메시지를 INFO 수준으로 낮춰 사용자 터미널이 깔끔하게 유지되도록 설정
logging.getLogger("pypdf").setLevel(logging.ERROR)


@dataclass
class BookMetadata:
    """PDF 파일에서 추출한 책 메타데이터"""

    file_path: Path
    title: str = ""
    author: str = ""
    subject: str = ""
    creator: str = ""
    creation_date: str = ""
    page_count: int = 0
    preview_text: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def display_title(self) -> str:
        """표시용 제목 반환 (없으면 파일명 사용)"""
        return self.title or self.file_path.stem


class PdfProcessor:
    """PDF 파일 메타데이터 및 텍스트 추출기"""

    # 미리보기 텍스트 최대 문자 수
    PREVIEW_MAX_CHARS = 500

    def process(self, pdf_path: Path) -> BookMetadata:
        """PDF 파일 하나를 처리하여 BookMetadata 반환"""
        metadata = BookMetadata(file_path=pdf_path)

        try:
            reader = PdfReader(str(pdf_path))
            self._extract_metadata(reader, metadata)
            self._extract_preview(reader, metadata)
        except (PyPdfError, OSError, ValueError):
            # PDF를 읽을 수 없더라도 파일 이름 기반으로 계속 진행
            pass

        metadata.tags = self._infer_tags(metadata)
        return metadata

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _extract_metadata(self, reader: PdfReader, metadata: BookMetadata) -> None:
        """PdfReader에서 메타데이터 추출"""
        metadata.page_count = len(reader.pages)

        doc_info = reader.metadata
        if doc_info is None:
            return

        metadata.title = self._clean(getattr(doc_info, "title", "") or "")
        metadata.author = self._clean(getattr(doc_info, "author", "") or "")
        metadata.subject = self._clean(getattr(doc_info, "subject", "") or "")
        metadata.creator = self._clean(getattr(doc_info, "creator", "") or "")

        raw_date = getattr(doc_info, "creation_date", None)
        if raw_date:
            metadata.creation_date = str(raw_date)[:10]  # YYYY-MM-DD 형식

    def _extract_preview(self, reader: PdfReader, metadata: BookMetadata) -> None:
        """첫 번째 페이지에서 미리보기 텍스트 추출"""
        if not reader.pages:
            return

        text = reader.pages[0].extract_text() or ""
        # 연속된 공백·줄바꿈 정리
        text = re.sub(r"\s+", " ", text).strip()
        metadata.preview_text = text[: self.PREVIEW_MAX_CHARS]

    @staticmethod
    def _clean(value: str) -> str:
        """메타데이터 문자열의 불필요한 공백 제거"""
        return value.strip()

    @staticmethod
    def _infer_tags(metadata: BookMetadata) -> list[str]:
        """메타데이터에서 태그를 추론"""
        tags: list[str] = ["전자책", "PDF"]

        subject = metadata.subject.lower()
        title = metadata.display_title.lower()

        keyword_map: dict[str, str] = {
            "python": "Python",
            "파이썬": "Python",
            "java": "Java",
            "자바": "Java",
            "finance": "금융",
            "금융": "금융",
            "trading": "트레이딩",
            "트레이딩": "트레이딩",
            "machine learning": "머신러닝",
            "머신러닝": "머신러닝",
            "deep learning": "딥러닝",
            "딥러닝": "딥러닝",
            "history": "역사",
            "역사": "역사",
            "science": "과학",
            "과학": "과학",
        }

        for keyword, tag in keyword_map.items():
            if keyword in subject or keyword in title:
                if tag not in tags:
                    tags.append(tag)

        return tags
