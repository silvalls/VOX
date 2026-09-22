"""Testes do suporte a múltiplos idiomas — sem baixar modelo nenhum.

O ``whisperx`` é substituído por um dublê em ``sys.modules``: o que se testa
aqui é a LÓGICA de escolha de idioma e a guarda de alinhamento, não a
biblioteca. Cada teste declara o que o dublê deve fazer (detectar tal idioma,
falhar ao carregar o modelo de alinhamento) e verifica o que sai.
"""

from __future__ import annotations

import sys
import types
from dataclasses import replace

import pytest

from degravador.config import CONFIG_PADRAO, IDIOMA_AUTO
from degravador.perfis import Perfil


PERFIL = Perfil(
    nome="cpu", device="cpu", modelo="large-v3-turbo", compute_type="int8",
    diarizacao_device="cpu", diarizacao_sequencial=True,
)


class _ModeloFalso:
    """Dublê do modelo ASR: registra o idioma recebido e devolve segmentos fixos."""

    def __init__(self, registro: dict, detectado: str | None):
        self._registro = registro
        self._detectado = detectado

    def transcribe(self, audio, batch_size=None, language=None):
        self._registro["language_transcribe"] = language
        return {
            "language": self._detectado,
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "Bom dia.",
                 "avg_logprob": -0.2, "no_speech_prob": 0.01, "compression_ratio": 1.2},
            ],
        }


@pytest.fixture
def whisperx_falso(monkeypatch):
    """Injeta um whisperx dublê. Devolve o dicionário de registro das chamadas."""
    registro: dict = {"align_chamado": False}

    def instalar(*, detectado=None, alinhamento_falha=None, idiomas=("pt", "es", "en")):
        mod = types.ModuleType("whisperx")

        def load_audio(caminho):
            return [0.0]

        def load_model(modelo, device, compute_type=None, language=None, asr_options=None):
            registro["language_load"] = language
            return _ModeloFalso(registro, detectado)

        def load_align_model(language_code=None, device=None):
            registro["align_idioma"] = language_code
            if alinhamento_falha is not None:
                raise alinhamento_falha
            return object(), {}

        def align(segmentos, modelo, metadata, audio, device, return_char_alignments=False):
            registro["align_chamado"] = True
            # O align() re-segmenta por sentença e descarta parte dos scores —
            # é justamente o comportamento que _recuperar_scores() compensa.
            return {"segments": [
                {"start": 0.0, "end": 2.0, "text": "Bom dia.", "avg_logprob": -0.2,
                 "words": [{"word": "Bom", "start": 0.0, "end": 0.5, "score": 0.9}]},
            ]}

        mod.load_audio = load_audio
        mod.load_model = load_model
        mod.load_align_model = load_align_model
        mod.align = align
        monkeypatch.setitem(sys.modules, "whisperx", mod)

        # A lista de idiomas com alinhamento é lida do whisperx; com o dublê no
        # lugar, fixamos o conjunto explicitamente.
        monkeypatch.setattr(
            "degravador.transcricao.idiomas_com_alinhamento", lambda: set(idiomas)
        )
        # Sem speechbrain real no caminho do teste.
        monkeypatch.setattr(
            "degravador._compat.proteger_speechbrain", lambda: None
        )
        return registro

    return instalar


def _transcrever(cfg, log=None):
    from degravador.transcricao import transcrever
    return transcrever("qualquer.wav", PERFIL, cfg, log=log or (lambda *a: None))


# ---------------------------------------------------------------------------
# Idioma explícito × automático
# ---------------------------------------------------------------------------
def test_idioma_explicito_e_repassado_e_nao_aciona_deteccao(whisperx_falso):
    # Com idioma forçado, o motor devolve o mesmo idioma (não há detecção).
    reg = whisperx_falso(detectado="es")
    rt = _transcrever(replace(CONFIG_PADRAO, idioma="es"))

    # Passar o código explicitamente nas duas chamadas é o que impede a
    # detecção automática do Whisper.
    assert reg["language_load"] == "es"
    assert reg["language_transcribe"] == "es"
    assert rt.language == "es"
    assert reg["align_idioma"] == "es"   # alinha no idioma certo, não no padrão pt


def test_auto_nao_passa_idioma_e_adota_o_detectado(whisperx_falso):
    reg = whisperx_falso(detectado="en")
    rt = _transcrever(replace(CONFIG_PADRAO, idioma=IDIOMA_AUTO))

    # 'auto' precisa virar None: é a ausência do parâmetro que liga a detecção.
    assert reg["language_load"] is None
    assert reg["language_transcribe"] is None
    # E o idioma efetivo é o detectado — nunca a string "auto".
    assert rt.language == "en"
    assert rt.alinhamento is True
    assert reg["align_idioma"] == "en"


def test_auto_sem_deteccao_cai_no_padrao(whisperx_falso):
    # Motor não devolveu idioma: o efetivo nunca pode ficar "auto".
    whisperx_falso(detectado=None)
    rt = _transcrever(replace(CONFIG_PADRAO, idioma=IDIOMA_AUTO))
    assert rt.language == "pt"


# ---------------------------------------------------------------------------
# Guarda de alinhamento
# ---------------------------------------------------------------------------
def test_idioma_sem_modelo_de_alinhamento_nao_quebra(whisperx_falso):
    # 'ja' transcreve, mas está fora do conjunto com modelo de alinhamento.
    reg = whisperx_falso(detectado="ja", idiomas=("pt", "es", "en"))
    linhas: list[str] = []
    rt = _transcrever(replace(CONFIG_PADRAO, idioma="ja"), log=linhas.append)

    assert reg["align_chamado"] is False       # nem tentou carregar
    assert rt.alinhamento is False
    assert rt.language == "ja"
    assert rt.segments and rt.segments[0]["text"] == "Bom dia."   # texto preservado
    assert any("sem modelo de alinhamento" in l for l in linhas)


def test_falha_ao_carregar_alinhamento_degrada_sem_perder_a_degravacao(whisperx_falso):
    # Caso da máquina instalada: idioma tem modelo, mas ele não está no bundle
    # e HF_HUB_OFFLINE=1 impede o download.
    whisperx_falso(detectado="es", alinhamento_falha=OSError("modelo ausente (offline)"))
    linhas: list[str] = []
    rt = _transcrever(replace(CONFIG_PADRAO, idioma="es"), log=linhas.append)

    assert rt.alinhamento is False
    assert rt.segments[0]["text"] == "Bom dia."
    # Os scores POR SEGMENTO sobrevivem — é o que a fidelidade.py usa.
    assert rt.segments[0]["no_speech_prob"] == 0.01
    assert any("alinhamento indisponível" in l for l in linhas)


# ---------------------------------------------------------------------------
# Metadata: o que vai para o JSON (auditabilidade)
# ---------------------------------------------------------------------------
def test_metadata_registra_idioma_efetivo_e_o_pedido():
    cfg = replace(CONFIG_PADRAO, idioma=IDIOMA_AUTO)
    meta = cfg.para_metadata(idioma_efetivo="en", alinhamento=True)

    assert meta["idioma"] == "en"           # o que valeu
    assert meta["idioma_pedido"] == "auto"  # o que foi pedido
    assert meta["alinhamento_por_palavra"] is True


def test_metadata_sem_alinhamento_fica_explicito():
    meta = replace(CONFIG_PADRAO, idioma="ja").para_metadata(
        idioma_efetivo="ja", alinhamento=False
    )
    assert meta["alinhamento_por_palavra"] is False


def test_pipeline_encadeia_idioma_e_vocabulario_sem_um_desfazer_o_outro():
    # Regressão: partir de CONFIG_PADRAO em cada replace() fazia a segunda opção
    # apagar a primeira.
    cfg = CONFIG_PADRAO
    cfg = replace(cfg, idioma="es")
    cfg = replace(cfg, params=replace(cfg.params, initial_prompt="ACME, Fulano"))

    assert cfg.idioma == "es"
    assert cfg.params.initial_prompt == "ACME, Fulano"


# ---------------------------------------------------------------------------
# Saídas: o documento tem de DIZER que não houve alinhamento
# ---------------------------------------------------------------------------
def _doc_sem_alinhamento():
    return {
        "metadata": {
            "arquivo": "audio.ogg", "criado_em": "2026-09-09T10:00:00",
            "duracao_s": 2.0, "sha256": "abc", "modelo": "large-v3-turbo",
            "versao_app": "0.1.0", "num_speakers": 1,
            "params": {"idioma": "ja", "idioma_pedido": "ja",
                       "alinhamento_por_palavra": False},
        },
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "Texto sem alinhamento.",
             "speaker": "SPEAKER_00", "flags": [], "words": []},
        ],
    }


def test_html_avisa_e_ainda_mostra_o_texto_sem_palavras():
    from degravador.saidas import html
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        p = html.exportar(_doc_sem_alinhamento(), Path(d) / "c.html")
        conteudo = p.read_text(encoding="utf-8")

    assert "aviso-alinhamento" in conteudo
    assert "não significa transcrição conferida" in conteudo
    # Sem 'words', o painel de leitura ficaria vazio: o texto tem de estar lá.
    assert "Texto sem alinhamento." in conteudo


def test_rotulo_idioma_diz_quando_foi_detectado():
    from degravador.saidas._comum import rotulo_idioma

    assert rotulo_idioma({"idioma": "pt", "idioma_pedido": "pt"}) == "português (pt)"
    assert rotulo_idioma({"idioma": "en", "idioma_pedido": "auto"}) == (
        "inglês (en) — detectado automaticamente"
    )
    # Idioma fora da lista de nomes: mostra o código, não inventa um nome.
    assert rotulo_idioma({"idioma": "ja", "idioma_pedido": "ja"}) == "ja"
    assert rotulo_idioma({}) is None
