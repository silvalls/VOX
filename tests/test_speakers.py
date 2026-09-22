"""Edição de interlocutores na conferência — separar, aglutinar, reatribuir, criar.

A diarização erra nos dois sentidos: junta duas pessoas numa fala só e picota a
fala de uma pessoa só. A conferência conserta ambos, e o documento corrigido tem
de continuar amarrado ao bruto (``origem_seg``) para o relatório poder auditar a
intervenção humana. Estes testes prendem esse contrato.
"""

from __future__ import annotations

from degravador import correcao, relatorio
from degravador.saidas import html


def _w(word, s, e, spk):
    return {"word": word, "start": s, "end": e, "score": 0.9, "speaker": spk, "flags": []}


def _doc():
    """Quatro segmentos; o primeiro tem DUAS pessoas coladas no mesmo rótulo."""
    segs = [
        {"start": 0.0, "end": 4.0, "text": "Bom dia doutor. Bom dia excelência.",
         "speaker": "SPEAKER_00", "flags": [], "avg_logprob": -0.2,
         "words": [_w("Bom", 0.0, 0.4, "SPEAKER_00"), _w("dia", 0.4, 0.8, "SPEAKER_00"),
                   _w("doutor.", 0.8, 1.9, "SPEAKER_00"), _w("Bom", 2.1, 2.5, "SPEAKER_00"),
                   _w("dia", 2.5, 2.9, "SPEAKER_00"), _w("excelência.", 2.9, 4.0, "SPEAKER_00")]},
        {"start": 4.2, "end": 6.0, "text": "Podemos começar", "speaker": "SPEAKER_01",
         "flags": [], "avg_logprob": -0.3, "words": [_w("Podemos", 4.2, 5.0, "SPEAKER_01")]},
        {"start": 6.0, "end": 8.0, "text": "a audiência.", "speaker": "SPEAKER_02",
         "flags": [], "avg_logprob": -0.4, "words": [_w("a", 6.0, 6.2, "SPEAKER_02")]},
        {"start": 8.5, "end": 9.9, "text": "De acordo.", "speaker": "SPEAKER_01",
         "flags": ["vozes_sobrepostas"], "avg_logprob": -0.5, "words": []},
    ]
    return {"metadata": {"arquivo": "audiencia.mp4", "num_speakers": 3,
                         "criado_em": "2026-09-22T10:00:00", "sha256": "a" * 64},
            "segments": segs}


# ---------------------------------------------------------------------------
# SEPARAR — um segmento vira dois, cada um com o seu interlocutor
# ---------------------------------------------------------------------------
def test_separar_divide_segmento_em_dois_interlocutores():
    doc = _doc()
    corr = {"schema": "degravador-correcao/1.1", "segmentos": [
        {"seg": 0, "origem": [0], "parte": 0, "speaker": "SPEAKER_00",
         "start": 0.0, "end": 2.1, "texto": "Bom dia, doutor."},
        {"seg": 0, "origem": [0], "parte": 1, "speaker": "INTERLOCUTOR_1",
         "start": 2.1, "end": 4.0, "texto": "Bom dia, excelência."},
    ], "novos_locutores": {"INTERLOCUTOR_1": "Juiz"}}
    novo = correcao.aplicar(doc, corr)
    segs = novo["segments"]

    assert len(segs) == len(doc["segments"]) + 1     # um segmento virou dois
    assert [s["text"] for s in segs[:2]] == ["Bom dia, doutor.", "Bom dia, excelência."]
    assert [s["speaker"] for s in segs[:2]] == ["SPEAKER_00", "INTERLOCUTOR_1"]
    # As duas partes continuam apontando para o segmento bruto de onde vieram.
    assert segs[0]["origem_seg"] == [0] and segs[1]["origem_seg"] == [0]
    assert segs[0]["end"] == 2.1 and segs[1]["start"] == 2.1
    # O interlocutor criado na conferência fica registrado — é atribuição humana.
    assert novo["metadata"]["locutores_criados_na_conferencia"] == {"INTERLOCUTOR_1": "Juiz"}
    # O bruto não foi tocado.
    assert len(doc["segments"]) == 4
    assert doc["segments"][0]["text"] == "Bom dia doutor. Bom dia excelência."


# ---------------------------------------------------------------------------
# AGLUTINAR — vários segmentos viram um só
# ---------------------------------------------------------------------------
def test_aglutinar_junta_segmentos_de_origens_diferentes():
    doc = _doc()
    corr = {"schema": "degravador-correcao/1.1", "segmentos": [
        {"seg": 0, "origem": [0], "parte": 0, "speaker": "SPEAKER_00",
         "start": 0.0, "end": 4.0, "texto": "Bom dia doutor. Bom dia excelência."},
        {"seg": 1, "origem": [1, 2], "parte": 0, "speaker": "SPEAKER_01",
         "start": 4.2, "end": 8.0, "texto": "Podemos começar a audiência."},
        {"seg": 3, "origem": [3], "parte": 0, "speaker": "SPEAKER_01",
         "start": 8.5, "end": 9.9, "texto": "De acordo."},
    ]}
    novo = correcao.aplicar(doc, corr)
    segs = novo["segments"]

    assert len(segs) == 3
    juntado = segs[1]
    assert juntado["text"] == "Podemos começar a audiência."
    assert juntado["origem_seg"] == [1, 2]
    assert juntado["start"] == 4.2 and juntado["end"] == 8.0
    assert juntado["speaker"] == "SPEAKER_01"
    # SPEAKER_02 era só a fala picotada: some da contagem de interlocutores.
    assert novo["metadata"]["num_speakers"] == 2


def test_aglutinar_preserva_flag_de_contexto_das_origens():
    # 'vozes sobrepostas' é marca de contexto do áudio, não de erro de texto:
    # aglutinar não pode fazê-la desaparecer.
    doc = _doc()
    corr = {"segmentos": [
        {"origem": [2, 3], "speaker": "SPEAKER_01", "start": 6.0, "end": 9.9,
         "texto": "a audiência. De acordo."},
    ]}
    novo = correcao.aplicar(doc, corr)
    alvo = [s for s in novo["segments"] if s.get("origem_seg") == [2, 3]][0]
    assert alvo["flags"] == ["vozes_sobrepostas"]


# ---------------------------------------------------------------------------
# REATRIBUIR e MESCLAR
# ---------------------------------------------------------------------------
def test_reatribuir_trecho_a_outro_interlocutor():
    doc = _doc()
    corr = {"segmentos": [
        {"seg": 2, "origem": [2], "speaker": "SPEAKER_01", "start": 6.0, "end": 8.0,
         "texto": "a audiência."},
    ]}
    novo = correcao.aplicar(doc, corr)
    alvo = [s for s in novo["segments"] if s["origem_seg"] == [2]][0]
    assert alvo["speaker"] == "SPEAKER_01"
    assert doc["segments"][2]["speaker"] == "SPEAKER_02"   # bruto intacto


def test_mesclagem_alcanca_ate_os_trechos_reatribuidos():
    # A pessoa reatribuiu um trecho a SPEAKER_02 e, depois, mesclou SPEAKER_02
    # em SPEAKER_01. O resultado tem de seguir a cadeia até o fim.
    doc = _doc()
    corr = {"segmentos": [
        {"seg": 0, "origem": [0], "speaker": "SPEAKER_02", "start": 0.0, "end": 4.0,
         "texto": "Bom dia."},
    ], "merges": {"SPEAKER_02": "SPEAKER_01"}}
    novo = correcao.aplicar(doc, corr)
    assert novo["segments"][0]["speaker"] == "SPEAKER_01"
    assert "SPEAKER_02" not in {s["speaker"] for s in novo["segments"]}


def test_correcao_parcial_nao_apaga_fala():
    # Correção feita à mão, cobrindo um segmento só: os demais seguem intactos.
    doc = _doc()
    novo = correcao.aplicar(doc, {"segmentos": [
        {"seg": 1, "texto": "Podemos começar."},
    ]})
    assert len(novo["segments"]) == 4
    assert novo["segments"][1]["text"] == "Podemos começar."
    assert novo["segments"][3]["text"] == "De acordo."
    # Sem 'speaker' no item, o locutor original é mantido.
    assert novo["segments"][1]["speaker"] == "SPEAKER_01"


# ---------------------------------------------------------------------------
# RELATÓRIO — a intervenção na atribuição de fala tem de estar escrita
# ---------------------------------------------------------------------------
def test_relatorio_registra_separacao_aglutinacao_e_reatribuicao():
    doc = _doc()
    corr = {"segmentos": [
        # separação do segmento 0 em duas vozes
        {"origem": [0], "parte": 0, "speaker": "SPEAKER_00", "start": 0.0, "end": 2.1,
         "texto": "Bom dia doutor."},
        {"origem": [0], "parte": 1, "speaker": "INTERLOCUTOR_1", "start": 2.1, "end": 4.0,
         "texto": "Bom dia excelência.", "tempo_estimado": True},
        # aglutinação dos segmentos 1 e 2
        {"origem": [1, 2], "parte": 0, "speaker": "SPEAKER_01", "start": 4.2, "end": 8.0,
         "texto": "Podemos começar a audiência."},
        # reatribuição do segmento 3
        {"origem": [3], "parte": 0, "speaker": "INTERLOCUTOR_1", "start": 8.5, "end": 9.9,
         "texto": "De acordo."},
    ], "novos_locutores": {"INTERLOCUTOR_1": "Juiz"}}
    doc_corr = correcao.aplicar(doc, corr)
    comp = relatorio.comparar(doc, doc_corr, correcao=corr)

    tipos = [a["tipo"] for a in comp["ajustes"]]
    assert "separado" in tipos and "aglutinado" in tipos and "reatribuido" in tipos
    sep = [a for a in comp["ajustes"] if a["tipo"] == "separado"][0]
    assert len(sep["partes"]) == 2
    assert any(p["estimado"] for p in sep["partes"])   # corte sem palavra alinhada
    assert comp["locutores_criados"] == {"INTERLOCUTOR_1": "Juiz"}
    assert comp["locutores_original"] == 3 and comp["locutores_corrigido"] == 3


def _corr_dividindo_o_primeiro(texto_parte2="Bom dia excelência."):
    return {"segmentos": [
        {"origem": [0], "parte": 0, "speaker": "SPEAKER_00", "start": 0.0, "end": 2.1,
         "texto": "Bom dia doutor."},
        {"origem": [0], "parte": 1, "speaker": "SPEAKER_01", "start": 2.1, "end": 4.0,
         "texto": texto_parte2},
        {"origem": [1], "parte": 0, "speaker": "SPEAKER_01", "start": 4.2, "end": 6.0,
         "texto": "Podemos começar"},
        {"origem": [2], "parte": 0, "speaker": "SPEAKER_02", "start": 6.0, "end": 8.0,
         "texto": "a audiência."},
        {"origem": [3], "parte": 0, "speaker": "SPEAKER_01", "start": 8.5, "end": 9.9,
         "texto": "De acordo."},
    ]}


def test_separar_sem_mexer_no_texto_nao_conta_como_alteracao_de_texto():
    # Depois de separar, os índices deslizam: comparar índice a índice acusaria
    # alteração em texto que a pessoa não encostou. Separar é ajuste de FALA,
    # e o relatório não pode cobrá-lo como se fosse erro de transcrição.
    doc = _doc()
    corr = _corr_dividindo_o_primeiro()
    comp = relatorio.comparar(doc, correcao.aplicar(doc, corr), correcao=corr)
    assert comp["segmentos_alterados"] == 0
    assert comp["pct_texto_alterado"] == 0.0
    assert [a["tipo"] for a in comp["ajustes"]] == ["separado", "reatribuido"]


def test_alteracao_de_texto_dentro_de_trecho_separado_aponta_a_origem_certa():
    doc = _doc()
    corr = _corr_dividindo_o_primeiro("Bom dia, senhor presidente.")
    comp = relatorio.comparar(doc, correcao.aplicar(doc, corr), correcao=corr)
    assert comp["segmentos_alterados"] == 1
    assert comp["alteracoes"][0]["segs"] == [0]
    assert comp["alteracoes"][0]["corrigido"] == "Bom dia doutor. Bom dia, senhor presidente."


def test_relatorio_nao_chama_mesclagem_de_reatribuicao():
    doc = _doc()
    corr = {"segmentos": [], "merges": {"SPEAKER_02": "SPEAKER_01"}}
    doc_corr = correcao.aplicar(doc, corr)
    comp = relatorio.comparar(doc, doc_corr, correcao=corr)
    assert [a["tipo"] for a in comp["ajustes"]] == []      # nenhuma reatribuição
    assert comp["merges"] == {"SPEAKER_02": "SPEAKER_01"}
    assert comp["locutores_corrigido"] == 2


def test_relatorio_antigo_sem_origem_continua_funcionando():
    # Correção no formato 1.0 (aplicada por uma versão anterior): o relatório
    # ainda precisa comparar, caindo no pareamento índice a índice.
    doc = _doc()
    doc_corr = {"metadata": {}, "segments": [dict(s) for s in doc["segments"]]}
    doc_corr["segments"][1]["text"] = "Podemos começar."
    comp = relatorio.comparar(doc, doc_corr)
    assert comp["segmentos_alterados"] == 1
    assert comp["ajustes"] == []


def test_relatorio_e_pdf_saem_com_todo_tipo_de_ajuste(tmp_path):
    # O relatório é o documento que expõe a intervenção humana. Se ele quebrar
    # num tipo de ajuste, a conferência fica sem prestação de contas — então
    # este teste passa por TODOS: separação (com corte estimado), aglutinação,
    # reatribuição, mesclagem e interlocutor criado.
    from degravador.saidas import pdf as spdf

    doc = _doc()
    corr = {"segmentos": [
        {"origem": [0], "parte": 0, "speaker": "SPEAKER_00", "start": 0.0, "end": 2.1,
         "texto": "Bom dia, doutor."},
        {"origem": [0], "parte": 1, "speaker": "INTERLOCUTOR_1", "start": 2.1, "end": 4.0,
         "texto": "Bom dia, excelência.", "tempo_estimado": True},
        {"origem": [1, 2], "parte": 0, "speaker": "SPEAKER_01", "start": 4.2, "end": 8.0,
         "texto": "Podemos começar a audiência."},
        {"origem": [3], "parte": 0, "speaker": "INTERLOCUTOR_1", "start": 8.5, "end": 9.9,
         "texto": "De acordo."},
    ], "merges": {"SPEAKER_02": "SPEAKER_01"},
        "novos_locutores": {"INTERLOCUTOR_1": "Juiz"},
        "locutores": {"SPEAKER_00": "Promotor", "SPEAKER_01": "Testemunha",
                      "INTERLOCUTOR_1": "Juiz"}}

    doc_corr = correcao.aplicar(doc, corr, revisado_por="Maria Conferente")
    comp = relatorio.comparar(doc, doc_corr, correcao=corr)
    assert {a["tipo"] for a in comp["ajustes"]} == {"separado", "aglutinado", "reatribuido"}

    destino = relatorio.gerar_pdf(
        comp, tmp_path / "rel.pdf", meta=doc["metadata"],
        conferencista="Maria Conferente", mapa_locutores=corr["locutores"])
    assert destino.exists() and destino.stat().st_size > 1000

    # O PDF da degravação precisa listar na legenda o interlocutor criado.
    saida = spdf.exportar(doc_corr, tmp_path / "corrigido.pdf",
                          mapa_locutores=corr["locutores"], pos_conferencia=True,
                          revisado_por="Maria Conferente")
    assert saida.exists() and saida.stat().st_size > 1000


# ---------------------------------------------------------------------------
# Conferência (HTML): os controles precisam estar na página
# ---------------------------------------------------------------------------
def test_html_entrega_blocos_e_controles_de_interlocutor(tmp_path):
    p = html.exportar(_doc(), tmp_path / "conf.html", audio_src="audiencia.wav")
    c = p.read_text(encoding="utf-8")

    assert "window.__BLOCOS__" in c and "window.__LOCUTORES__" in c
    assert "window.__PALAVRAS__" in c          # tempos por palavra: corte fiel
    assert 'class="seg-spk"' in c or "seg-spk" in c
    assert "b-separar" in c and "b-juntar" in c
    assert 'id="btnNovoLoc"' in c              # criar voz que a máquina não separou
    assert 'id="desfazer"' in c
    assert "degravador-correcao/1.1" in c
    # O painel de cima continua sendo a prova: sem controles de edição nele.
    conferencia = c.split('id="conferencia"')[1].split('id="correcao"')[0]
    assert "contenteditable" not in conferencia


def test_html_oferece_interlocutores_mesmo_com_uma_voz_so(tmp_path):
    # É justamente o caso em que a diarização colou duas pessoas num rótulo:
    # sem o painel, não haveria como criar a segunda voz.
    doc = _doc()
    for s in doc["segments"]:
        s["speaker"] = "SPEAKER_00"
    c = html.exportar(doc, tmp_path / "uma.html").read_text(encoding="utf-8")
    assert 'id="btnNovoLoc"' in c
    assert "seg-spk" in c
