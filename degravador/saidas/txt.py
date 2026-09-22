"""Saída TXT — texto corrido com locutores e timestamps de turno."""

from __future__ import annotations

from pathlib import Path

from ._comum import iter_turnos, texto_turno, fmt_hms, rotulo_locutor


def _tem_multiplos_locutores(doc: dict) -> bool:
    speakers = {s.get("speaker") for s in doc.get("segments", [])}
    speakers.discard(None)
    return len(speakers) > 1


def exportar(
    doc: dict,
    caminho: str | Path,
    *,
    mapa_locutores: dict | None = None,
    sem_timestamps: bool = False,
    **_opts,
) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    identificar = _tem_multiplos_locutores(doc)
    linhas: list[str] = []

    for turno in iter_turnos(doc):
        texto = texto_turno(turno)
        if not texto:
            continue
        prefixo = ""
        if identificar:
            nome = rotulo_locutor(turno["speaker"], mapa_locutores) or "LOCUTOR"
            ts = "" if sem_timestamps else f" ({fmt_hms(turno['start'])})"
            prefixo = f"{nome}{ts}: "
        elif not sem_timestamps:
            prefixo = f"({fmt_hms(turno['start'])}) "
        linhas.append(f"{prefixo}{texto}")

    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n\n".join(linhas))
        f.write("\n")
    return caminho
