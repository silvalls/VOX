"""Glossário determinístico (v1.1) — substituições exatas definidas pelo usuário.

Correção literal, SEM IA: ex.: grafar corretamente um nome próprio recorrente.
Aplicado apenas ao TEXTO DERIVADO na exportação; o JSON bruto (fonte de verdade)
permanece intacto para auditoria.

Formato do CSV (cabeçalho opcional ``de,para``; delimitador , ou ;):

    de,para
    João Sylva,João Silva
    RG,R.G.
"""

from __future__ import annotations

import copy
import csv
from pathlib import Path


def carregar(caminho_csv: str | Path) -> dict[str, str]:
    """Lê o CSV de substituições exatas. Retorna {de: para}."""
    caminho = Path(caminho_csv)
    mapa: dict[str, str] = {}
    with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
        amostra = f.read(2048)
        f.seek(0)
        delim = ";" if amostra.count(";") > amostra.count(",") else ","
        leitor = csv.reader(f, delimiter=delim)
        for i, linha in enumerate(leitor):
            if len(linha) < 2:
                continue
            de, para = linha[0].strip(), linha[1].strip()
            if i == 0 and de.lower() in ("de", "origem", "from"):
                continue  # cabeçalho
            if de:
                mapa[de] = para
    return mapa


def _substituir_texto(texto: str, mapa: dict[str, str]) -> str:
    # Substituição literal por ocorrência (mais longas primeiro para evitar
    # substituição parcial indevida).
    for de in sorted(mapa, key=len, reverse=True):
        if de in texto:
            texto = texto.replace(de, mapa[de])
    return texto


def aplicar(doc: dict, mapa: dict[str, str]) -> dict:
    """Retorna uma CÓPIA do documento com o glossário aplicado ao texto.

    Não modifica o documento original (o JSON bruto continua sendo a verdade).
    """
    if not mapa:
        return doc
    novo = copy.deepcopy(doc)
    for seg in novo.get("segments", []):
        if seg.get("text"):
            seg["text"] = _substituir_texto(seg["text"], mapa)
        for w in seg.get("words", []):
            if w.get("word"):
                w["word"] = _substituir_texto(w["word"], mapa)
    return novo
