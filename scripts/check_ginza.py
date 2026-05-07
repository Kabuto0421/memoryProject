"""Minimal GiNZA verification script."""

from __future__ import annotations

from pathlib import Path
import sys

import spacy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TEXT = "これはGiNZAの動作確認です。"


def main() -> None:
    """Load the GiNZA pipeline and print token information."""
    nlp = spacy.load("ja_ginza")
    doc = nlp(TEXT)
    for token in doc:
        print(f"{token.text}\t{token.lemma_}\t{token.pos_}")


if __name__ == "__main__":
    main()
