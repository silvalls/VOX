"""Saída JSON — a FONTE DE VERDADE do Degravador.

Contém a transcrição bruta completa: palavras, timestamps por palavra, locutor,
scores de confiança e metadados de processamento. Todos os outros formatos são
derivados deste arquivo, sem reprocessar o áudio.

``import json`` aqui refere-se à biblioteca padrão (import absoluto); este módulo
não sombreia o stdlib.
"""

from __future__ import annotations

import json
from pathlib import Path

ESQUEMA_VERSAO = "1.0"


def _normalizar_palavra(w: dict) -> dict:
    return {
        "word": (w.get("word") or "").strip(),
        "start": w.get("start"),
        "end": w.get("end"),
        "score": w.get("score"),
        "speaker": w.get("speaker"),
        "flags": list(w.get("flags", [])),
    }


def _normalizar_segmento(seg: dict) -> dict:
    return {
        "start": seg.get("start"),
        "end": seg.get("end"),
        "text": (seg.get("text") or "").strip(),
        "speaker": seg.get("speaker"),
        "avg_logprob": seg.get("avg_logprob"),
        "no_speech_prob": seg.get("no_speech_prob"),
        "compression_ratio": seg.get("compression_ratio"),
        "flags": list(seg.get("flags", [])),
        "words": [_normalizar_palavra(w) for w in seg.get("words", [])],
    }


def construir_documento(metadata: dict, segments: list[dict]) -> dict:
    """Monta o documento canônico a partir dos metadados e segmentos."""
    return {
        "schema_version": ESQUEMA_VERSAO,
        "app": "VOX",
        "metadata": metadata,
        "segments": [_normalizar_segmento(s) for s in segments],
    }


def salvar_em(doc: dict, caminho: str | Path, **_opts) -> Path:
    """Grava o documento em JSON (UTF-8, indentado, legível)."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return caminho


def carregar(caminho: str | Path) -> dict:
    """Carrega um documento JSON para re-export (sem reprocessar áudio)."""
    caminho = Path(caminho)
    with open(caminho, "r", encoding="utf-8") as f:
        doc = json.load(f)
    if "segments" not in doc or "metadata" not in doc:
        raise ValueError(
            f"{caminho} não parece um JSON do Degravador (faltam 'segments'/'metadata')."
        )
    return doc
