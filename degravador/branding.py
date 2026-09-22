"""Identidade visual do VOX (nome, subtítulo, cores, logo).

Centraliza a marca para a interface (app + página de conferência). O nome do
PACOTE Python continua 'degravador' (interno); o PRODUTO é o VOX.
"""

from __future__ import annotations

import base64
import functools
from pathlib import Path

NOME = "VOX"
# Subtítulo institucional. Vazio de propósito: o produto não exibe vínculo de
# unidade/órgão. Quem consome deve OMITIR o elemento quando vazio, não renderizar
# um espaço em branco (ver saidas/html.py). Basta preencher aqui para voltar.
SUBTITULO = ""
DESCRICAO = "Degravação local, fiel e auditável — áudio ou vídeo em pt-BR."

# Paleta extraída da identidade visual (onda dourada → violeta sobre fundo quase preto).
CORES = {
    "fundo": "#0a0a14",
    "fundo2": "#141020",
    "cartao": "#17141f",
    "marca_a": "#f7b23c",   # dourado/âmbar (início)
    "marca_b": "#7b3fd6",   # roxo/violeta (fim)
    "texto": "#ececf3",
    "suave": "#a9a6bd",
    "borda": "#2a2740",
}
GRADIENTE = "linear-gradient(100deg,#f7b23c,#c26bb0,#7b3fd6)"

_LOGO = Path(__file__).parent / "webui" / "logo.png"


@functools.lru_cache(maxsize=1)
def logo_data_uri() -> str:
    """Retorna a logo como data URI (para páginas autocontidas). '' se ausente."""
    try:
        b = _LOGO.read_bytes()
        return "data:image/png;base64," + base64.b64encode(b).decode("ascii")
    except Exception:
        return ""
