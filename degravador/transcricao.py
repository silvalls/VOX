"""Etapas 2–3 — Transcrição (WhisperX + faster-whisper) e alinhamento.

Orquestra o WhisperX:
  1. VAD (Silero, embutido no WhisperX) segmenta apenas a fala.
  2. faster-whisper transcreve no idioma de ``cfg.idioma``, com parâmetros de
     fidelidade. ``IDIOMA_AUTO`` deixa o Whisper detectar — conveniência, não
     padrão recomendado: a detecção olha os primeiros 30 s e erra em áudio
     forense com ruído inicial ou saudação em outro idioma. Para material
     sabidamente monolíngue, informar o idioma é mais fiel.
  3. Alinhamento forçado (wav2vec2 do idioma) gera timestamps por palavra —
     quando há modelo para ele; ver a guarda em ``transcrever()``.

Gestão de VRAM: cada modelo é descarregado assim que deixa de ser usado, para
caber no perfil de 4 GB. A diarização (etapa seguinte) roda depois, já com a
VRAM liberada — ver diarizacao.py e cli.py.

O import de ``whisperx``/``torch`` é preguiçoso: a CLI consegue exibir --help e
mensagens de erro amigáveis mesmo sem as dependências pesadas instaladas.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import IDIOMA, IDIOMA_AUTO, Config, idiomas_com_alinhamento
from .perfis import Perfil


def _liberar_vram(device: str) -> None:
    gc.collect()
    if device == "cuda":
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass


@dataclass
class ResultadoTranscricao:
    segments: list[dict]      # segmentos com 'words' (start/end/score) e scores de confiança
    language: str             # idioma EFETIVO (o detectado, quando o pedido foi 'auto')
    audio: Any                # np.ndarray 16kHz — reaproveitado pela diarização
    alinhamento: bool = True  # houve forced alignment (timestamps/scores por palavra)?


# ---------------------------------------------------------------------------
# Recuperação dos scores de confiança após o alinhamento
# ---------------------------------------------------------------------------
# Os scores de segmento (avg_logprob, no_speech_prob, compression_ratio) nascem
# no faster-whisper e alimentam a fidelidade.py ([inaudível] / baixa confiança).
# O whisperx.align() propaga apenas o avg_logprob e descarta os outros dois, e
# NÃO preserva a contagem de segmentos: cada segmento bruto é quebrado em
# subsegmentos por sentença (nltk punkt) e depois reagrupado por (start, end).
# Um segmento bruto com três frases vira até três alinhados — por isso o
# pareamento tem de ser por TEMPO, nunca por índice.

def _intervalo(seg: dict) -> tuple[float, float] | None:
    """(start, end) do segmento, ou None se não houver tempo utilizável."""
    ini, fim = seg.get("start"), seg.get("end")
    if ini is None and fim is None:
        return None
    if ini is None:
        ini = fim
    if fim is None:
        fim = ini
    try:
        return float(ini), float(fim)
    except (TypeError, ValueError):
        return None


def _parear_por_tempo(alinhados: list[dict], brutos: list[dict]) -> list[int | None]:
    """Para cada segmento alinhado, o índice do segmento bruto de origem.

    Critério: maior sobreposição temporal. Sem sobreposição (segmento de duração
    zero, ou tempo interpolado que escapou do intervalo original), cai no bruto
    mais próximo do centro do alinhado. Devolve None quando não há candidato.
    """
    # (índice, início, fim) apenas dos brutos com tempo utilizável.
    candidatos = []
    for i, b in enumerate(brutos):
        iv = _intervalo(b)
        if iv is not None:
            candidatos.append((i, iv[0], iv[1]))
    if not candidatos:
        return [None] * len(alinhados)

    mapa: list[int | None] = []
    for seg in alinhados:
        iv = _intervalo(seg)
        if iv is None:
            mapa.append(None)
            continue
        s, e = iv
        centro = (s + e) / 2

        melhor_i: int | None = None
        melhor_sobrep = 0.0
        melhor_dist = float("inf")
        for i, bi, bf in candidatos:
            # Os brutos estão em ordem cronológica: uma vez achada sobreposição,
            # nenhum bruto que comece depois do fim deste alinhado vai superá-la.
            if bi >= e and melhor_sobrep > 0.0:
                break
            sobrep = min(e, bf) - max(s, bi)
            if sobrep > melhor_sobrep:
                melhor_sobrep = sobrep
                melhor_i = i
            elif melhor_sobrep <= 0.0:
                # Ainda sem sobreposição: guarda o mais próximo do centro.
                dist = 0.0 if bi <= centro <= bf else min(abs(centro - bi), abs(centro - bf))
                if dist < melhor_dist:
                    melhor_dist = dist
                    melhor_i = i
        mapa.append(melhor_i)
    return mapa


def _recuperar_scores(alinhados: list[dict], brutos: list[dict]) -> None:
    """Repõe in place os scores de confiança perdidos no alinhamento.

    Nunca sobrescreve um score já presente: o avg_logprob que o align() propaga
    é o do segmento correto e tem precedência sobre o nosso pareamento.
    """
    mapa = _parear_por_tempo(alinhados, brutos)
    for seg, i in zip(alinhados, mapa):
        if i is None:
            continue
        base = brutos[i]
        for chave in ("avg_logprob", "no_speech_prob", "compression_ratio"):
            if chave in base and seg.get(chave) is None:
                seg[chave] = base[chave]


def _asr_options(cfg: Config) -> dict:
    p = cfg.params
    return {
        "temperatures": list(p.temperatures),          # (0.0,) — sem fallback amostrado
        "condition_on_previous_text": p.condition_on_previous_text,
        "compression_ratio_threshold": p.compression_ratio_threshold,
        "log_prob_threshold": p.log_prob_threshold,
        "no_speech_threshold": p.no_speech_threshold,
        "beam_size": p.beam_size,
        "hallucination_silence_threshold": p.hallucination_silence_threshold,
        "initial_prompt": p.initial_prompt,   # viés de vocabulário (opcional)
    }


def transcrever(
    audio_wav: str | Path,
    perfil: Perfil,
    cfg: Config,
    *,
    log=print,
) -> ResultadoTranscricao:
    """Transcreve e alinha ``audio_wav`` (WAV 16 kHz mono).

    Retorna segmentos com timestamps por palavra e scores de confiança
    preservados (``avg_logprob``, ``no_speech_prob``, ``compression_ratio``).
    """
    from ._compat import proteger_speechbrain
    proteger_speechbrain()  # neutraliza lazy-modules do speechbrain antes do whisperx
    import whisperx  # import pesado, adiado

    audio = whisperx.load_audio(str(audio_wav))

    # --- Transcrição -------------------------------------------------------
    # 'auto' = não passar idioma nenhum, que é o que aciona a detecção do
    # faster-whisper. Passar o código explicitamente continua sendo o modo mais
    # fiel para material sabidamente monolíngue (ver docstring do módulo).
    idioma_pedido = None if cfg.idioma == IDIOMA_AUTO else cfg.idioma

    log(f"  · carregando modelo {perfil.modelo} ({perfil.compute_type})…")
    modelo = whisperx.load_model(
        perfil.modelo,
        perfil.device,
        compute_type=perfil.compute_type,
        language=idioma_pedido,
        asr_options=_asr_options(cfg),
    )
    log("  · transcrevendo (VAD + faster-whisper)…")
    bruto = modelo.transcribe(
        audio, batch_size=cfg.params.batch_size, language=idioma_pedido
    )
    segs_brutos = bruto.get("segments", [])

    # O idioma que de fato valeu: o pedido, ou o que o Whisper detectou.
    idioma_efetivo = bruto.get("language") or idioma_pedido or IDIOMA
    if idioma_pedido is None:
        log(f"  · idioma detectado: {idioma_efetivo}")

    # Descarrega o ASR ANTES de alinhar/diarizar (perfil 4 GB).
    del modelo
    _liberar_vram(perfil.device)

    # --- Alinhamento forçado (timestamps por palavra) ----------------------
    # Nem todo idioma tem modelo de alinhamento, e numa máquina instalada
    # (HF_HUB_OFFLINE=1) só há os que foram embutidos. Nos dois casos seguimos
    # com os segmentos brutos: timestamps por SEGMENTO, sem scores por palavra.
    segs_alinhados = segs_brutos
    alinhou = False
    if idioma_efetivo not in idiomas_com_alinhamento():
        log(f"  · sem modelo de alinhamento para '{idioma_efetivo}': seguindo com "
            "timestamps por segmento (sem scores por palavra).")
    else:
        try:
            log(f"  · alinhando (wav2vec2 {idioma_efetivo}) para timestamps por palavra…")
            modelo_a, metadata = whisperx.load_align_model(
                language_code=idioma_efetivo, device=perfil.device
            )
            alinhado = whisperx.align(
                segs_brutos, modelo_a, metadata, audio, perfil.device,
                return_char_alignments=False,
            )
            del modelo_a
            _liberar_vram(perfil.device)
            segs_alinhados = alinhado.get("segments", [])
            # O align() descarta no_speech_prob/compression_ratio e re-segmenta
            # por sentença; repomos os scores pareando por tempo
            # (ver _parear_por_tempo).
            _recuperar_scores(segs_alinhados, segs_brutos)
            alinhou = True
        except Exception as e:
            # Típico: modelo não embutido no bundle offline. Não é motivo para
            # perder a degravação inteira — mas TEM de constar no documento.
            _liberar_vram(perfil.device)
            segs_alinhados = segs_brutos
            log(f"  · alinhamento indisponível para '{idioma_efetivo}' "
                f"({type(e).__name__}): seguindo com timestamps por segmento.")

    return ResultadoTranscricao(
        segments=segs_alinhados,
        language=idioma_efetivo,
        audio=audio,
        alinhamento=alinhou,
    )
