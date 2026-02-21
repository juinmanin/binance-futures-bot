#!/usr/bin/env python3
"""
전자책 → 옵시디언 정리 CLI 스크립트

사용법:
    python scripts/organize_ebooks.py [전자책_폴더] [옵시디언_볼트_폴더]

예시:
    # 기본값 사용 (~/전자책 → ~/obsidian/전자책 노트)
    python scripts/organize_ebooks.py

    # 경로 직접 지정
    python scripts/organize_ebooks.py /home/user/전자책 "/home/user/obsidian/전자책 노트"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ebook_organizer import EbookOrganizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="전자책 폴더의 PDF 파일을 옵시디언 마크다운 노트로 정리합니다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "ebook_dir",
        nargs="?",
        default=None,
        help="PDF 전자책이 있는 폴더 경로 (기본값: ~/전자책)",
    )
    parser.add_argument(
        "vault_dir",
        nargs="?",
        default=None,
        help="옵시디언 볼트 내 저장 폴더 경로 (기본값: ~/obsidian/전자책 노트)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    organizer = EbookOrganizer(
        ebook_dir=args.ebook_dir,
        vault_dir=args.vault_dir,
    )

    print(f"📂 전자책 폴더: {organizer.ebook_dir}")
    print(f"📓 옵시디언 저장 폴더: {organizer.vault_dir}")
    print()

    if not organizer.ebook_dir.exists():
        print(f"❌ 오류: 전자책 폴더를 찾을 수 없습니다 → {organizer.ebook_dir}")
        return 1

    result = organizer.organize()

    print(f"✅ 처리 완료: {result.total_processed}개 파일")
    for note in result.notes:
        print(f"   📄 {note.name}")

    if result.total_skipped:
        print(f"\n⚠️  건너뜀: {result.total_skipped}개 파일")
        for path in result.skipped:
            print(f"   ⛔ {path.name}")

    if result.total_processed == 0 and result.total_skipped == 0:
        print("ℹ️  처리할 PDF 파일이 없습니다.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
