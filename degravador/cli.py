"""Interface de linha de comando do Degravador.

Fluxo padrão (processar):
    entrada → extração (ffmpeg) → transcrição (WhisperX) → alinhamento
            → diarização (pyannote) → marcações de fidelidade → saídas

Fluxo de re-export (sem reprocessar áudio):
    --reexportar clipe.json → aplica locutores/glossário → novas saídas

Uso:
    degravador video.mp4
    degravador reuniao.mkv --num-speakers 3 --formatos txt,srt,json,docx,html
    degravador arquivo.mp4 --perfil recomendado        # força o caminho 4 GB
    degravador entrevista.mp4 --idioma es              # fala em outro idioma
    degravador material.mp4 --idioma auto              # deixa o Whisper detectar
    degravador --reexportar clipe.json --formatos docx --locutores "Juiz,Testemunha"
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import CONFIG_PADRAO, IDIOMA, IDIOMA_AUTO
from .perfis import selecionar_perfil, PERFIS_VALIDOS
from .saidas import EXPORTADORES, FORMATOS_VALIDOS


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _carregar_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass  # .env é opcional


def _resolver_estilo(caminho: str | None) -> str | None:
    if caminho:
        return caminho
    padrao = Path("estilos") / "oficial_abnt.json"
    return str(padrao) if padrao.exists() else None


def _mapa_locutores(doc: dict, nomes_csv: str | None) -> dict | None:
    """Constrói {SPEAKER_00: 'Juiz', ...} a partir da lista --locutores."""
    if not nomes_csv:
        return None
    from .saidas.docx import _locutores_em_ordem
    nomes = [n.strip() for n in nomes_csv.split(",") if n.strip()]
    ordem = _locutores_em_ordem(doc)
    return {spk: nome for spk, nome in zip(ordem, nomes)}


def _saida(base: Path, ext: str) -> Path:
    """Anexa a extensão ao nome COMPLETO (não usa with_suffix, que 'comeria'
    pontos internos de nomes como 'audio 16.32.53')."""
    return base.parent / (base.name + ext)


def _formatos(valor: str) -> list[str]:
    fmts = [f.strip().lower() for f in valor.split(",") if f.strip()]
    invalidos = [f for f in fmts if f not in FORMATOS_VALIDOS]
    if invalidos:
        raise argparse.ArgumentTypeError(
            f"Formato(s) inválido(s): {invalidos}. Válidos: {FORMATOS_VALIDOS}"
        )
    return fmts


def _exportar_todos(
    doc: dict,
    formatos: list[str],
    base: Path,
    *,
    mapa_locutores=None,
    sem_timestamps=False,
    caminho_estilo=None,
    audio_src=None,
    log=print,
) -> None:
    for fmt in formatos:
        func, ext = EXPORTADORES[fmt]
        destino = _saida(base, ext)
        func(
            doc, destino,
            mapa_locutores=mapa_locutores,
            sem_timestamps=sem_timestamps,
            caminho_estilo=caminho_estilo,
            audio_src=audio_src,
        )
        log(f"  ✓ {destino.name}")


# ---------------------------------------------------------------------------
# Fluxo: processar (pipeline completo)
# ---------------------------------------------------------------------------
def _processar(args) -> int:
    from . import extracao
    from .saidas import json as saida_json

    entrada = Path(args.entrada)
    if not entrada.exists():
        print(f"ERRO: arquivo não encontrado: {entrada}", file=sys.stderr)
        return 2

    outdir = Path(args.saida) if args.saida else entrada.parent
    outdir.mkdir(parents=True, exist_ok=True)
    base = outdir / entrada.stem

    # Perfil
    try:
        perfil = selecionar_perfil(args.perfil)
    except (ValueError, RuntimeError) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 2
    if args.modelo:
        perfil.modelo = args.modelo
    print(perfil.resumo())

    # 1) Extração + metadados de auditoria
    print("→ Extraindo e normalizando áudio (ffmpeg)…")
    try:
        dur = extracao.duracao_segundos(entrada)
        sha = extracao.sha256_arquivo(entrada)
        wav = extracao.extrair_audio(
            entrada, _saida(base, ".deg.wav"),
            normalizar=not args.sem_normalizacao,
        )
    except (extracao.FFmpegNaoEncontrado, RuntimeError, FileNotFoundError) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 2
    if dur:
        print(f"  duração: {dur/60:.1f} min")
        if perfil.device == "cpu":
            print("  aviso: perfil CPU — arquivos longos podem levar bastante tempo.")

    # 2) Transcrição + alinhamento
    # cfg (não CONFIG_PADRAO) daqui em diante: as marcações de fidelidade e o
    # metadata precisam refletir as opções desta execução, e não o padrão.
    cfg = replace(CONFIG_PADRAO, idioma=args.idioma)
    print("→ Transcrevendo…")
    try:
        from .transcricao import transcrever
        rt = transcrever(wav, perfil, cfg)
    except ImportError as e:
        import traceback
        traceback.print_exc()
        print(_erro_dependencia(e), file=sys.stderr)
        return 3
    segments = rt.segments
    num_speakers = None
    sobreposicoes = None
    backend_diar = None

    # 3) Diarização (opcional). Backend 'auto' = pyannote se houver token, senão sem-token.
    diar = "nenhum" if args.sem_diarizacao else args.diarizador
    if diar != "nenhum":
        print("→ Diarizando…")
        try:
            from .diarizacao import diarizar, TokenHFAusente
            rd = diarizar(
                rt.audio, segments, perfil,
                backend=diar,
                hf_token=os.environ.get("HF_TOKEN"),
                num_speakers=args.num_speakers,
                min_speakers=args.min_speakers,
                max_speakers=args.max_speakers,
            )
            segments = rd.segments
            num_speakers = rd.num_speakers
            sobreposicoes = rd.sobreposicoes
            backend_diar = rd.backend
            print(f"  {num_speakers} interlocutor(es) — backend: {rd.backend}.")
        except TokenHFAusente as e:
            print(f"AVISO: {e}\n  Continuando SEM diarização.", file=sys.stderr)
        except Exception as e:
            print(f"AVISO: diarização falhou ({type(e).__name__}: {e}).\n"
                  "  Continuando SEM diarização.", file=sys.stderr)

    # 4) Marcações de fidelidade
    from .fidelidade import aplicar_marcacoes
    aplicar_marcacoes(segments, cfg.limiares, sobreposicoes)

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
        "num_speakers": num_speakers,
        "diarizador": backend_diar,
        "params": cfg.para_metadata(
            idioma_efetivo=rt.language, alinhamento=rt.alinhamento
        ),
        "audio_arquivo": wav.name,
        "revisado_por": args.responsavel,
    }
    doc = saida_json.construir_documento(metadata, segments)

    # JSON é sempre gravado (fonte de verdade), mesmo se não pedido.
    caminho_json = _saida(base, ".json")
    saida_json.salvar_em(doc, caminho_json)
    print(f"  ✓ {caminho_json.name} (fonte de verdade)")

    # 6) Demais saídas (derivadas; glossário aplicado só aqui)
    formatos = [f for f in args.formatos if f != "json"]
    doc_saida = _aplicar_glossario(doc, args.glossario)
    mapa = _mapa_locutores(doc, args.locutores)
    _exportar_todos(
        doc_saida, formatos, base,
        mapa_locutores=mapa,
        sem_timestamps=args.sem_timestamps,
        caminho_estilo=_resolver_estilo(args.estilo),
        audio_src=wav.name,
    )
    print("Concluído.")
    return 0


# ---------------------------------------------------------------------------
# Fluxo: re-export (a partir do JSON, sem reprocessar)
# ---------------------------------------------------------------------------
def _reexportar(args) -> int:
    from .saidas import json as saida_json

    caminho_json = Path(args.reexportar)
    if not caminho_json.exists():
        print(f"ERRO: JSON não encontrado: {caminho_json}", file=sys.stderr)
        return 2
    doc = saida_json.carregar(caminho_json)

    outdir = Path(args.saida) if args.saida else caminho_json.parent
    base = outdir / caminho_json.stem  # stem já remove só o '.json' final

    formatos = [f for f in args.formatos if f != "json"] or ["docx"]
    mapa = _mapa_locutores(doc, args.locutores)
    audio_src = doc.get("metadata", {}).get("audio_arquivo")
    estilo = _resolver_estilo(args.estilo)

    # --- Com correção humana: gera 'corrigido' + mantém 'original' como cópia ---
    if args.corrigir:
        from . import correcao
        from .saidas import json as sj
        corr = correcao.carregar(args.corrigir)
        # Nomes de locutores atribuídos pelo usuário na interface (se houver).
        if corr.get("locutores"):
            mapa = corr["locutores"]
        doc_corr = correcao.aplicar(doc, corr, revisado_por=args.responsavel)
        doc_corr_g = _aplicar_glossario(doc_corr, args.glossario)
        doc_orig_g = _aplicar_glossario(doc, args.glossario)

        print(f"→ Aplicando correção humana de {Path(args.corrigir).name} "
              f"(mantendo o original como cópia)…")
        # JSON corrigido preservado ao lado do original (que fica intacto).
        sj.salvar_em(doc_corr, _saida(base, ".corrigido.json"))
        print(f"  ✓ {_saida(base, '.corrigido.json').name}")
        _exportar_todos(
            doc_corr_g, formatos, _saida(base, ".corrigido"),
            mapa_locutores=mapa, sem_timestamps=args.sem_timestamps,
            caminho_estilo=estilo, audio_src=audio_src,
        )
        _exportar_todos(
            doc_orig_g, formatos, _saida(base, ".original"),
            mapa_locutores=mapa, sem_timestamps=args.sem_timestamps,
            caminho_estilo=estilo, audio_src=audio_src,
        )
        print("Concluído.")
        return 0

    doc_saida = _aplicar_glossario(doc, args.glossario)
    print(f"→ Re-exportando a partir de {caminho_json.name} (sem reprocessar)…")
    _exportar_todos(
        doc_saida, formatos, base,
        mapa_locutores=mapa,
        sem_timestamps=args.sem_timestamps,
        caminho_estilo=estilo,
        audio_src=audio_src,
    )
    print("Concluído.")
    return 0


def _aplicar_glossario(doc: dict, caminho_csv: str | None) -> dict:
    if not caminho_csv:
        return doc
    from . import glossario
    mapa = glossario.carregar(caminho_csv)
    return glossario.aplicar(doc, mapa)


def _erro_dependencia(e: ImportError) -> str:
    return (
        f"ERRO: dependência não instalada ({e.name}).\n"
        "Instale o PyTorch adequado à sua GPU e depois as dependências:\n"
        "  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128\n"
        "  pip install -r requirements.txt\n"
        "(veja as notas de GPU/Blackwell no README.md)"
    )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def _construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="degravador",
        description="Degravação automática local, fiel e auditável, em pt-BR.",
    )
    p.add_argument("entrada", nargs="?", help="arquivo de vídeo ou áudio")
    p.add_argument("--reexportar", metavar="JSON",
                   help="re-exporta a partir de um JSON existente (não reprocessa)")
    p.add_argument("--corrigir", metavar="CORRECAO_JSON",
                   help="aplica uma correção humana (.correcao.json) sobre o JSON de "
                        "--reexportar: gera a versão 'corrigido' e mantém a 'original'")
    p.add_argument("--formatos", type=_formatos, default=["json", "txt", "docx"],
                   help="lista separada por vírgula: %s" % ",".join(FORMATOS_VALIDOS))
    p.add_argument("--perfil", choices=PERFIS_VALIDOS,
                   help="força o perfil de hardware (recomendado = caminho 4 GB)")
    p.add_argument("--modelo", help="sobrescreve o modelo Whisper (ex.: large-v3)")
    p.add_argument("--idioma", default=IDIOMA, metavar="ISO",
                   help=f"código ISO do idioma da fala (padrão: {IDIOMA}); "
                        f"'{IDIOMA_AUTO}' deixa o Whisper detectar. Informar o "
                        "idioma é mais fiel do que deixar detectar. Idiomas sem "
                        "modelo de alinhamento transcrevem, mas ficam sem "
                        "timestamps/scores por palavra")
    p.add_argument("--num-speakers", type=int, help="fixa o nº de interlocutores")
    p.add_argument("--min-speakers", type=int, help="mínimo de interlocutores")
    p.add_argument("--max-speakers", type=int, help="máximo de interlocutores")
    p.add_argument("--diarizador", choices=["auto", "pyannote", "speechbrain", "nenhum"],
                   default="auto",
                   help="motor de diarização (auto = pyannote se houver token, "
                        "senão speechbrain sem token)")
    p.add_argument("--sem-diarizacao", action="store_true",
                   help="desativa a identificação de locutores (= --diarizador nenhum)")
    p.add_argument("--locutores", help='nomes em ordem, ex.: "Juiz,Testemunha,Promotor"')
    p.add_argument("--glossario", metavar="CSV",
                   help="substituições determinísticas (aplicadas ao texto derivado)")
    p.add_argument("--sem-timestamps", action="store_true",
                   help="oculta os timestamps por turno")
    p.add_argument("--sem-normalizacao", action="store_true",
                   help="não aplica loudnorm na extração")
    p.add_argument("--estilo", metavar="JSON",
                   help="arquivo de estilo do DOCX (padrão: estilos/oficial_abnt.json)")
    p.add_argument("--responsavel", help="nome do responsável pela conferência (metadados)")
    p.add_argument("--saida", metavar="DIR", help="pasta de saída (padrão: junto da entrada)")
    p.add_argument("--version", action="version", version=f"Degravador {__version__}")
    return p


def _forcar_utf8() -> None:
    # O console do Windows costuma usar cp1252 e quebra em caracteres como
    # → · ✓ …  Forçamos UTF-8 na saída (funciona também quando redirecionada).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _forcar_utf8()
    from ._offline import configurar
    configurar()          # modelos embutidos + offline, se instalado
    _carregar_env()
    parser = _construir_parser()
    args = parser.parse_args(argv)

    if args.reexportar:
        return _reexportar(args)
    if not args.entrada:
        parser.error("informe um arquivo de entrada ou use --reexportar JSON")
    return _processar(args)


if __name__ == "__main__":
    raise SystemExit(main())
