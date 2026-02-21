"""옵시디언 호환 마크다운 노트를 생성하는 모듈"""

from __future__ import annotations

import re
from pathlib import Path

from .pdf_processor import BookMetadata


class ObsidianWriter:
    """BookMetadata를 받아 옵시디언 마크다운 파일로 저장"""

    def write(self, metadata: BookMetadata, vault_dir: Path) -> Path:
        """마크다운 노트를 작성하고 저장된 경로를 반환"""
        vault_dir.mkdir(parents=True, exist_ok=True)

        note_path = vault_dir / f"{self._safe_filename(metadata.display_title)}.md"
        note_path.write_text(self._render(metadata), encoding="utf-8")
        return note_path

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _render(self, metadata: BookMetadata) -> str:
        """마크다운 내용 렌더링"""
        tags_yaml = "\n".join(f"  - {t}" for t in metadata.tags)

        lines: list[str] = [
            "---",
            f"title: \"{self._escape_yaml(metadata.display_title)}\"",
        ]

        if metadata.author:
            lines.append(f'author: "{self._escape_yaml(metadata.author)}"')
        if metadata.subject:
            lines.append(f'subject: "{self._escape_yaml(metadata.subject)}"')
        if metadata.creation_date:
            lines.append(f"creation_date: {metadata.creation_date}")
        if metadata.page_count:
            lines.append(f"pages: {metadata.page_count}")

        lines += [
            f"source: \"[[전자책/{metadata.file_path.name}]]\"",
            "tags:",
            tags_yaml,
            "---",
            "",
            f"# {metadata.display_title}",
            "",
        ]

        # 기본 정보 섹션
        lines += ["## 📖 기본 정보", ""]
        if metadata.author:
            lines.append(f"- **저자**: {metadata.author}")
        if metadata.subject:
            lines.append(f"- **주제**: {metadata.subject}")
        if metadata.creation_date:
            lines.append(f"- **작성일**: {metadata.creation_date}")
        if metadata.page_count:
            lines.append(f"- **페이지 수**: {metadata.page_count}페이지")
        lines.append(f"- **파일**: `{metadata.file_path.name}`")
        lines.append("")

        # 미리보기 섹션
        if metadata.preview_text:
            lines += [
                "## 📝 미리보기",
                "",
                f"> {metadata.preview_text}",
                "",
            ]

        # 독서 노트 템플릿
        lines += [
            "## 🗒️ 독서 노트",
            "",
            "### 핵심 내용",
            "",
            "- ",
            "",
            "### 인상적인 구절",
            "",
            "> ",
            "",
            "### 느낀 점",
            "",
            "",
            "### 적용할 점",
            "",
            "",
        ]

        return "\n".join(lines)

    @staticmethod
    def _safe_filename(title: str) -> str:
        """파일명으로 사용할 수 없는 문자 제거"""
        safe = re.sub(r'[\\\/\*\?:"<>\|]', "_", title)
        safe = safe.strip(". ")
        return safe or "제목없음"

    @staticmethod
    def _escape_yaml(value: str) -> str:
        """YAML 문자열 내 큰따옴표 이스케이프"""
        return value.replace('"', '\\"')
