"""Testes leves: fidelidade + exportadores, sem modelos pesados (torch/whisperx).

Rodam em qualquer máquina com `pytest`, protegendo contra regressões nas
marcações de fidelidade e na geração de cada formato de saída.
"""

from __future__ import annotations

import json as _json

import pytest

from degravador.config import CONFIG_PADRAO
from degravador.fidelidade import aplicar_marcacoes
from degravador.saidas import json as sj
from degravador.saidas import txt, srt, vtt, html


def _w(word, s, e, score, spk="SPEAKER_00"):
    return {"word": word, "start": s, "end": e, "score": score, "speaker": spk, "flags": []}


def _segments():
    return [
        {"start": 0.0, "end": 1.6, "text": "Bom dia a todos.", "speaker": "SPEAKER_00",
         "avg_logprob": -0.2, "no_speech_prob": 0.01, "compression_ratio": 1.2, "flags": [],
         "words": [_w("Bom", 0.0, 0.4, 0.95), _w("dia", 0.4, 0.8, 0.9),
                   _w("a", 0.8, 0.9, 0.30),  # score baixo
                   _w("todos.", 0.9, 1.6, 0.88)]},
        {"start": 1.8, "end": 4.0, "text": "Podemos começar.", "speaker": "SPEAKER_01",
         "avg_logprob": -1.4, "no_speech_prob": 0.05, "compression_ratio": 1.1, "flags": [],
         "words": [_w("Podemos", 1.8, 2.4, 0.8, "SPEAKER_01"),
                   _w("começar.", 2.4, 4.0, 0.6, "SPEAKER_01")]},
        {"start": 4.2, "end": 5.0, "text": "", "speaker": "SPEAKER_00",
         "avg_logprob": -0.9, "no_speech_prob": 0.85, "compression_ratio": 1.0, "flags": [],
         "words": []},
        {"start": 5.0, "end": 7.0, "text": "Fala sobreposta.", "speaker": "SPEAKER_01",
         "avg_logprob": -0.3, "no_speech_prob": 0.02, "compression_ratio": 1.3, "flags": [],
         "words": [_w("Fala", 5.0, 5.4, 0.9, "SPEAKER_01"),
                   _w("sobreposta.", 5.4, 6.2, 0.85, "SPEAKER_01")]},
    ]


def _doc():
    segs = _segments()
    aplicar_marcacoes(segs, CONFIG_PADRAO.limiares, sobreposicoes=[(5.5, 6.0)])
    meta = {"arquivo": "exemplo.mp4", "sha256": "a" * 64, "duracao_s": 7.0,
            "criado_em": "2026-07-03T10:00:00", "modelo": "large-v3-turbo",
            "versao_app": "0.1.0", "perfil": "recomendado", "num_speakers": 2,
            "audio_arquivo": "exemplo.deg.wav", "revisado_por": None,
            "params": CONFIG_PADRAO.para_metadata()}
    return sj.construir_documento(meta, segs)


def test_marcacoes_fidelidade():
    doc = _doc()
    s = doc["segments"]
    # palavra "a" (score 0.30 < 0.40) -> baixa_confianca
    assert "baixa_confianca" in s[0]["words"][2]["flags"]
    # segmento com avg_logprob -1.4 -> baixa_confianca
    assert "baixa_confianca" in s[1]["flags"]
    # segmento mudo (no_speech 0.85, sem texto) -> inaudivel
    assert "inaudivel" in s[2]["flags"]
    # segmento em janela de sobreposição -> vozes_sobrepostas
    assert "vozes_sobrepostas" in s[3]["flags"]


def test_json_roundtrip(tmp_path):
    doc = _doc()
    p = tmp_path / "x.json"
    sj.salvar_em(doc, p)
    lido = sj.carregar(p)
    assert lido["schema_version"] == sj.ESQUEMA_VERSAO
    assert len(lido["segments"]) == 4
    assert lido["metadata"]["sha256"] == "a" * 64


def test_txt(tmp_path):
    doc = _doc()
    p = tmp_path / "x.txt"
    txt.exportar(doc, p, mapa_locutores={"SPEAKER_00": "Juiz", "SPEAKER_01": "Testemunha"})
    conteudo = p.read_text(encoding="utf-8")
    assert "Juiz (00:00:00):" in conteudo
    assert "[inaudível – 00:00:04]" in conteudo
    assert "[vozes sobrepostas]" in conteudo


def test_srt_vtt(tmp_path):
    doc = _doc()
    ps, pv = tmp_path / "x.srt", tmp_path / "x.vtt"
    srt.exportar(doc, ps)
    vtt.exportar(doc, pv)
    assert "-->" in ps.read_text(encoding="utf-8")
    assert vtt.exportar and pv.read_text(encoding="utf-8").startswith("WEBVTT")


def test_html_interativo(tmp_path):
    doc = _doc()
    p = tmp_path / "x.html"
    html.exportar(doc, p, audio_src="exemplo.deg.wav")
    c = p.read_text(encoding="utf-8")
    assert 'id="audio"' in c
    assert "data-seek=" in c
    assert 'class="w baixa"' in c  # palavra de baixa confiança realçada


def test_saida_preserva_pontos_no_nome():
    # Regressão: nomes com pontos (ex.: "audio 16.32.53") não podem perder
    # segmentos ao anexar a extensão de saída.
    from pathlib import Path
    from degravador.cli import _saida
    base = Path("out") / "WhatsApp Ptt 2026-07-03 at 16.32.53"
    assert _saida(base, ".json").name == "WhatsApp Ptt 2026-07-03 at 16.32.53.json"
    assert _saida(base, ".deg.wav").name == "WhatsApp Ptt 2026-07-03 at 16.32.53.deg.wav"


def test_glossario_deterministico(tmp_path):
    from degravador import glossario
    csv = tmp_path / "termos.csv"
    csv.write_text("de,para\nSylva,Silva\n", encoding="utf-8")
    mapa = glossario.carregar(csv)
    assert mapa == {"Sylva": "Silva"}
    doc = {"segments": [{"text": "João Sylva falou.",
                         "words": [{"word": "Sylva"}], "flags": []}]}
    novo = glossario.aplicar(doc, mapa)
    assert "Silva" in novo["segments"][0]["text"]
    assert novo["segments"][0]["words"][0]["word"] == "Silva"
    # não mutou o original (JSON bruto preservado)
    assert doc["segments"][0]["text"] == "João Sylva falou."


def test_correcao_preserva_original(tmp_path):
    from degravador import correcao
    doc = _doc()
    original_texto = doc["segments"][0]["text"]
    corr = {"schema": "degravador-correcao/1.0", "segmentos": [
        {"seg": 0, "speaker": "SPEAKER_00", "start": 0.0, "texto": "Texto corrigido pelo humano."},
    ]}
    novo = correcao.aplicar(doc, corr, revisado_por="Fulano")
    # corrigido reflete a edição; sem words (texto humano prevalece)
    assert novo["segments"][0]["text"] == "Texto corrigido pelo humano."
    assert novo["segments"][0]["words"] == []
    assert novo["metadata"]["revisado"] is True
    assert novo["metadata"]["revisado_por"] == "Fulano"
    # original NÃO foi mutado
    assert doc["segments"][0]["text"] == original_texto
    assert doc["segments"][0]["words"]  # continua com palavras


def test_correcao_merge_locutores():
    from degravador import correcao
    doc = _doc()  # SPEAKER_00 e SPEAKER_01
    novo = correcao.aplicar(doc, {"segmentos": [], "merges": {"SPEAKER_01": "SPEAKER_00"}})
    speakers = {s.get("speaker") for s in novo["segments"]}
    assert "SPEAKER_01" not in speakers
    assert speakers == {"SPEAKER_00"}
    assert novo["metadata"]["num_speakers"] == 1
    # original intacto
    assert {s.get("speaker") for s in doc["segments"]} == {"SPEAKER_00", "SPEAKER_01"}


def test_scores_pareiam_por_tempo_nao_por_indice():
    # Regressão: o whisperx.align() quebra cada segmento em subsegmentos por
    # sentença, então len(alinhados) != len(brutos). Parear por índice jogava os
    # scores de confiança no segmento errado — e a fidelidade.py marcava
    # [inaudível]/baixa_confiança no lugar errado.
    from degravador.transcricao import _parear_por_tempo, _recuperar_scores

    brutos = [
        # um segmento, três frases -> vira três alinhados
        {"start": 0.0, "end": 6.0, "text": "Bom dia. Podemos começar. Sim.",
         "avg_logprob": -0.2, "no_speech_prob": 0.01, "compression_ratio": 1.2},
        # o segmento mudo que DEVE receber no_speech_prob alto
        {"start": 6.2, "end": 7.0, "text": "",
         "avg_logprob": -0.9, "no_speech_prob": 0.85, "compression_ratio": 1.0},
    ]
    alinhados = [
        {"start": 0.0, "end": 1.6, "text": "Bom dia.", "avg_logprob": -0.2},
        {"start": 1.6, "end": 4.0, "text": "Podemos começar.", "avg_logprob": -0.2},
        {"start": 4.0, "end": 6.0, "text": "Sim.", "avg_logprob": -0.2},
        {"start": 6.2, "end": 7.0, "text": "", "avg_logprob": -0.9},
    ]

    assert _parear_por_tempo(alinhados, brutos) == [0, 0, 0, 1]

    _recuperar_scores(alinhados, brutos)
    # as três frases herdam os scores do MESMO segmento bruto de origem
    for seg in alinhados[:3]:
        assert seg["no_speech_prob"] == 0.01
        assert seg["compression_ratio"] == 1.2
    # o segmento mudo mantém o seu (por índice, teria ficado sem score nenhum)
    assert alinhados[3]["no_speech_prob"] == 0.85

    # e a fidelidade agora marca o segmento certo como inaudível
    aplicar_marcacoes(alinhados, CONFIG_PADRAO.limiares)
    assert "inaudivel" in alinhados[3]["flags"]
    assert "inaudivel" not in alinhados[0]["flags"]


def test_recuperar_scores_nao_sobrescreve_avg_logprob():
    # O align() já propaga o avg_logprob do segmento correto; o pareamento não
    # pode substituí-lo por um valor de outro segmento.
    from degravador.transcricao import _recuperar_scores

    brutos = [{"start": 0.0, "end": 5.0, "avg_logprob": -1.4, "no_speech_prob": 0.02}]
    alinhados = [{"start": 0.0, "end": 2.0, "avg_logprob": -0.3}]
    _recuperar_scores(alinhados, brutos)
    assert alinhados[0]["avg_logprob"] == -0.3   # preservado
    assert alinhados[0]["no_speech_prob"] == 0.02  # preenchido


def test_parear_tolera_segmentos_sem_tempo():
    from degravador.transcricao import _parear_por_tempo

    brutos = [{"start": 0.0, "end": 2.0}, {"start": 2.0, "end": 4.0}]
    # segmento sem tempo -> None; duração zero -> cai no bruto que o contém
    alinhados = [{"text": "sem tempo"}, {"start": 3.0, "end": 3.0}]
    assert _parear_por_tempo(alinhados, brutos) == [None, 1]
    # sem brutos utilizáveis, ninguém pareia (e nada quebra)
    assert _parear_por_tempo(alinhados, []) == [None, None]


def test_docx(tmp_path):
    pytest.importorskip("docx")
    from degravador.saidas import docx as sd
    doc = _doc()
    p = tmp_path / "x.docx"
    sd.exportar(doc, p, mapa_locutores={"SPEAKER_00": "Juiz", "SPEAKER_01": "Testemunha"})
    from docx import Document
    d = Document(str(p))
    assert d.styles["Normal"].font.name == "Arial"
    assert d.styles["Normal"].font.size.pt == 12
    assert round(d.sections[0].top_margin.cm, 1) == 3.0
