"""Saída VTT — legendas WebVTT com identificação de locutor."""

from __future__ import annotations

from pathlib import Path

from ._comum import fmt_vtt, texto_segmento, rotulo_locutor


def _tem_multiplos_locutores(doc: dict) -> bool:
    speakers = {s.get("speaker") for s in doc.get("segments", [])}
    speakers.discard(None)
    return len(speakers) > 1


def exportar(
    doc: dict,
    caminho: str | Path,
    *,
    mapa_locutores: dict | None = None,
    **_opts,
) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    identificar = _tem_multiplos_locutores(doc)
    blocos: list[str] = ["WEBVTT", ""]
    for seg in doc.get("segments", []):
        texto = texto_segmento(seg)
        if not texto:
            continue
        inicio = fmt_vtt(seg.get("start", 0.0))
        fim = fmt_vtt(seg.get("end", seg.get("start", 0.0)))
        if identificar and seg.get("speaker"):
            nome = rotulo_locutor(seg["speaker"], mapa_locutores)
            texto = f"<v {nome}>{texto}"
        blocos.append(f"{inicio} --> {fim}\n{texto}\n")

    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(blocos))
    return caminho
