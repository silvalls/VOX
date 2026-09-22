"""Marcações de fidelidade — o coração da confiabilidade do Degravador.

Não altera nenhuma palavra transcrita. Apenas ANOTA (flags) onde a máquina tem
baixa confiança, onde houve fala sobreposta e onde o alinhamento por palavra é
duvidoso — para direcionar a conferência humana. Tudo com base em limiares
configuráveis (config.LimiaresFidelidade).

Flags de segmento : "baixa_confianca", "inaudivel", "vozes_sobrepostas"
Flags de palavra  : "baixa_confianca", "align_fallback"
"""

from __future__ import annotations

from .config import LimiaresFidelidade


def _segmento_baixa_confianca(seg: dict, lim: LimiaresFidelidade) -> bool:
    avg = seg.get("avg_logprob")
    cr = seg.get("compression_ratio")
    if avg is not None and avg < lim.avg_logprob_min:
        return True
    if cr is not None and cr > lim.compression_ratio_max:
        return True
    return False


def _tratar_palavras(seg: dict, lim: LimiaresFidelidade) -> None:
    """Marca palavras de baixa confiança e aplica a guarda de alinhamento.

    Guarda de alinhamento: palavra sem timestamp ou com duração implausível
    volta ao timestamp do segmento e recebe 'align_fallback' (para revisão).
    """
    seg_ini = seg.get("start")
    seg_fim = seg.get("end")
    for w in seg.get("words", []):
        flags = set(w.get("flags", []))

        score = w.get("score")
        if score is not None and score < lim.word_score_min:
            flags.add("baixa_confianca")

        st, en = w.get("start"), w.get("end")
        implausivel = (
            st is None or en is None
            or (en - st) <= lim.word_dur_min_s
            or (en - st) > lim.word_dur_max_s
        )
        if implausivel:
            if st is None:
                w["start"] = seg_ini
            if en is None:
                w["end"] = seg_fim
            flags.add("align_fallback")

        w["flags"] = sorted(flags)


def _marcar_sobreposicoes(
    segments: list[dict],
    sobreposicoes: list[tuple[float, float]],
    minimo_s: float = 0.2,
) -> None:
    for seg in segments:
        s, e = seg.get("start"), seg.get("end")
        if s is None or e is None:
            continue
        for (os_, oe) in sobreposicoes:
            if min(e, oe) - max(s, os_) > minimo_s:
                flags = set(seg.get("flags", []))
                flags.add("vozes_sobrepostas")
                seg["flags"] = sorted(flags)
                break


def aplicar_marcacoes(
    segments: list[dict],
    lim: LimiaresFidelidade,
    sobreposicoes: list[tuple[float, float]] | None = None,
) -> list[dict]:
    """Anota os segmentos/palavras in place e retorna a lista."""
    for seg in segments:
        flags = set(seg.get("flags", []))
        texto = (seg.get("text") or "").strip()
        nsp = seg.get("no_speech_prob")

        # Provável trecho mudo/ruído sem fala inteligível → [inaudível].
        if nsp is not None and nsp > lim.no_speech_prob_max and not texto:
            flags.add("inaudivel")
        elif _segmento_baixa_confianca(seg, lim) or (
            nsp is not None and nsp > lim.no_speech_prob_max
        ):
            flags.add("baixa_confianca")

        seg["flags"] = sorted(flags)
        _tratar_palavras(seg, lim)

    if sobreposicoes:
        _marcar_sobreposicoes(segments, sobreposicoes)

    return segments
