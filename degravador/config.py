"""Configuração central do Degravador.

Reúne, num só lugar, os limiares de fidelidade, os parâmetros de transcrição e
os caminhos de cache. Instituições podem sobrescrever via arquivo de estilo ou
variáveis de ambiente sem tocar no restante do código.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Idioma e modelo
# ---------------------------------------------------------------------------
IDIOMA = "pt"          # padrão; sobrescrevível por --idioma / interface
IDIOMA_AUTO = "auto"   # deixa o Whisper detectar nos primeiros 30 s do áudio

# Idiomas oferecidos na interface gráfica: (código, rótulo).
#
# A lista precisa conter APENAS idiomas cujo modelo de alinhamento está embutido
# no instalador (ver empacotar/README.md). Numa máquina instalada o
# HF_HUB_OFFLINE=1 impede download: oferecer um idioma fora do bundle produziria
# uma degravação sem timestamps por palavra, sem o usuário entender por quê.
# A CLI (--idioma) não tem essa restrição — lá vale qualquer código ISO.
IDIOMAS_INTERFACE: tuple[tuple[str, str], ...] = (
    ("pt", "Português (Brasil)"),
    ("es", "Espanhol"),
    ("en", "Inglês"),
    ("fr", "Francês"),
    ("de", "Alemão"),
    ("it", "Italiano"),
    (IDIOMA_AUTO, "Detectar automaticamente"),
)


def idiomas_com_alinhamento() -> set[str]:
    """Códigos ISO com modelo de alinhamento por palavra no whisperx instalado.

    Fora desta lista o Whisper ainda transcreve (são 99 idiomas), mas não há
    forced alignment: sem timestamps nem scores por palavra.

    Lida do próprio whisperx em vez de copiada, para não apodrecer a cada
    atualização da biblioteca. Import preguiçoso (o módulo é pesado), como em
    transcricao.py e perfis.py.
    """
    try:
        from whisperx.alignment import (
            DEFAULT_ALIGN_MODELS_HF as _H,
            DEFAULT_ALIGN_MODELS_TORCH as _T,
        )
    except Exception:
        # Sem whisperx instalado não há o que alinhar; quem chama trata a ausência.
        return set()
    return set(_T) | set(_H)


# Nome do modelo por perfil (ver perfis.py para a seleção automática).
MODELO_TURBO = "large-v3-turbo"
MODELO_MAXIMO = "large-v3"


# ---------------------------------------------------------------------------
# Limiares de fidelidade (Fase 3) — todos ajustáveis
# ---------------------------------------------------------------------------
@dataclass
class LimiaresFidelidade:
    # Segmento marcado como baixa confiança / candidato a [inaudível]
    avg_logprob_min: float = -1.0        # abaixo disso: baixa confiança
    no_speech_prob_max: float = 0.6      # acima disso: provável silêncio/ruído
    compression_ratio_max: float = 2.4   # acima disso: provável alucinação/repetição

    # Palavra marcada como baixa confiança (score do alinhamento wav2vec2)
    word_score_min: float = 0.4

    # Guarda de alinhamento: duração de palavra considerada implausível
    word_dur_min_s: float = 0.0          # <= 0 é sempre implausível
    word_dur_max_s: float = 30.0         # palavra "durando" mais que isso é bug de alinhamento


# ---------------------------------------------------------------------------
# Parâmetros de transcrição (faster-whisper via WhisperX)
# ---------------------------------------------------------------------------
@dataclass
class ParamsTranscricao:
    # Fidelidade: temperatura única, SEM fallback amostrado.
    # Um segmento ruim é marcado como baixa confiança em vez de "chutado".
    temperatures: tuple[float, ...] = (0.0,)
    condition_on_previous_text: bool = False
    beam_size: int = 5
    # Guardas de alucinação do faster-whisper:
    compression_ratio_threshold: float = 2.4
    log_prob_threshold: float = -1.0
    no_speech_threshold: float = 0.6
    # Contém alucinações do Whisper em trechos de silêncio (faster-whisper).
    hallucination_silence_threshold: float = 2.0
    # batch_size do WhisperX (reduzir se faltar VRAM no perfil 4 GB):
    batch_size: int = 16
    # Viés de vocabulário: termos/nomes esperados no contexto (siglas, jargão,
    # nomes próprios). Ajuda a grafá-los corretamente. NÃO reescreve o texto —
    # apenas orienta o reconhecimento. Vazio por padrão (neutro).
    initial_prompt: str | None = None


# ---------------------------------------------------------------------------
# Caminhos de cache (modelos baixados sob demanda ficam aqui)
# ---------------------------------------------------------------------------
def _cache_base() -> Path:
    # Respeita HF_HOME se definido; senão usa ~/.cache
    base = os.environ.get("HF_HOME")
    if base:
        return Path(base)
    return Path.home() / ".cache"


CACHE_HUGGINGFACE = _cache_base() / "huggingface"
CACHE_WHISPERX = _cache_base() / "whisperx"


# ---------------------------------------------------------------------------
# Agregado carregável/serializável
# ---------------------------------------------------------------------------
@dataclass
class Config:
    idioma: str = IDIOMA
    limiares: LimiaresFidelidade = field(default_factory=LimiaresFidelidade)
    params: ParamsTranscricao = field(default_factory=ParamsTranscricao)

    def para_metadata(
        self,
        *,
        idioma_efetivo: str | None = None,
        alinhamento: bool | None = None,
    ) -> dict:
        """Subconjunto serializável para gravar no JSON (auditabilidade).

        ``idioma_efetivo`` é o idioma REALMENTE usado na transcrição — com
        ``--idioma auto`` o pedido é "auto" e o efetivo é o que o Whisper
        detectou. É o efetivo que vale para auditoria; o pedido fica registrado
        ao lado, em ``idioma_pedido``.

        ``alinhamento`` diz se houve forced alignment por palavra. ``False``
        significa que os scores por palavra NÃO foram medidos — distinto de
        terem sido medidos e saído bons. ``None`` = não registrado.
        """
        return {
            "idioma": idioma_efetivo or self.idioma,
            "idioma_pedido": self.idioma,
            "alinhamento_por_palavra": alinhamento,
            "temperatures": list(self.params.temperatures),
            "condition_on_previous_text": self.params.condition_on_previous_text,
            "beam_size": self.params.beam_size,
            "vad": "silero (via whisperx)",
            "initial_prompt": self.params.initial_prompt,
            "limiares": asdict(self.limiares),
        }


# Instância padrão usada pela CLI quando nada é sobrescrito.
CONFIG_PADRAO = Config()
