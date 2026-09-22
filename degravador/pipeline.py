"""Pipeline de degravação reutilizável (CLI e app desktop).

Encapsula: extração → transcrição → alinhamento → diarização → fidelidade →
documento JSON (fonte de verdade). Aceita um callback de ``progresso(pct, msg)``
para a interface mostrar uma barra.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import CONFIG_PADRAO
from .perfis import selecionar_perfil


class CanceladoError(Exception):
    """Processamento cancelado pelo usuário."""


# Fator aproximado de velocidade (× tempo real) por perfil, para estimativa.
_FATOR_ESTIMATIVA = {"maximo": 10.0, "recomendado": 16.0, "cpu": 0.9}


def _saida(base: Path, ext: str) -> Path:
    return base.parent / (base.name + ext)


def degravar(
    caminho: str | Path,
    outdir: str | Path,
    *,
    perfil_nome: str | None = None,
    diarizador: str = "auto",
    num_speakers: int | None = None,
    normalizar: bool = True,
    vocabulario: str | None = None,
    idioma: str | None = None,
    salvar_json: bool = True,
    progresso=None,
    cancelado=None,
) -> dict:
    """Processa um arquivo e retorna (doc, caminho_json, caminho_wav).

    ``vocabulario`` é o caminho de um arquivo de termos (viés de reconhecimento).
    ``idioma`` é o código ISO da fala (``'auto'`` deixa o Whisper detectar);
    ``None`` mantém o padrão de ``CONFIG_PADRAO``.
    ``progresso`` é ``callable(pct:int, msg:str)`` opcional.
    """
    from dataclasses import replace

    prog = progresso or (lambda pct, msg: None)

    def _ck():
        if cancelado and cancelado():
            raise CanceladoError()

    from . import extracao
    from .transcricao import transcrever
    from .fidelidade import aplicar_marcacoes
    from .saidas import json as sj

    entrada = Path(caminho)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    base = outdir / entrada.stem

    # Config do processamento. As opções se ACUMULAM: cada replace() parte do
    # cfg anterior, nunca de CONFIG_PADRAO — senão a segunda desfaz a primeira.
    cfg = CONFIG_PADRAO
    if idioma:
        cfg = replace(cfg, idioma=idioma)
    if vocabulario:
        from . import vocabulario as _voc
        prompt = _voc.prompt_de_arquivo(vocabulario)
        cfg = replace(cfg, params=replace(cfg.params, initial_prompt=prompt))

    perfil = selecionar_perfil(perfil_nome)

    # 1) Extração + auditoria
    _ck()
    prog(5, "Extraindo e normalizando o áudio…")
    dur = extracao.duracao_segundos(entrada)
    sha = extracao.sha256_arquivo(entrada)
    wav = extracao.extrair_audio(entrada, _saida(base, ".deg.wav"), normalizar=normalizar)

    # 2) Transcrição + alinhamento
    _ck()
    fator = _FATOR_ESTIMATIVA.get(perfil.nome, 12.0)
    est_min = (dur / fator / 60) if dur else 0
    msg = "Transcrevendo…"
    if dur:
        msg = f"Transcrevendo… ({dur/60:.0f} min de áudio · estimativa ~{max(1, round(est_min))} min)"
    prog(25, msg)
    rt = transcrever(wav, perfil, cfg)
    segments = rt.segments
    num = None
    sobre = None
    backend = None

    # 3) Diarização
    _ck()
    if diarizador != "nenhum":
        prog(75, "Identificando os interlocutores…")
        try:
            from .diarizacao import diarizar
            rd = diarizar(
                rt.audio, segments, perfil,
                backend=diarizador, hf_token=os.environ.get("HF_TOKEN"),
                num_speakers=num_speakers,
            )
            segments = rd.segments
            num = rd.num_speakers
            sobre = rd.sobreposicoes
            backend = rd.backend
        except Exception as e:  # best-effort
            prog(80, f"Diarização indisponível ({type(e).__name__}); seguindo sem locutores.")

    # 4) Fidelidade
    prog(92, "Marcando trechos incertos…")
    aplicar_marcacoes(segments, cfg.limiares, sobre)

    # 5) Documento (fonte de verdade)
    metadata = {
        "arquivo": entrada.name,
        "arquivo_caminho": str(entrada.resolve()),
        "sha256": sha,
        "duracao_s": dur,
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "modelo": perfil.modelo,
        "versao_app": __version__,
        "perfil": perfil.nome,
        "num_speakers": num,
        "diarizador": backend,
        # Idioma efetivo e disponibilidade de alinhamento vêm da transcrição,
        # não do pedido: é o que de fato valeu que tem valor de auditoria.
        "params": cfg.para_metadata(
            idioma_efetivo=rt.language, alinhamento=rt.alinhamento
        ),
        "audio_arquivo": wav.name,
        "revisado_por": None,
    }
    doc = sj.construir_documento(metadata, segments)
    caminho_json = None
    if salvar_json:
        caminho_json = _saida(base, ".json")
        sj.salvar_em(doc, caminho_json)

    prog(100, "Concluído.")
    return {"doc": doc, "json": str(caminho_json) if caminho_json else None,
            "wav": str(wav), "base": str(base)}
