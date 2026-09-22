"""Etapa 4 — Diarização de locutores (dois backends) e fusão palavra↔locutor.

Roda DEPOIS da transcrição, com a VRAM já liberada (perfil 4 GB).

Backends:
  • "pyannote"    — pyannote.audio 3.1. Melhor qualidade, trata sobreposição de
                    vozes. Exige aceitar termos no Hugging Face + token (uma vez).
  • "speechbrain" — SEM token. Embeddings ECAPA (Apache-2.0) por segmento +
                    agrupamento. Não trata sobreposição; bom para áudio limpo.
                    É o plano B / caminho offline sem cadastro.

``diarizar`` despacha para o backend escolhido e devolve os segmentos com
``speaker`` por palavra/segmento.
"""

from __future__ import annotations

from dataclasses import dataclass

from .perfis import Perfil


# Distância de cosseno (0..2) para separar locutores no backend sem-token.
# Ajustável: menor = mais locutores; maior = menos.
SPEECHBRAIN_LIMIAR = 0.72
SPEECHBRAIN_DUR_MIN_S = 0.5   # segmentos menores herdam o locutor do vizinho
SPEECHBRAIN_MAX_AUTO = 8      # teto de sanidade quando o nº de locutores é automático

# Modelo pyannote usado por padrão pelo stack atual (whisperx 3.8 + pyannote 4).
# É o mais novo/robusto. Requer aceitar os termos deste repositório no HF.
PYANNOTE_MODELO = "pyannote/speaker-diarization-community-1"


class TokenHFAusente(RuntimeError):
    pass


@dataclass
class ResultadoDiarizacao:
    segments: list[dict]
    num_speakers: int
    sobreposicoes: list[tuple[float, float]]
    backend: str


# ---------------------------------------------------------------------------
# Utilidades comuns
# ---------------------------------------------------------------------------
def _rotular_em_ordem(labels) -> list[str]:
    """Converte rótulos de cluster em SPEAKER_00, SPEAKER_01… na ordem de aparição."""
    mapa: dict = {}
    saida = []
    for l in labels:
        if l not in mapa:
            mapa[l] = f"SPEAKER_{len(mapa):02d}"
        saida.append(mapa[l])
    return saida


def _atribuir_por_segmento(segments: list[dict], speakers: list[str]) -> None:
    """Grava o locutor no segmento e em cada palavra dele."""
    for seg, spk in zip(segments, speakers):
        seg["speaker"] = spk
        for w in seg.get("words", []):
            w["speaker"] = spk


# ---------------------------------------------------------------------------
# Backend SEM token: SpeechBrain ECAPA + agrupamento
# ---------------------------------------------------------------------------
def diarizar_speechbrain(
    audio,
    segments: list[dict],
    perfil: Perfil,
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    log=print,
) -> ResultadoDiarizacao:
    import numpy as np
    import torch
    from sklearn.cluster import AgglomerativeClustering

    try:
        from speechbrain.inference import EncoderClassifier
    except Exception:  # layout alternativo
        from speechbrain.inference.classifiers import EncoderClassifier

    log("  · diarizando (SpeechBrain ECAPA, sem token)…")
    device = perfil.diarizacao_device
    from ._offline import savedir_speechbrain
    _sd = savedir_speechbrain()
    _kw = {"savedir": _sd} if _sd else {}
    classificador = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        run_opts={"device": device}, **_kw,
    )

    sr = 16000
    vetores: list = []
    idx_com_emb: list[int] = []
    for i, seg in enumerate(segments):
        ini, fim = seg.get("start"), seg.get("end")
        if ini is None or fim is None or (fim - ini) < SPEECHBRAIN_DUR_MIN_S:
            continue
        a = int(ini * sr)
        b = min(len(audio), int(fim * sr))
        if b - a < int(SPEECHBRAIN_DUR_MIN_S * sr):
            continue
        trecho = torch.tensor(np.asarray(audio[a:b], dtype="float32")).unsqueeze(0).to(device)
        with torch.no_grad():
            emb = classificador.encode_batch(trecho).squeeze().detach().cpu().numpy()
        n = np.linalg.norm(emb)
        vetores.append(emb / n if n > 0 else emb)
        idx_com_emb.append(i)

    if len(vetores) == 0:
        log("  · nenhum segmento longo o suficiente para diarizar; pulando.")
        return ResultadoDiarizacao(segments, 0, [], "speechbrain")

    X = np.vstack(vetores)

    # Quantidade de locutores
    if num_speakers and num_speakers >= 1:
        n = min(num_speakers, len(X))
        modelo = AgglomerativeClustering(n_clusters=n, metric="cosine", linkage="average")
    else:
        modelo = AgglomerativeClustering(
            n_clusters=None, distance_threshold=SPEECHBRAIN_LIMIAR,
            metric="cosine", linkage="average",
        )
    labels_emb = list(modelo.fit_predict(X)) if len(X) > 1 else [0]

    # Aplica limites min/max, se dados, re-agrupando com nº fixo
    n_detectado = len(set(labels_emb))
    alvo = None
    if min_speakers and n_detectado < min_speakers:
        alvo = min(min_speakers, len(X))
    if max_speakers and n_detectado > max_speakers:
        alvo = max_speakers
    if alvo:
        labels_emb = list(
            AgglomerativeClustering(n_clusters=alvo, metric="cosine", linkage="average")
            .fit_predict(X)
        )

    # Propaga rótulos para TODOS os segmentos (curtos herdam do vizinho anterior)
    por_idx = {idx: lab for idx, lab in zip(idx_com_emb, labels_emb)}
    labels_todos: list = []
    ultimo = labels_emb[0]
    for i in range(len(segments)):
        if i in por_idx:
            ultimo = por_idx[i]
        labels_todos.append(ultimo)

    speakers = _rotular_em_ordem(labels_todos)
    _atribuir_por_segmento(segments, speakers)
    distintos = len(set(speakers))
    log(f"  · {distintos} locutor(es) estimado(s) (sem token).")
    return ResultadoDiarizacao(segments, distintos, [], "speechbrain")


# ---------------------------------------------------------------------------
# Backend COM token: pyannote.audio (speaker-diarization-community-1)
# ---------------------------------------------------------------------------
def _pipeline_pyannote(hf_token: str, device: str):
    import whisperx
    try:
        from whisperx.diarize import DiarizationPipeline
    except Exception:
        DiarizationPipeline = whisperx.DiarizationPipeline
    try:
        import torch
        dev = torch.device(device)
    except Exception:
        dev = device
    # Passa PYANNOTE_MODELO explicitamente em vez de aceitar o padrão do
    # whisperx: o modelo fica fixado no código (auditabilidade) e é o repositório
    # cujos termos o usuário precisa ter aceitado no HF.
    # A API mudou entre versões: 'token' (novas) vs 'use_auth_token' — e o ramo
    # antigo não aceita model_name, caindo no padrão da versão instalada.
    try:
        return DiarizationPipeline(
            model_name=PYANNOTE_MODELO, token=hf_token, device=dev
        )
    except TypeError:
        return DiarizationPipeline(use_auth_token=hf_token, device=dev)


def _calcular_sobreposicoes(df) -> list[tuple[float, float]]:
    try:
        linhas = [(float(r["start"]), float(r["end"]), r.get("speaker")) for _, r in df.iterrows()]
    except Exception:
        return []
    linhas.sort()
    sobrepostos: list[tuple[float, float]] = []
    for i in range(len(linhas)):
        s1, e1, spk1 = linhas[i]
        for j in range(i + 1, len(linhas)):
            s2, e2, spk2 = linhas[j]
            if s2 >= e1:
                break
            if spk2 != spk1:
                ini, fim = max(s1, s2), min(e1, e2)
                if fim > ini:
                    sobrepostos.append((ini, fim))
    return sobrepostos


def diarizar_pyannote(
    audio,
    segments: list[dict],
    perfil: Perfil,
    hf_token: str | None,
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    log=print,
) -> ResultadoDiarizacao:
    import os
    # No modo offline (instalador) os modelos já estão embutidos: o pyannote
    # carrega do cache local, sem token. Só exigimos token fora do modo offline.
    offline = bool(os.environ.get("VOX_OFFLINE"))
    if not hf_token and not offline:
        raise TokenHFAusente(
            "Diarização pyannote requer HF_TOKEN. Use o backend sem token "
            "(--diarizador speechbrain) ou configure o token."
        )
    import whisperx

    log(f"  · diarizando (pyannote: {PYANNOTE_MODELO.split('/')[-1]})…")
    pipe = _pipeline_pyannote(hf_token, perfil.diarizacao_device)
    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = num_speakers
    if min_speakers:
        kwargs["min_speakers"] = min_speakers
    if max_speakers:
        kwargs["max_speakers"] = max_speakers

    df = pipe(audio, **kwargs)
    resultado = whisperx.assign_word_speakers(df, {"segments": segments})
    segs = resultado["segments"]
    distintos = {s.get("speaker") for s in segs}
    distintos.discard(None)
    return ResultadoDiarizacao(segs, len(distintos), _calcular_sobreposicoes(df), "pyannote")


# ---------------------------------------------------------------------------
# Despacho
# ---------------------------------------------------------------------------
def escolher_backend(preferido: str, hf_token: str | None) -> str:
    """Resolve 'auto' → pyannote (melhor). Só cai no speechbrain quando NÃO há
    token E não é o modo offline. No modo offline (instalador) o pyannote carrega
    do cache local sem token, então é sempre o preferido."""
    if preferido == "auto":
        import os
        if os.environ.get("VOX_OFFLINE") or hf_token:
            return "pyannote"
        return "speechbrain"
    return preferido


def diarizar(
    audio,
    segments: list[dict],
    perfil: Perfil,
    *,
    backend: str = "auto",
    hf_token: str | None = None,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    log=print,
) -> ResultadoDiarizacao:
    from ._compat import proteger_speechbrain
    proteger_speechbrain()
    escolhido = escolher_backend(backend, hf_token)
    if escolhido == "pyannote":
        return diarizar_pyannote(
            audio, segments, perfil, hf_token,
            num_speakers=num_speakers, min_speakers=min_speakers,
            max_speakers=max_speakers, log=log,
        )
    return diarizar_speechbrain(
        audio, segments, perfil,
        num_speakers=num_speakers, min_speakers=min_speakers,
        max_speakers=max_speakers, log=log,
    )
