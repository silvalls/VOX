"""Saída PDF — documento oficial de degravação (VOX).

Espelha o DOCX oficial (ABNT + Manual de Redação): Arial 12, justificado, A4,
margens 3/3/2/2 cm, cabeçalho "TERMO DE DEGRAVAÇÃO" com SHA-256, legenda de
interlocutores, corpo por turno e termo de encerramento.

Suporta a versão "pós-conferência" (``pos_conferencia=True``): marca explicitamente
que houve conferência humana e registra o responsável (conferencista).

Usa fpdf2. Para acentuação completa, embute a fonte Arial do sistema Windows
(fallback: Helvetica do núcleo, com saneamento de caracteres).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ._comum import (
    fmt_hms, iter_turnos, rotulo_idioma as _rotulo_idioma, rotulo_locutor,
    texto_turno,
)


_MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

_FONTES_ARIAL = [
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
]

_ESTILO_PADRAO = {
    "titulo": "TERMO DE DEGRAVAÇÃO",
    "tamanho_pt": 12,
    "recuo_primeira_linha_cm": 1.25,
    "margens_cm": {"superior": 3, "esquerda": 3, "inferior": 2, "direita": 2},
    "termo_encerramento": "Documento produzido por processamento automatizado local (VOX).",
}


def _carregar_estilo(caminho_estilo: str | Path | None) -> dict:
    estilo = dict(_ESTILO_PADRAO)
    if caminho_estilo and Path(caminho_estilo).exists():
        with open(caminho_estilo, "r", encoding="utf-8") as f:
            estilo.update(json.load(f))
    return estilo


def _data_extenso(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{dt.day} de {_MESES[dt.month - 1]} de {dt.year}"


def _locutores_em_ordem(doc: dict) -> list[str]:
    vistos: list[str] = []
    for seg in doc.get("segments", []):
        spk = seg.get("speaker")
        if spk and spk not in vistos:
            vistos.append(spk)
    return vistos


def exportar(
    doc: dict,
    caminho: str | Path,
    *,
    mapa_locutores: dict | None = None,
    sem_timestamps: bool = False,
    caminho_estilo: str | Path | None = None,
    pos_conferencia: bool = False,
    revisado_por: str | None = None,
    **_opts,
) -> Path:
    from fpdf import FPDF

    estilo = _carregar_estilo(caminho_estilo)
    meta = doc.get("metadata", {})
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tam = estilo["tamanho_pt"]
    m = estilo["margens_cm"]

    # --- Fonte: Arial embutida (Unicode) ou Helvetica (núcleo, latin-1) ---
    fonte = "Helvetica"
    unicode_ok = False
    for regular, negrito in _FONTES_ARIAL:
        if Path(regular).exists() and Path(negrito).exists():
            fonte = "Arial"
            break

    class DocPDF(FPDF):
        def header(self):
            self.set_y(8)
            self.set_font(fonte, size=9)
            self.cell(0, 6, str(self.page_no()), align="R")
            self.set_y(m["superior"] * 10)

    pdf = DocPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(m["esquerda"] * 10, m["superior"] * 10, m["direita"] * 10)
    pdf.set_auto_page_break(auto=True, margin=m["inferior"] * 10)
    if fonte == "Arial":
        for regular, negrito in _FONTES_ARIAL:
            if Path(regular).exists():
                pdf.add_font("Arial", "", regular)
                pdf.add_font("Arial", "B", negrito)
                unicode_ok = True
                break

    def S(txt: str) -> str:
        if unicode_ok:
            return txt
        # Fallback latin-1: troca caracteres fora do conjunto por equivalentes.
        return (txt.replace("–", "-").replace("—", "-").replace("…", "...")
                   .replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
                   .encode("latin-1", "replace").decode("latin-1"))

    pdf.add_page()

    # === Título ===
    pdf.set_font(fonte, "B", tam + 1)
    pdf.cell(0, 9, S(estilo["titulo"].upper()), align="C", new_x="LMARGIN", new_y="NEXT")
    if pos_conferencia:
        pdf.set_font(fonte, "B", tam - 1)
        pdf.set_text_color(150, 40, 90)
        pdf.cell(0, 7, S("VERSÃO CORRIGIDA — PÓS-CONFERÊNCIA"), align="C",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # === Metadados ===
    def linha(rot, val):
        pdf.set_font(fonte, "B", tam)
        pdf.write(6, S(f"{rot}: "))
        pdf.set_font(fonte, "", tam)
        pdf.write(6, S(str(val if val is not None else "—")))
        pdf.ln(6)

    # No INÍCIO: apenas origem, data/hora e duração.
    linha("Arquivo de origem", meta.get("arquivo"))
    linha("Data e hora do processamento", meta.get("criado_em"))
    dur = meta.get("duracao_s")
    linha("Duração do áudio", fmt_hms(dur) if dur else None)

    # === Legenda de interlocutores ===
    locutores = _locutores_em_ordem(doc)
    if locutores:
        pdf.ln(2)
        pdf.set_font(fonte, "B", tam)
        pdf.cell(0, 6, S("Legenda de interlocutores"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fonte, "", tam)
        for spk in locutores:
            nome = rotulo_locutor(spk, mapa_locutores)
            if nome and nome != spk:
                pdf.cell(0, 6, S(f"{spk} -> {nome}"), new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.cell(0, 6, S(f"{spk} (rótulo técnico — não renomeado)"),
                         new_x="LMARGIN", new_y="NEXT")

    # === Corpo da degravação ===
    pdf.ln(3)
    pdf.set_font(fonte, "B", tam)
    pdf.cell(0, 6, S("Degravação"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(fonte, "", tam)

    identificar = len(locutores) > 1
    for turno in iter_turnos(doc):
        texto = texto_turno(turno)
        if not texto:
            continue
        texto = texto.replace("*", "")  # evita conflito com markdown do fpdf
        prefixo = ""
        if identificar:
            nome = (rotulo_locutor(turno["speaker"], mapa_locutores) or "LOCUTOR").upper()
            ts = "" if sem_timestamps else f" ({fmt_hms(turno['start'])})"
            prefixo = f"**{nome}{ts}:** "
        pdf.multi_cell(0, 6.5, S(f"{prefixo}{texto}"), align="J", markdown=True,
                       new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)

    # === Fecho — Identificação e integridade (última parte do documento) ===
    pdf.ln(6)
    pdf.set_draw_color(180, 180, 180)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(3)
    pdf.set_font(fonte, "B", tam)
    pdf.cell(0, 7, S("IDENTIFICAÇÃO E INTEGRIDADE"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    params = meta.get("params") or {}
    linha("Interlocutores identificados", meta.get("num_speakers"))
    linha("Idioma da fala", _rotulo_idioma(params))
    linha("Modelo utilizado", meta.get("modelo"))
    linha("Versão do VOX", meta.get("versao_app"))
    if pos_conferencia:
        linha("Conferência humana", "SIM — trechos conferidos contra o áudio")
        linha("Responsável pela conferência", revisado_por or meta.get("revisado_por") or "—")
    else:
        linha("Conferência humana", "NÃO (versão pré-conferência)")
        linha("Responsável pela conferência", "____________________")
    linha("Hash SHA-256 do original", meta.get("sha256"))

    # === Aviso: degravação sem alinhamento por palavra ===
    # Sem forced alignment não há score por palavra, e a conferência perde o
    # realce palavra a palavra. A ausência de marcações passaria por
    # "transcrição limpa" quando na verdade é "não foi medida" — distinção que,
    # num documento com pretensão probatória, não é cosmética.
    if params.get("alinhamento_por_palavra") is False:
        pdf.ln(2)
        pdf.set_font(fonte, "B", tam - 1)
        pdf.multi_cell(
            0, 5.5,
            S("Observação: não houve alinhamento por palavra para este idioma. "
              "Os timestamps são por trecho de fala, e a confiança foi medida "
              "por trecho — não palavra a palavra. A ausência de realces de "
              "baixa confiança palavra a palavra, portanto, NÃO indica "
              "transcrição conferida: indica medição não realizada nesse nível."),
            align="J", new_x="LMARGIN", new_y="NEXT",
        )
        pdf.set_font(fonte, "", tam)

    # === Termo de encerramento ===
    pdf.ln(3)
    pdf.set_font(fonte, "", tam)
    pdf.multi_cell(0, 6.5, S(estilo["termo_encerramento"]), align="J",
                   new_x="LMARGIN", new_y="NEXT")
    data = _data_extenso(meta.get("criado_em"))
    if data:
        pdf.ln(2)
        pdf.cell(0, 6, S(data), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.cell(0, 6, S("____________________________________"), align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, S("Responsável pela conferência"), align="C",
             new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(caminho))
    return caminho
