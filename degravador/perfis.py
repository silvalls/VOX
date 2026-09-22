"""Detecção de hardware e seleção de perfil.

No startup, detectamos GPU/VRAM e escolhemos o perfil adequado. O usuário sempre
pode sobrescrever com ``--perfil``. O perfil ``recomendado`` (alvo primário do
projeto, GPU de 4 GB) pode ser FORÇADO mesmo numa GPU grande — útil para o
desenvolvedor validar o caminho de produção na própria máquina.

O import de ``torch`` é preguiçoso: este módulo pode ser importado (e ``--help``
funcionar) mesmo antes de o PyTorch estar instalado.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import MODELO_TURBO, MODELO_MAXIMO


PERFIS_VALIDOS = ("maximo", "recomendado", "cpu")


@dataclass
class Perfil:
    nome: str                 # maximo | recomendado | cpu
    device: str               # "cuda" | "cpu"
    modelo: str               # nome do modelo Whisper
    compute_type: str         # float16 | int8_float16 | int8
    diarizacao_device: str    # onde rodar o pyannote
    # Sequencial: descarrega o modelo ASR da VRAM ANTES de diarizar
    # (evita disputa de VRAM no perfil 4 GB).
    diarizacao_sequencial: bool
    vram_gb: float | None = None
    gpu_nome: str | None = None

    def resumo(self) -> str:
        onde = self.device.upper()
        if self.vram_gb:
            onde += f" · {self.gpu_nome} ({self.vram_gb:.1f} GB VRAM)"
        seq = "sequencial" if self.diarizacao_sequencial else "concorrente"
        return (
            f"Perfil '{self.nome}': {onde} | modelo {self.modelo} "
            f"({self.compute_type}) | diarização {self.diarizacao_device} ({seq})"
        )


def _info_gpu() -> tuple[bool, float, str]:
    """Retorna (tem_cuda, vram_gb_maior, nome). Seguro sem torch instalado."""
    try:
        import torch
    except Exception:
        return False, 0.0, ""
    if not torch.cuda.is_available():
        return False, 0.0, ""
    # Se houver múltiplas GPUs, considera a de maior VRAM.
    melhor_vram = 0.0
    melhor_nome = ""
    for i in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(i)
        vram = props.total_memory / (1024 ** 3)
        if vram > melhor_vram:
            melhor_vram = vram
            melhor_nome = props.name
    return True, melhor_vram, melhor_nome


def _perfil_recomendado(device: str, vram: float, nome: str) -> Perfil:
    """Perfil 4 GB: turbo int8_float16, diarização sequencial."""
    return Perfil(
        nome="recomendado",
        device=device,
        modelo=MODELO_TURBO,
        compute_type="int8_float16" if device == "cuda" else "int8",
        diarizacao_device=device,
        diarizacao_sequencial=True,
        vram_gb=vram or None,
        gpu_nome=nome or None,
    )


def _perfil_maximo(vram: float, nome: str) -> Perfil:
    return Perfil(
        nome="maximo",
        device="cuda",
        modelo=MODELO_MAXIMO,
        compute_type="float16",
        diarizacao_device="cuda",
        diarizacao_sequencial=False,
        vram_gb=vram or None,
        gpu_nome=nome or None,
    )


def _perfil_cpu() -> Perfil:
    return Perfil(
        nome="cpu",
        device="cpu",
        modelo=MODELO_TURBO,
        compute_type="int8",
        diarizacao_device="cpu",
        diarizacao_sequencial=True,
    )


def selecionar_perfil(forcado: str | None = None) -> Perfil:
    """Escolhe o perfil.

    - ``forcado`` em {maximo, recomendado, cpu} sobrescreve a detecção.
      Note que ``recomendado`` numa GPU grande é intencionalmente permitido:
      força o caminho de produção 4 GB (turbo + diarização sequencial).
    - Sem ``forcado``: detecta VRAM e decide (>=10 GB → máximo; 4–10 GB →
      recomendado; sem GPU → cpu).
    """
    tem_cuda, vram, nome = _info_gpu()

    if forcado:
        forcado = forcado.lower()
        if forcado not in PERFIS_VALIDOS:
            raise ValueError(
                f"Perfil inválido: {forcado!r}. Use um de {PERFIS_VALIDOS}."
            )
        if forcado == "cpu":
            return _perfil_cpu()
        if not tem_cuda:
            raise RuntimeError(
                f"Perfil '{forcado}' exige GPU CUDA, mas nenhuma foi detectada. "
                "Use --perfil cpu."
            )
        if forcado == "maximo":
            return _perfil_maximo(vram, nome)
        return _perfil_recomendado("cuda", vram, nome)

    # Automático
    if not tem_cuda:
        return _perfil_cpu()
    # No build offline os modelos são embutidos e o large-v3 completo NÃO vai
    # junto: mesmo em GPU grande, mantemos o turbo (que está no bundle).
    import os
    if vram >= 10.0 and not os.environ.get("VOX_OFFLINE"):
        return _perfil_maximo(vram, nome)
    return _perfil_recomendado("cuda", vram, nome)
