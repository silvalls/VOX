"""Exportadores. Todos derivam do JSON (fonte de verdade), sem reprocessar.

Registro central de formatos → função exportadora ``(doc, caminho_saida, **opts)``.
"""

from __future__ import annotations

from . import json as _json
from . import txt as _txt
from . import srt as _srt
from . import vtt as _vtt
from . import docx as _docx
from . import pdf as _pdf
from . import html as _html

# formato → (função, extensão)
EXPORTADORES = {
    "json": (_json.salvar_em, ".json"),
    "txt": (_txt.exportar, ".txt"),
    "srt": (_srt.exportar, ".srt"),
    "vtt": (_vtt.exportar, ".vtt"),
    "docx": (_docx.exportar, ".docx"),
    "pdf": (_pdf.exportar, ".pdf"),
    "html": (_html.exportar, ".html"),
}

FORMATOS_VALIDOS = tuple(EXPORTADORES.keys())

__all__ = ["EXPORTADORES", "FORMATOS_VALIDOS"]
