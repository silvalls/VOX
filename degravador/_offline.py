"""Modo offline / modelos embutidos.

Quando o VOX é distribuído pelo instalador, os modelos e o ffmpeg vão **dentro**
do pacote. Este módulo detecta a pasta ``modelos/`` ao lado do executável (ou na
raiz do projeto, em desenvolvimento) e aponta as bibliotecas para lá,
desligando qualquer acesso à internet:

  - HF_HOME / HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE → cache do Hugging Face local;
  - TORCH_HOME → pesos do torch/hub local;
  - PATH → ffmpeg embutido;
  - savedir do SpeechBrain (ECAPA) → pasta local.

Deve ser chamado ANTES de importar whisperx/pyannote/torch (em cli.main e app.main).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ativo = False
_base_modelos: Path | None = None


def _raiz() -> Path:
    # Empacotado (PyInstaller): ao lado do executável. Em dev: raiz do projeto.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def base_modelos() -> Path | None:
    return _base_modelos


def savedir_speechbrain() -> str | None:
    if _base_modelos:
        return str(_base_modelos / "speechbrain")
    return None


def configurar() -> bool:
    """Ativa o modo offline se houver uma pasta ``modelos/`` embutida. Idempotente."""
    global _ativo, _base_modelos
    if _ativo:
        return True

    raiz = _raiz()
    modelos = raiz / "modelos"
    if not modelos.exists():
        return False  # modo desenvolvimento (usa cache do usuário + internet)

    _base_modelos = modelos
    os.environ.setdefault("HF_HOME", str(modelos / "huggingface"))
    os.environ.setdefault("TORCH_HOME", str(modelos / "torch"))
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    # ffmpeg embutido no PATH
    ffmpeg_dir = raiz / "ffmpeg"
    if ffmpeg_dir.exists():
        os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")

    # Sinaliza que os modelos são embutidos (o large-v3 completo NÃO vai no bundle):
    # a seleção automática de perfil deve ficar no turbo (recomendado), nunca "máximo".
    os.environ["VOX_OFFLINE"] = "1"

    _ativo = True
    return True
