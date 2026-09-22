"""Utilitários compartilhados pelos exportadores.

Centraliza: formatação de tempo, agrupamento de segmentos em turnos de fala,
rótulos de locutor e renderização das marcações de fidelidade em texto.
"""

from __future__ import annotations

from typing import Iterator


# ---------------------------------------------------------------------------
# Tempo
# ---------------------------------------------------------------------------
def fmt_hms(segundos: float) -> str:
    """HH:MM:SS (para textos e turnos)."""
    segundos = max(0.0, float(segundos or 0.0))
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def fmt_srt(segundos: float) -> str:
    """HH:MM:SS,mmm (SubRip)."""
    return _fmt_ms(segundos, sep=",")


def fmt_vtt(segundos: float) -> str:
    """HH:MM:SS.mmm (WebVTT)."""
    return _fmt_ms(segundos, sep=".")


def _fmt_ms(segundos: float, sep: str) -> str:
    segundos = max(0.0, float(segundos or 0.0))
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    ms = int(round((segundos - int(segundos)) * 1000))
    if ms == 1000:  # arredondamento
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


# ---------------------------------------------------------------------------
# Locutores
# ---------------------------------------------------------------------------
def rotulo_locutor(speaker: str | None, mapa: dict | None) -> str | None:
    """Traduz SPEAKER_00 → nome atribuído pelo usuário, se houver."""
    if speaker is None:
        return None
    if mapa and speaker in mapa:
        return mapa[speaker]
    return speaker


# ---------------------------------------------------------------------------
# Idioma
# ---------------------------------------------------------------------------
# Nomes em português dos idiomas que o VOX oferece na interface. Fora desta
# lista (a CLI aceita qualquer código ISO) mostra-se o próprio código, que é
# informação suficiente e não inventa um nome errado.
_NOMES_IDIOMA = {
    "pt": "português", "es": "espanhol", "en": "inglês", "fr": "francês",
    "de": "alemão", "it": "italiano",
}


def rotulo_idioma(params: dict | None) -> str | None:
    """Idioma da fala para exibição no documento, ex.: 'português (pt)'.

    Registra também quando o idioma foi DETECTADO em vez de informado: um
    documento probatório precisa dizer se aquilo foi uma escolha do operador ou
    um palpite da máquina.
    """
    params = params or {}
    codigo = params.get("idioma")
    if not codigo:
        return None
    nome = _NOMES_IDIOMA.get(codigo)
    rotulo = f"{nome} ({codigo})" if nome else str(codigo)
    if params.get("idioma_pedido") == "auto":
        rotulo += " — detectado automaticamente"
    return rotulo


# ---------------------------------------------------------------------------
# Turnos de fala (segmentos consecutivos do mesmo locutor)
# ---------------------------------------------------------------------------
def iter_turnos(doc: dict) -> Iterator[dict]:
    """Agrupa segmentos consecutivos do mesmo locutor em turnos.

    Cada turno: {speaker, start, end, segmentos:[...]}.
    """
    turno: dict | None = None
    for seg in doc.get("segments", []):
        spk = seg.get("speaker")
        if turno is not None and turno["speaker"] == spk:
            turno["segmentos"].append(seg)
            turno["end"] = seg.get("end", turno["end"])
        else:
            if turno is not None:
                yield turno
            turno = {
                "speaker": spk,
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
                "segmentos": [seg],
            }
    if turno is not None:
        yield turno


# ---------------------------------------------------------------------------
# Texto com marcações de fidelidade
# ---------------------------------------------------------------------------
def texto_segmento(seg: dict) -> str:
    """Texto do segmento com as marcações de fidelidade aplicadas.

    Convenções:
      - segmento marcado 'inaudivel'      → "[inaudível – HH:MM:SS]"
      - segmento marcado 'vozes_sobrepostas' → sufixo "[vozes sobrepostas]"
    O realce por palavra de baixa confiança é visual (DOCX/HTML), não textual.
    """
    flags = set(seg.get("flags", []))
    if "inaudivel" in flags:
        return f"[inaudível – {fmt_hms(seg.get('start', 0.0))}]"
    texto = (seg.get("text") or "").strip()
    if not texto:
        # Sem texto reconstruível: reconstrói pelas palavras, se houver.
        texto = " ".join(
            (w.get("word") or "").strip() for w in seg.get("words", [])
        ).strip()
    if "vozes_sobrepostas" in flags:
        texto = f"{texto} [vozes sobrepostas]".strip()
    return texto


def texto_turno(turno: dict) -> str:
    """Concatena o texto dos segmentos de um turno."""
    partes = [texto_segmento(s) for s in turno["segmentos"]]
    return " ".join(p for p in partes if p).strip()
