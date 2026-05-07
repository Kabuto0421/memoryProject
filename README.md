# Long Memory Prototype

macOS 上でローカル開発するための、最小 Python 環境です。  
現段階では本格実装には入らず、`uv`・FastAPI・Streamlit・pytest・spaCy/GiNZA を使える土台だけを整えています。

## Requirements

- macOS
- Homebrew
- `uv`

## Setup

```bash
brew install uv
uv sync
```

このリポジトリでは `.python-version` を `3.12` に固定しています。

## Directory Layout

```text
app/
  api/
  core/
  memory/
  analysis/
  tests/
scripts/
```

## Installed Dependencies

- `fastapi`
- `uvicorn`
- `streamlit`
- `pytest`
- `spacy`
- `ginza`
- `ja-ginza`
- `sudachipy`
- `sudachidict-core`
- `sentence-transformers`

## Verification Commands

FastAPI:

```bash
uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Streamlit:

```bash
uv run streamlit run app/streamlit_app.py --server.headless true
```

pytest:

```bash
uv run pytest
```

GiNZA:

```bash
uv run python scripts/check_ginza.py
```

## Current Scope

- FastAPI の最小アプリ
- Streamlit の最小アプリ
- pytest の最小テスト
- GiNZA の日本語解析確認スクリプト

SQLite 前提のローカル開発を想定しており、PostgreSQL / pgvector / Docker はまだ入れていません。
