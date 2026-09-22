"""Relatório diferencial de conferência — original × corrigido (pós-conferência).

Compara a versão exportada inicialmente (o que a máquina transcreveu) com a versão
corrigida pelo conferencista, apura o **percentual de alteração** e lista, trecho a
trecho, o que mudou. É um documento **à parte**, para transparência e auditoria da
intervenção humana.

Registra duas classes de intervenção, porque são responsabilidades distintas:

  - **texto** — o que se ouviu diferente do que a máquina escreveu;
  - **atribuição de fala** — trechos separados, aglutinados, reatribuídos a outro
    interlocutor, rótulos mesclados e interlocutores criados na conferência.

A comparação não pode ser índice a índice: separar e aglutinar mudam a contagem de
segmentos. Ela é feita por **grupo de origem** — o campo ``origem_seg`` que a
correção grava em cada segmento resultante amarra cada trecho corrigido aos
segmentos brutos de onde veio.
"""

from __future__ import annotations

import difflib
from datetime import datetime
from pathlib import Path

from .saidas._comum import fmt_hms, rotulo_locutor

_FONTES_ARIAL = (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf")
_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _texto(seg: dict) -> str:
    return (seg.get("text") or "").strip()


def _grupos(segs_o: list, segs_c: list) -> list[tuple[list[int], list[dict]]]:
    """Casa segmentos originais com os corrigidos que os cobrem.

    Devolve ``[(indices_originais, segmentos_corrigidos), ...]`` na ordem do
    áudio. Um grupo com mais corrigidos que originais é uma **separação**; com
    mais originais que corrigidos, uma **aglutinação**.

    Sem ``origem_seg`` (correções antigas), cai no pareamento índice a índice.
    """
    tem_origem = any(s.get("origem_seg") is not None for s in segs_c)
    if not tem_origem:
        return [([i], [segs_c[i]]) for i in range(min(len(segs_o), len(segs_c)))]

    # União dos índices originais que um mesmo segmento corrigido amarra.
    pai: dict[int, int] = {}

    def achar(i):
        pai.setdefault(i, i)
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    def unir(a, b):
        ra, rb = achar(a), achar(b)
        if ra != rb:
            pai[max(ra, rb)] = min(ra, rb)

    for s in segs_c:
        origem = s.get("origem_seg") or []
        for i in origem[1:]:
            unir(origem[0], i)

    grupos: dict[int, tuple[list[int], list[dict]]] = {}
    for i in range(len(segs_o)):
        grupos.setdefault(achar(i), ([], []))[0].append(i)
    for s in segs_c:
        origem = s.get("origem_seg") or []
        if not origem:
            continue
        grupos.setdefault(achar(origem[0]), ([], []))[1].append(s)
    return [grupos[k] for k in sorted(grupos)]


def comparar(doc_orig: dict, doc_corr: dict, *, correcao: dict | None = None) -> dict:
    """Apura as diferenças entre as duas versões (texto e atribuição de fala)."""
    segs_o = doc_orig.get("segments", [])
    segs_c = doc_corr.get("segments", [])
    merges = dict((correcao or {}).get("merges") or {})
    criados = dict((correcao or {}).get("novos_locutores")
                   or doc_corr.get("metadata", {}).get("locutores_criados_na_conferencia") or {})

    def resolver(spk):
        visto = set()
        while spk in merges and spk not in visto:
            visto.add(spk)
            spk = merges[spk]
        return spk

    alteracoes: list[dict] = []
    ajustes: list[dict] = []
    total = alterados = 0

    for indices, corrigidos in _grupos(segs_o, segs_c):
        to = " ".join(_texto(segs_o[i]) for i in indices).strip()
        tc = " ".join(_texto(c) for c in corrigidos).strip()
        inicio = segs_o[indices[0]].get("start") if indices else None

        if to or tc:
            total += 1
            if to != tc:
                alterados += 1
                alteracoes.append({
                    "seg": indices[0] if indices else None,
                    "segs": indices,
                    "start": inicio,
                    "speaker": segs_o[indices[0]].get("speaker") if indices else None,
                    "original": to,
                    "corrigido": tc,
                })

        # --- estrutura de fala ---
        if len(corrigidos) > len(indices):
            ajustes.append({
                "tipo": "separado",
                "start": inicio,
                "partes": [{"start": c.get("start"), "speaker": c.get("speaker"),
                            "texto": _texto(c), "estimado": bool(c.get("tempo_estimado"))}
                           for c in corrigidos],
            })
        elif indices and len(indices) > len(corrigidos) and corrigidos:
            ajustes.append({
                "tipo": "aglutinado",
                "start": inicio,
                "segs": indices,
                "speaker": corrigidos[0].get("speaker"),
                "texto": tc,
            })

        for c in corrigidos:
            origem = c.get("origem_seg") or indices
            if not origem:
                continue
            antes = segs_o[origem[0]].get("speaker")
            depois = c.get("speaker")
            # Mesclagem de rótulos não é reatribuição de trecho: é a mesma voz
            # ganhando um nome só. Relatada à parte, não trecho a trecho.
            if antes != depois and resolver(antes) != depois:
                ajustes.append({
                    "tipo": "reatribuido",
                    "start": c.get("start"),
                    "de": antes, "para": depois,
                    "texto": _texto(c),
                })

    texto_o = " ".join(_texto(s) for s in segs_o)
    texto_c = " ".join(_texto(s) for s in segs_c)
    ratio = difflib.SequenceMatcher(None, texto_o, texto_c).ratio()
    return {
        "total_segmentos": total,
        "segmentos_alterados": alterados,
        "pct_segmentos": (alterados / total * 100) if total else 0.0,
        "pct_texto_alterado": (1 - ratio) * 100,
        "similaridade": ratio * 100,
        "alteracoes": alteracoes,
        "ajustes": ajustes,
        "merges": merges,
        "locutores_criados": criados,
        "locutores_original": len({s.get("speaker") for s in segs_o if s.get("speaker")}),
        "locutores_corrigido": len({s.get("speaker") for s in segs_c if s.get("speaker")}),
    }


def _data_extenso(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{dt.day} de {_MESES[dt.month - 1]} de {dt.year}"


def gerar_pdf(
    comp: dict,
    caminho: str | Path,
    *,
    meta: dict,
    conferencista: str | None = None,
    mapa_locutores: dict | None = None,
) -> Path:
    from fpdf import FPDF

    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    fonte = "Helvetica"
    unicode_ok = False
    if Path(_FONTES_ARIAL[0]).exists():
        fonte = "Arial"

    class RPDF(FPDF):
        def header(self):
            self.set_y(8)
            self.set_font(fonte, size=9)
            self.cell(0, 6, str(self.page_no()), align="R")
            self.set_y(30)

    pdf = RPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(30, 30, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    if fonte == "Arial":
        pdf.add_font("Arial", "", _FONTES_ARIAL[0])
        pdf.add_font("Arial", "B", _FONTES_ARIAL[1])
        unicode_ok = True

    def S(t: str) -> str:
        if unicode_ok:
            return t
        return (t.replace("–", "-").replace("—", "-").replace("…", "...")
                 .encode("latin-1", "replace").decode("latin-1"))

    pdf.add_page()

    pdf.set_font(fonte, "B", 13)
    pdf.cell(0, 9, S("RELATÓRIO DE CONFERÊNCIA"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(fonte, "", 11)
    pdf.cell(0, 6, S("Comparativo: versão original × versão corrigida (pós-conferência)"),
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    def linha(rot, val):
        pdf.set_font(fonte, "B", 12)
        pdf.write(6, S(f"{rot}: "))
        pdf.set_font(fonte, "", 12)
        pdf.write(6, S(str(val if val is not None else "—")))
        pdf.ln(6)

    linha("Arquivo de origem", meta.get("arquivo"))
    linha("Responsável pela conferência", conferencista or "—")
    linha("Data e hora do processamento", meta.get("criado_em"))
    linha("Hash SHA-256 do original", meta.get("sha256"))

    # Resumo percentual
    pdf.ln(3)
    pdf.set_fill_color(243, 238, 255)
    pdf.set_font(fonte, "B", 12)
    pdf.cell(0, 8, S("Resumo das alterações"), new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_font(fonte, "", 12)
    total = comp["total_segmentos"]
    alt = comp["segmentos_alterados"]
    linha("Segmentos alterados", f"{alt} de {total}  ({comp['pct_segmentos']:.1f}%)")
    linha("Percentual de alteração do texto", f"{comp['pct_texto_alterado']:.1f}%")
    linha("Similaridade com o original", f"{comp['similaridade']:.1f}%")
    if comp.get("locutores_original") or comp.get("locutores_corrigido"):
        linha("Interlocutores", f"{comp.get('locutores_original', 0)} identificados pela máquina → "
                                f"{comp.get('locutores_corrigido', 0)} após a conferência")

    # --- Ajustes de atribuição de fala ---
    # Quem falou o quê é metade do valor probatório do documento. Se a pessoa
    # separou, aglutinou ou reatribuiu trechos, isso precisa estar escrito: é
    # intervenção humana sobre o que a máquina havia concluído.
    ajustes = comp.get("ajustes") or []
    merges = comp.get("merges") or {}
    criados = comp.get("locutores_criados") or {}
    if ajustes or merges or criados:
        def nome(spk):
            return rotulo_locutor(spk, mapa_locutores) or spk or "(sem interlocutor)"

        pdf.ln(3)
        pdf.set_font(fonte, "B", 12)
        pdf.cell(0, 8, S("Ajustes de atribuição de fala"), new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.set_font(fonte, "", 11)

        for spk, n in criados.items():
            pdf.multi_cell(0, 6, S(f"• Interlocutor criado na conferência: {spk}"
                                   + (f" — {n}" if n and n != spk else "")),
                           new_x="LMARGIN", new_y="NEXT")
        for de, para in merges.items():
            pdf.multi_cell(0, 6, S(f"• Rótulos mesclados: {nome(de)} passou a ser {nome(para)} "
                                   "em todo o documento (mesma voz, dois rótulos)."),
                           new_x="LMARGIN", new_y="NEXT")
        for a in ajustes:
            ts = fmt_hms(a.get("start") or 0.0)
            if a["tipo"] == "separado":
                quem = " / ".join(nome(p.get("speaker")) for p in a.get("partes", []))
                estimado = any(p.get("estimado") for p in a.get("partes", []))
                obs = " (ponto de corte estimado pelo texto — sem alinhamento por palavra)" if estimado else ""
                pdf.multi_cell(0, 6, S(f"• [{ts}] Fala separada em {len(a.get('partes', []))} trechos "
                                       f"→ {quem}.{obs}"), new_x="LMARGIN", new_y="NEXT")
            elif a["tipo"] == "aglutinado":
                pdf.multi_cell(0, 6, S(f"• [{ts}] {len(a.get('segs', []))} trechos aglutinados "
                                       f"numa fala só de {nome(a.get('speaker'))}."),
                               new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.multi_cell(0, 6, S(f"• [{ts}] Trecho reatribuído: {nome(a.get('de'))} "
                                       f"→ {nome(a.get('para'))}."), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    # Lista de alterações
    pdf.ln(3)
    pdf.set_font(fonte, "B", 12)
    pdf.cell(0, 7, S("Detalhamento das alterações"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    if not comp["alteracoes"]:
        pdf.set_font(fonte, "", 12)
        pdf.multi_cell(0, 6.5, S("Nenhuma alteração — o texto corrigido é idêntico ao "
                                 "originalmente transcrito."), new_x="LMARGIN", new_y="NEXT")
    else:
        for a in comp["alteracoes"]:
            nome = rotulo_locutor(a.get("speaker"), mapa_locutores) or ""
            cab = f"[{fmt_hms(a.get('start') or 0.0)}] {nome}".strip()
            pdf.set_font(fonte, "B", 11)
            pdf.multi_cell(0, 6, S(cab), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(fonte, "", 11)
            pdf.set_text_color(150, 60, 60)
            pdf.multi_cell(0, 6, S(f"Original:  {a['original']}"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(40, 110, 70)
            pdf.multi_cell(0, 6, S(f"Corrigido: {a['corrigido'] or '(removido)'}"),
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)

    pdf.ln(4)
    pdf.set_font(fonte, "", 10)
    pdf.multi_cell(0, 5.5, S("Observação: a transcrição bruta original é preservada; este "
                             "relatório documenta exclusivamente as correções humanas "
                             "realizadas na conferência."), new_x="LMARGIN", new_y="NEXT")
    data = _data_extenso(meta.get("criado_em"))
    if data:
        pdf.ln(2)
        pdf.cell(0, 6, S(data), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(caminho))
    return caminho
