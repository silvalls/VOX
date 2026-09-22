"""Compatibilidade de ambiente (Windows) — neutraliza minas de dependências.

O SpeechBrain 1.x (arrastado como dependência) registra vários *lazy modules* de
integrações opcionais (k2, flair, …). Quando o pyannote/whisperx carrega o VAD,
o ``lightning`` chama ``inspect.getmodule()``, que percorre ``sys.modules`` e
acessa ``__file__`` de cada um. Ao tocar num lazy-module do SpeechBrain, o
``__getattr__`` dispara o import da integração — que falha (dep opcional ausente)
e **derruba a transcrição** com erros como "No module named 'k2'/'flair'".

Correção cirúrgica (idempotente): para acessos a *dunders* (``__file__`` etc.),
o ``LazyModule`` passa a lançar ``AttributeError`` (comportamento correto),
em vez de disparar o import. Isso conserta todas as integrações de uma vez,
sem instalar k2/flair/etc. Chamado antes de importar o whisperx.
"""

from __future__ import annotations

import importlib.util
import sys
import types

_protegido = False


def proteger_speechbrain() -> None:
    global _protegido
    if _protegido:
        return
    _protegido = True

    # Rede de segurança: stub inofensivo do 'k2' (não existe no Windows).
    if importlib.util.find_spec("k2") is None and "k2" not in sys.modules:
        sys.modules["k2"] = types.ModuleType("k2")

    try:
        from speechbrain.utils import importutils as _sbi
    except Exception:
        return  # SpeechBrain não instalado: nada a fazer

    lazy = getattr(_sbi, "LazyModule", None)
    if lazy is None or getattr(lazy, "_degravador_patched", False):
        return

    _orig = lazy.__getattr__

    def _getattr_seguro(self, attr):
        # Não dispara import lazy só para o inspect ler dunders (__file__…).
        if attr.startswith("__") and attr.endswith("__"):
            raise AttributeError(attr)
        return _orig(self, attr)

    lazy.__getattr__ = _getattr_seguro
    lazy._degravador_patched = True
