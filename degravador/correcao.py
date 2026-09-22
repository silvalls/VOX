"""Correção humana pós-conferência — fiel e rastreável.

O usuário confere ouvindo o áudio e corrige no painel de correção da interface.
Isso gera um ``.correcao.json``. Aqui aplicamos essa correção sobre uma CÓPIA do
documento, produzindo a versão "corrigida — pós-conferência", **sem jamais
alterar o JSON bruto original** (que continua sendo a prova imutável, com
timestamps e scores).

Nenhuma IA participa: a correção é 100% humana.

A correção carrega duas coisas:

  1. **texto** de cada trecho, como a pessoa digitou;
  2. **estrutura de fala** — a quem pertence cada trecho. A diarização erra em
     dois sentidos opostos, e a conferência conserta os dois:
       - juntou duas pessoas numa fala só → o conferente **separa** o trecho e
         atribui cada parte a um interlocutor (criando um novo, se preciso);
       - picotou a fala de uma pessoa só → o conferente **aglutina** os trechos;
       - deu dois rótulos à mesma pessoa → **mescla** os rótulos no documento todo.

Por isso um trecho corrigido não é mais necessariamente um segmento original:
cada segmento resultante guarda ``origem_seg`` — a lista de índices dos segmentos
brutos de onde veio. É esse campo que permite ao relatório de conferência
confrontar cada palavra corrigida com o que a máquina havia transcrito.

Formatos aceitos:
  - ``degravador-correcao/1.0`` — um item por segmento, só texto (compatível);
  - ``degravador-correcao/1.1`` — itens com ``origem``/``parte``/``end`` e
    ``novos_locutores``, permitindo separar e aglutinar.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path


ESQUEMA_CORRECAO = "degravador-correcao/1.1"
ESQUEMAS_ACEITOS = ("degravador-correcao/1.0", "degravador-correcao/1.1")


def carregar(caminho: str | Path) -> dict:
    """Lê o .correcao.json produzido pela interface."""
    caminho = Path(caminho)
    with open(caminho, "r", encoding="utf-8") as f:
        corr = json.load(f)
    if "segmentos" not in corr:
        raise ValueError(
            f"{caminho} não é um arquivo de correção válido (falta 'segmentos')."
        )
    return corr


def _resolvedor(merges: dict):
    """Segue a cadeia de mesclagens (A→B, B→C ⇒ A→C), à prova de ciclo."""
    def resolver(spk):
        visto = set()
        while spk in merges and spk not in visto:
            visto.add(spk)
            spk = merges[spk]
        return spk
    return resolver


def _origem(item: dict) -> list[int]:
    """Índices dos segmentos brutos que este trecho corrigido cobre."""
    origem = item.get("origem")
    if isinstance(origem, list) and origem:
        return [int(i) for i in origem]
    seg = item.get("seg")
    return [int(seg)] if seg is not None else []


def aplicar(doc: dict, correcao: dict, *, revisado_por: str | None = None) -> dict:
    """Retorna uma CÓPIA do documento com o texto e a atribuição de fala corrigidos.

    - Reconstrói a lista de segmentos a partir dos trechos da conferência, que
      podem ter sido **separados** (um segmento vira vários) ou **aglutinados**
      (vários viram um). Cada resultante leva ``origem_seg``.
    - Aplica as **mesclagens** de locutor em todo o documento.
    - Zera ``words`` dos trechos corrigidos (o texto humano prevalece; sem realce
      de baixa confiança na versão corrigida) e remove as flags de incerteza,
      preservando ``vozes_sobrepostas`` (marca de contexto, não de erro).
    - Segmentos que a correção não menciona são **mantidos intactos** — uma
      correção parcial (feita à mão, pela CLI) nunca apaga fala.
    - Marca nos metadados que houve conferência humana.

    O documento original recebido NÃO é modificado.
    """
    novo = copy.deepcopy(doc)
    originais = novo.get("segments", [])
    resolver = _resolvedor(correcao.get("merges") or {})

    itens = [i for i in (correcao.get("segmentos") or []) if _origem(i) or i.get("texto")]
    cobertos: set[int] = set()
    reconstruidos: list[dict] = []

    for item in itens:
        origem = [i for i in _origem(item) if 0 <= i < len(originais)]
        cobertos.update(origem)
        # O primeiro segmento de origem serve de base: preserva avg_logprob,
        # no_speech_prob e demais medições do bruto, que seguem sendo a prova
        # de como aquele trecho foi reconhecido.
        base = copy.deepcopy(originais[origem[0]]) if origem else {}

        flags = set()
        for i in origem:
            flags.update(originais[i].get("flags", []))

        inicio = item.get("start")
        if inicio is None:
            inicio = base.get("start", 0.0)
        fim = item.get("end")
        if fim is None:
            fim = originais[origem[-1]].get("end") if origem else inicio

        speaker = item.get("speaker")
        if speaker is None and "speaker" not in item:
            speaker = base.get("speaker")

        base.update({
            "start": float(inicio or 0.0),
            "end": float(fim if fim is not None else (inicio or 0.0)),
            "text": (item.get("texto") or "").strip(),
            "speaker": resolver(speaker) if speaker else speaker,
            "words": [],  # texto humano é a verdade da versão corrigida
            "flags": [f for f in flags if f == "vozes_sobrepostas"],
            "origem_seg": origem,
        })
        if item.get("tempo_estimado"):
            # Corte feito por texto, não por palavra alinhada: o relatório diz.
            base["tempo_estimado"] = True
        reconstruidos.append(base)

    # Segmentos fora da correção seguem como estão (com o locutor resolvido).
    for i, seg in enumerate(originais):
        if i in cobertos:
            continue
        mantido = copy.deepcopy(seg)
        if mantido.get("speaker"):
            mantido["speaker"] = resolver(mantido["speaker"])
        mantido["origem_seg"] = [i]
        reconstruidos.append(mantido)

    if reconstruidos:
        # Ordenação estável: a lista já vem na ordem da conferência; ordenar por
        # tempo só recoloca os segmentos não corrigidos no lugar certo.
        reconstruidos.sort(key=lambda s: float(s.get("start") or 0.0))
        novo["segments"] = reconstruidos

    distintos = {s.get("speaker") for s in novo.get("segments", [])}
    distintos.discard(None)

    meta = novo.setdefault("metadata", {})
    meta["num_speakers"] = len(distintos) or None
    meta["revisado"] = True
    meta["revisado_em"] = datetime.now().isoformat(timespec="seconds")
    if revisado_por:
        meta["revisado_por"] = revisado_por
    novos = correcao.get("novos_locutores") or {}
    if novos:
        # Vozes que a máquina não separou e a pessoa criou na conferência: o
        # documento precisa dizer quais interlocutores são atribuição humana.
        meta["locutores_criados_na_conferencia"] = dict(novos)
    return novo
