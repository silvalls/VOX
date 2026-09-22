"""Viés de vocabulário (deterministicamente orientado, sem reescrita).

Carrega uma lista de termos/nomes esperados no contexto (siglas, jargão jurídico,
nomes próprios recorrentes) e monta um ``initial_prompt`` curto que ORIENTA o
reconhecimento do Whisper a grafá-los corretamente. Não adiciona nem remove
conteúdo: apenas melhora a chance de acerto nesses termos.

Arquivo de vocabulário: um termo por linha (ou separados por vírgula). Linhas
começando com '#' são comentários. Ex.:

    # Siglas
    FUNAI, MPI, Ibram, DPU
    # Nomes
    Chacriabá
    grileiro
"""

from __future__ import annotations

from pathlib import Path

# O prompt do Whisper é limitado (~224 tokens). Mantemos curto por segurança.
MAX_CHARS = 800


def carregar(caminho: str | Path) -> list[str]:
    termos: list[str] = []
    with open(caminho, "r", encoding="utf-8-sig") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            for t in linha.split(","):
                t = t.strip()
                if t and t not in termos:
                    termos.append(t)
    return termos


def construir_prompt(termos: list[str], max_chars: int = MAX_CHARS) -> str | None:
    """Monta o initial_prompt a partir dos termos, truncando com segurança."""
    if not termos:
        return None
    prefixo = "Vocabulário do contexto: "
    partes: list[str] = []
    total = len(prefixo)
    for t in termos:
        add = len(t) + 2
        if total + add > max_chars:
            break
        partes.append(t)
        total += add
    if not partes:
        return None
    return prefixo + ", ".join(partes) + "."


def prompt_de_arquivo(caminho: str | Path) -> str | None:
    return construir_prompt(carregar(caminho))
