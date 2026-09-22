"""Saída HTML — espaço de conferência + correção (offline, autocontido).

Dois painéis sincronizados por um mesmo áudio:

  • CONFERÊNCIA (topo, somente leitura): a transcrição ORIGINAL, com a atribuição
    ORIGINAL de locutores. Clicar numa palavra toca aquele instante; a palavra
    corrente é destacada; trechos de baixa confiança ficam realçados. Este painel
    NUNCA é editado — é a prova.

  • CORREÇÃO (embaixo, editável): o mesmo texto, em blocos, pré-preenchido e
    editável. Aqui o conferente ouve e corrige **texto e atribuição de fala**:

      - trocar o interlocutor de um bloco inteiro;
      - SEPARAR um bloco em dois no ponto do cursor (quando a diarização juntou
        duas pessoas na mesma fala) e dar a cada parte o seu interlocutor;
      - JUNTAR (aglutinar) blocos vizinhos num só, inclusive de segmentos
        diferentes (quando a diarização picotou a fala de uma pessoa só);
      - CRIAR um interlocutor que a máquina não separou;
      - MESCLAR dois rótulos que são a mesma pessoa, em todo o documento.

    Toda alteração estrutural pode ser desfeita (↶ desfazer).

O painel de correção é montado pelo JavaScript a partir de ``window.__BLOCOS__``:
separar, juntar e restaurar rascunho produzem exatamente a mesma marcação que a
carga inicial, porque passam todos pela mesma função de renderização.

Quando aberto dentro do app desktop (pywebview), o botão salvar chama o Python
(``window.pywebview.api.salvar_correcao``). Aberto direto no navegador, ele baixa
um ``.correcao.json`` que o CLI converte em PDF corrigido.

O áudio NÃO é embutido (arquivos de horas seriam enormes); a página espera o
WAV/mídia ao lado dela (a CLI posiciona e passa ``audio_src``).
"""

from __future__ import annotations

import html as _html
import json
from pathlib import Path
from urllib.parse import quote as _url_quote

from ._comum import (
    fmt_hms, iter_turnos, rotulo_idioma, rotulo_locutor, texto_segmento,
)
from .. import branding


_CSS = """
:root { --baixa:#f8d7da; --atual:#ffd54a; --ativo:#f3eeff; --borda:#e2e2e2;
        --marca:#7b3fd6; --marca-b:#f7b23c;
        --grad:linear-gradient(100deg,#f7b23c,#c26bb0,#7b3fd6); }
* { box-sizing:border-box; }
html,body { height:100%; }
body { margin:0; font-family:system-ui,Arial,sans-serif; color:#1a1a1a;
       background:#f4f5f7; display:flex; flex-direction:column; }
header { background:#fff; border-bottom:1px solid var(--borda); padding:10px 16px;
         box-shadow:0 1px 4px rgba(0,0,0,.06); z-index:10; }
header h1 { font-size:15px; margin:0 0 8px; }
.marca-conf { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.marca-conf img { height:34px; width:auto; }
.marca-conf .nome { font-weight:800; letter-spacing:1px; font-size:20px;
  background:var(--grad); -webkit-background-clip:text; background-clip:text;
  -webkit-text-fill-color:transparent; }
.marca-conf .sub { font-size:10px; color:#999; letter-spacing:1px; align-self:flex-end;
  padding-bottom:3px; }
audio { width:100%; }
.barra { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:8px; font-size:13px; }
.barra button { font-size:13px; padding:6px 10px; border:1px solid #bbb; border-radius:6px;
                background:#fff; cursor:pointer; }
.barra button.primario { background:var(--grad); color:#fff; border:0; font-weight:700; }
.barra button:hover { filter:brightness(.97); }
.barra button:disabled { opacity:.45; cursor:default; }
.barra label { display:flex; align-items:center; gap:4px; color:#444; }
.amostra { display:inline-block; width:12px; height:12px; border-radius:2px; vertical-align:middle; }
#salvo { color:#8a4fd8; font-weight:600; }
main { flex:1; display:flex; flex-direction:column; overflow:hidden; }
.painel { overflow:auto; padding:16px 20px; }
.painel-titulo { position:sticky; top:0; background:#f4f5f7; margin:0 0 8px; padding:6px 0;
                 font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:#777;
                 font-weight:700; border-bottom:1px solid var(--borda); }
.painel-titulo .dica-painel { text-transform:none; letter-spacing:0; font-weight:400;
  color:#999; font-size:11px; margin-left:8px; }
#conferencia { flex:1; background:#fbfbfc; line-height:1.9; }
#correcao { flex:1; background:#fff; border-top:3px solid #7b3fd6; line-height:1.7; }
.turno { margin:0 0 14px; }
.locutor { font-weight:700; text-transform:uppercase; color:#8a4fd8; cursor:pointer; }
.locutor .ts { color:#999; font-weight:400; }
.w { cursor:pointer; padding:0 1px; border-radius:3px; }
.w:hover { background:#e8f0fe; }
.w.baixa { background:var(--baixa); }
.w.atual { background:var(--atual); box-shadow:0 0 0 2px var(--atual); }
.marca { color:#a00; font-style:italic; }
.edit-turno { margin:0 0 12px; padding:6px 8px; border-radius:6px; border:1px solid transparent; }
.edit-turno.ativo { background:var(--ativo); border-color:#cfe0ff; }
.edit-turno.parte { border-left:3px solid #c26bb0; }
.edit-cab { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-bottom:3px; }
.edit-ts { color:#888; font-size:12px; cursor:pointer; font-variant-numeric:tabular-nums; }
.edit-ts:hover { color:#7b3fd6; text-decoration:underline; }
.edit-locutor { font-weight:700; text-transform:uppercase; color:#555; font-size:.9em; }
.seg-spk { font-size:12px; font-weight:700; padding:3px 6px; border:1px solid var(--borda);
  border-radius:5px; background:#fff; color:#6a3fb0; max-width:230px; cursor:pointer; }
.seg-spk:focus { outline:none; border-color:#7b3fd6; box-shadow:0 0 0 2px #e7dcff; }
.edit-acoes { display:flex; gap:4px; opacity:0; transition:opacity .12s; }
.edit-turno:hover .edit-acoes, .edit-turno.ativo .edit-acoes,
.edit-turno:focus-within .edit-acoes { opacity:1; }
.edit-acoes button { font-size:11px; padding:2px 7px; border:1px solid var(--borda);
  border-radius:5px; background:#fff; color:#555; cursor:pointer; }
.edit-acoes button:hover { background:#f3eeff; border-color:#b79ae8; color:#5a2ea6; }
.edit-acoes button:disabled { opacity:.35; cursor:default; background:#fff; }
.edit-texto { display:block; margin-top:2px; padding:4px 6px; border:1px solid var(--borda);
              border-radius:5px; background:#fff; min-height:1.7em; outline:none; }
.edit-texto:focus { border-color:#7b3fd6; box-shadow:0 0 0 2px #e7dcff; }
.ren-painel { margin-top:8px; font-size:13px; }
.ren-painel summary { cursor:pointer; color:#8a4fd8; font-weight:600; }
.ren-grade { display:flex; flex-wrap:wrap; gap:8px 16px; margin-top:8px; align-items:center; }
.loc-item { display:flex; align-items:center; gap:6px; }
.loc-id { font-weight:700; color:#666; font-size:12px; }
.loc-item.novo .loc-id { color:#0a7a3f; }
.loc-seta { color:#aaa; }
.loc-nome { padding:4px 8px; border:1px solid var(--borda); border-radius:5px; min-width:200px; }
.loc-nome:focus { border-color:#7b3fd6; outline:none; box-shadow:0 0 0 2px #e7dcff; }
#btnNovoLoc { font-size:12px; padding:5px 10px; border:1px dashed #b79ae8; border-radius:6px;
  background:#faf7ff; color:#6a3fb0; cursor:pointer; font-weight:600; }
#btnNovoLoc:hover { background:#f3eeff; }
.vel { font-size:13px; color:#555; } .vel b { color:#222; }
.barra small { color:#999; font-weight:400; }
.barra2 { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:8px; font-size:13px; }
.barra2 input#busca { padding:6px 10px; border:1px solid var(--borda); border-radius:6px;
  min-width:240px; font-size:13px; }
.barra2 input#busca:focus { outline:none; border-color:#7b3fd6; box-shadow:0 0 0 2px #e7dcff; }
.barra2 button { font-size:13px; padding:5px 9px; border:1px solid #bbb; border-radius:6px;
  background:#fff; cursor:pointer; }
.barra2 button:disabled { opacity:.45; cursor:default; }
#buscaInfo { color:#777; } #rascunhoAviso { color:#0a7a3f; font-weight:600; }
#rascunhoAviso button { margin-left:6px; font-size:12px; }
#avisoEdicao { color:#8a2b8a; font-weight:600; }
.w.busca-hit { background:#fff2a8; } .w.busca-atual { background:#ffcaa8; box-shadow:0 0 0 2px #ffaf7a; }
.loc-merge { font-size:12px; padding:3px 4px; border:1px solid var(--borda); border-radius:5px;
  background:#fff; color:#555; }
.modal-conf { position:fixed; inset:0; background:rgba(10,10,20,.72); z-index:100;
  display:flex; align-items:center; justify-content:center; }
.modal-cartao { background:#fff; border-radius:14px; padding:28px 32px; width:min(460px,92vw);
  box-shadow:0 20px 60px rgba(0,0,0,.4); }
.modal-cartao .mt { font-weight:800; font-size:20px; margin-bottom:6px;
  background:var(--grad); -webkit-background-clip:text; background-clip:text;
  -webkit-text-fill-color:transparent; }
.modal-cartao p { color:#556; font-size:14px; margin:0 0 16px; }
.modal-cartao input { width:100%; padding:11px 13px; border:1px solid #cfc9dd; border-radius:9px;
  font-size:15px; margin-bottom:14px; }
.modal-cartao input:focus { outline:none; border-color:#7b3fd6; box-shadow:0 0 0 2px #e7dcff; }
.modal-cartao button { width:100%; padding:12px; border:0; border-radius:9px; font-size:15px;
  font-weight:800; color:#fff; background:var(--grad); cursor:pointer; }
.aviso-portatil { margin:6px 0 2px; padding:8px 12px; border-radius:8px; font-size:13px;
  background:#fff6e6; border:1px solid #f0d090; color:#7a5b12; }
.aviso-alinhamento { margin:6px 0 2px; padding:8px 12px; border-radius:8px; font-size:13px;
  background:#fdecec; border:1px solid #e2a3a3; color:#8a2b2b; }
</style>
"""

_JS = """
<script>
(function () {
  const audio = document.getElementById('audio');
  const palavras = Array.prototype.slice.call(document.querySelectorAll('#conferencia .w[data-start]'));
  const inicios = palavras.map(w => parseFloat(w.dataset.start));
  const seguir = document.getElementById('seguir');
  const salvo = document.getElementById('salvo');
  const painelCorr = document.getElementById('correcao');
  const grade = document.getElementById('renGrade');
  const avisoEdicao = document.getElementById('avisoEdicao');
  const PALAVRAS = window.__PALAVRAS__ || {};

  // Dentro do VOX (pywebview): some o aviso de cópia portátil e o botão passa a
  // indicar que gera o PDF. Fora do VOX (navegador), o aviso permanece.
  window.addEventListener('pywebviewready', () => {
    const av = document.getElementById('avisoPortatil'); if (av) av.style.display = 'none';
    const b = document.getElementById('salvar'); if (b) b.textContent = 'Salvar correção (gera PDF)';
  });

  function fmtHMS(t) {
    t = Math.max(0, t || 0);
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = Math.floor(t % 60);
    const p = n => String(n).padStart(2, '0');
    return p(h) + ':' + p(m) + ':' + p(s);
  }
  function tocarEm(t) { if (!isNaN(t)) { audio.currentTime = t; audio.play(); } }

  document.querySelectorAll('#conferencia [data-seek]').forEach(el =>
    el.addEventListener('click', () => tocarEm(parseFloat(el.dataset.seek))));

  // =====================================================================
  // INTERLOCUTORES
  // A lista é a fonte de verdade da identidade das vozes: ordem de aparição
  // (que o PDF usa na legenda), nome atribuído pela pessoa e marca de "criado
  // na conferência". 'merges' registra rótulos absorvidos por outro.
  // =====================================================================
  let locutores = (window.__LOCUTORES__ || []).map(l => ({ id: l.id, nome: l.nome || '', novo: false }));
  let merges = {};

  function acharLoc(id) { for (const l of locutores) if (l.id === id) return l; return null; }
  function resolver(id) {           // segue a cadeia de mesclagens
    const visto = {};
    while (id && merges[id] && !visto[id]) { visto[id] = 1; id = merges[id]; }
    return id;
  }
  function nomeDe(id) {
    if (!id) return '(sem interlocutor)';
    const l = acharLoc(resolver(id));
    return (l && l.nome.trim()) ? l.nome.trim() : resolver(id);
  }
  function locutoresVivos() { return locutores.filter(l => !merges[l.id]); }

  function novoId() {
    let n = 1, id;
    do { id = 'INTERLOCUTOR_' + n; n++; } while (acharLoc(id));
    return id;
  }

  // ---- painel de nomear/mesclar (montado a partir de 'locutores') ----
  function renderLocutores() {
    if (!grade) return;
    const foco = document.activeElement;
    const focoId = (foco && foco.classList.contains('loc-nome')) ? foco.dataset.speaker : null;
    const posCaret = focoId ? foco.selectionStart : null;
    grade.innerHTML = '';
    locutoresVivos().forEach(l => {
      const item = document.createElement('div');
      item.className = 'loc-item' + (l.novo ? ' novo' : '');
      item.dataset.row = l.id;
      const id = document.createElement('span');
      id.className = 'loc-id'; id.textContent = l.novo ? '✚ ' + l.id : l.id;
      const seta = document.createElement('span');
      seta.className = 'loc-seta'; seta.textContent = '→';
      const inp = document.createElement('input');
      inp.className = 'loc-nome'; inp.type = 'text'; inp.dataset.speaker = l.id;
      inp.placeholder = l.id + ' (deixe em branco se não souber)';
      inp.value = l.nome;
      inp.addEventListener('input', () => {
        l.nome = inp.value;
        aplicarNomes();      // barato: só o rótulo visível de cada trecho
        agendarSelects();    // caro: reconstrói as listas — só quando a pessoa pára
        salvarRascunho();
      });
      const sel = document.createElement('select');
      sel.className = 'loc-merge'; sel.dataset.speaker = l.id;
      sel.title = 'Mesclar: tudo o que é deste rótulo passa a ser do outro, no documento inteiro';
      sel.appendChild(new Option('↳ mesclar com…', ''));
      locutoresVivos().forEach(o => { if (o.id !== l.id) sel.appendChild(new Option(nomeDe(o.id), o.id)); });
      sel.addEventListener('change', () => {
        const de = l.id, para = sel.value;
        sel.value = '';
        if (!para || de === para) return;
        if (!confirm('Mesclar ' + nomeDe(de) + ' em ' + nomeDe(para) + '?\\n' +
                     'Todas as falas de ' + nomeDe(de) + ' passarão a ser de ' + nomeDe(para) + '.')) return;
        guardarPasso();
        merges[de] = para;
        painelCorr.querySelectorAll('.edit-turno').forEach(el => {
          if (el.dataset.speaker === de) el.dataset.speaker = para;
        });
        renderLocutores(); atualizarSelects(); aplicarNomes();
        anunciar('Interlocutores mesclados.'); salvarRascunho();
      });
      item.append(id, seta, inp, sel);
      grade.appendChild(item);
    });
    if (focoId) {
      const volta = grade.querySelector('.loc-nome[data-speaker="' + CSS.escape(focoId) + '"]');
      if (volta) { volta.focus(); if (posCaret != null) volta.setSelectionRange(posCaret, posCaret); }
    }
  }

  function criarLocutor(nome) {
    const l = { id: novoId(), nome: nome || '', novo: true };
    locutores.push(l);
    renderLocutores(); atualizarSelects();
    return l;
  }

  const btnNovoLoc = document.getElementById('btnNovoLoc');
  if (btnNovoLoc) btnNovoLoc.addEventListener('click', () => {
    guardarPasso();
    const l = criarLocutor('');
    focarNome(l.id);
    anunciar('Interlocutor criado — dê um nome a ele.');
    salvarRascunho();
  });

  function focarNome(id) {
    const painel = document.querySelector('.ren-painel');
    if (painel) painel.open = true;
    const inp = grade && grade.querySelector('.loc-nome[data-speaker="' + CSS.escape(id) + '"]');
    if (inp) { inp.scrollIntoView({ block: 'nearest' }); inp.focus(); }
  }

  // Nome aplicado ao vivo em toda a página. O painel de cima (a prova) mantém a
  // ATRIBUIÇÃO original — só o nome exibido acompanha; reatribuições de fala
  // valem para o documento corrigido.
  function aplicarNomes() {
    document.querySelectorAll('#conferencia .locutor[data-speaker]').forEach(el => {
      const nl = el.querySelector('.nome-loc');
      if (nl) nl.textContent = nomeDe(el.dataset.speaker);
    });
    painelCorr.querySelectorAll('.edit-turno').forEach(el => {
      const sel = el.querySelector('.seg-spk');
      if (sel) {
        const opt = sel.querySelector('option[value="' + CSS.escape(el.dataset.speaker || '') + '"]');
        if (opt) opt.textContent = nomeDe(el.dataset.speaker);
      }
    });
  }

  function atualizarSelects() {
    painelCorr.querySelectorAll('.seg-spk').forEach(sel => preencherSelect(sel, sel.closest('.edit-turno').dataset.speaker));
  }

  let selTimer;
  function agendarSelects() { clearTimeout(selTimer); selTimer = setTimeout(atualizarSelects, 400); }

  function preencherSelect(sel, atual) {
    atual = resolver(atual || '') || '';
    sel.innerHTML = '';
    sel.appendChild(new Option('(sem interlocutor)', ''));
    locutoresVivos().forEach(l => sel.appendChild(new Option(nomeDe(l.id), l.id)));
    if (atual && !acharLoc(atual)) sel.appendChild(new Option(atual, atual));
    sel.appendChild(new Option('✚ novo interlocutor…', '__novo__'));
    sel.value = atual;
  }

  // =====================================================================
  // BLOCOS DE CORREÇÃO
  // Cada bloco é um trecho de fala editável. 'origem' guarda de quais
  // segmentos da transcrição original ele veio — é o que liga a correção ao
  // documento probatório, mesmo depois de separar e aglutinar.
  // =====================================================================
  function origemDe(el) {
    return (el.dataset.origem || '').split(',').filter(s => s !== '').map(Number);
  }

  function criarBloco(b) {
    const el = document.createElement('div');
    el.className = 'edit-turno' + (b.parte ? ' parte' : '');
    el.dataset.origem = (b.origem || []).join(',');
    el.dataset.parte = b.parte || 0;
    el.dataset.off0 = b.off0 || 0;
    el.dataset.start = (b.start != null ? b.start : 0);
    el.dataset.end = (b.end != null ? b.end : (b.start || 0));
    el.dataset.speaker = b.speaker || '';
    if (b.estimado) el.dataset.estimado = '1';

    const cab = document.createElement('span');
    cab.className = 'edit-cab';

    const sel = document.createElement('select');
    sel.className = 'seg-spk';
    sel.title = 'A quem pertence esta fala';
    preencherSelect(sel, el.dataset.speaker);
    sel.addEventListener('change', () => {
      if (sel.value === '__novo__') {
        guardarPasso();
        const l = criarLocutor('');
        el.dataset.speaker = l.id;
        atualizarSelects();
        focarNome(l.id);
        anunciar('Interlocutor criado e atribuído — dê um nome a ele.');
      } else {
        guardarPasso();
        el.dataset.speaker = sel.value;
        anunciar('Fala reatribuída a ' + nomeDe(sel.value) + '.');
      }
      salvarRascunho();
    });

    const ts = document.createElement('span');
    ts.className = 'edit-ts';
    ts.textContent = fmtHMS(parseFloat(el.dataset.start));
    ts.title = 'Ouvir a partir daqui';
    ts.addEventListener('click', () => tocarEm(parseFloat(el.dataset.start)));

    const acoes = document.createElement('span');
    acoes.className = 'edit-acoes';
    const bSep = document.createElement('button');
    bSep.type = 'button'; bSep.className = 'b-separar'; bSep.textContent = '✂ separar';
    bSep.title = 'Separar em dois a partir do cursor — para quando duas pessoas caíram na mesma fala';
    // O clique não pode tirar o foco do texto: é a posição do cursor que define
    // ONDE separar. Sem isto, o botão apagaria justamente o dado que ele usa.
    bSep.addEventListener('mousedown', e => e.preventDefault());
    bSep.addEventListener('click', () => separar(el));
    const bJun = document.createElement('button');
    bJun.type = 'button'; bJun.className = 'b-juntar'; bJun.textContent = '⬆ juntar';
    bJun.title = 'Aglutinar este trecho ao bloco de cima — para quando a fala de uma pessoa foi picotada';
    bJun.addEventListener('click', () => juntar(el));
    acoes.append(bSep, bJun);

    cab.append(sel, ts, acoes);

    const campo = document.createElement('span');
    campo.className = 'edit-texto';
    campo.contentEditable = 'true';
    campo.spellcheck = true;
    campo.textContent = b.texto || '';
    campo.addEventListener('input', salvarRascunho);
    // Guardamos a última posição do cursor: o navegador pode recolher a seleção
    // ao clicar num botão, e "separar" depende dela.
    ['keyup', 'mouseup', 'input', 'focus'].forEach(ev =>
      campo.addEventListener(ev, () => {
        const o = caretOffset(campo);
        if (o >= 0) el._ultimoOff = o;
      }));

    el.append(cab, campo);
    return el;
  }

  function renderBlocos(lista) {
    painelCorr.querySelectorAll('.edit-turno').forEach(e => e.remove());
    const frag = document.createDocumentFragment();
    lista.forEach(b => frag.appendChild(criarBloco(b)));
    painelCorr.appendChild(frag);
    atualizarEstadoBotoes();
  }

  function blocos() { return Array.prototype.slice.call(painelCorr.querySelectorAll('.edit-turno')); }

  function atualizarEstadoBotoes() {
    blocos().forEach((el, i) => {
      const b = el.querySelector('.b-juntar');
      if (b) b.disabled = (i === 0);
    });
  }

  // ---- Separar: quebra o bloco no ponto do cursor -----------------------
  // O instante do corte vem das PALAVRAS alinhadas (fiel ao áudio) sempre que
  // existirem; sem alinhamento por palavra, é interpolado pelo texto e o bloco
  // fica marcado como tempo estimado — a diferença é registrada no relatório.
  function ancoras(el) {
    const off0 = parseInt(el.dataset.off0, 10) || 0;
    const lista = [];
    let pos = -off0;
    origemDe(el).forEach(si => {
      (PALAVRAS[si] || []).forEach(p => {
        if (pos >= 0) lista.push({ pos: pos, t: p[0] });
        pos += String(p[1]).length + 1;
      });
    });
    return lista;
  }

  function caretOffset(campo) {
    const sel = window.getSelection();
    if (!sel || !sel.rangeCount) return -1;
    const r = sel.getRangeAt(0);
    if (!campo.contains(r.startContainer)) return -1;
    const pre = r.cloneRange();
    pre.selectNodeContents(campo);
    pre.setEnd(r.startContainer, r.startOffset);
    return pre.toString().length;
  }

  function tempoDoCorte(el, off, texto) {
    const ini = parseFloat(el.dataset.start) || 0;
    const fim = parseFloat(el.dataset.end) || ini;
    const anc = ancoras(el);
    if (anc.length) {
      let melhor = anc[0];
      for (const a of anc) if (Math.abs(a.pos - off) < Math.abs(melhor.pos - off)) melhor = a;
      if (melhor.t > ini && melhor.t < fim) return { t: melhor.t, estimado: false };
    }
    const frac = texto.length ? Math.min(1, Math.max(0, off / texto.length)) : 0.5;
    return { t: Math.round((ini + (fim - ini) * frac) * 1000) / 1000, estimado: true };
  }

  function separar(el) {
    const campo = el.querySelector('.edit-texto');
    const texto = campo.innerText;
    let off = caretOffset(campo);
    if (off < 0 && el._ultimoOff != null) off = Math.min(el._ultimoOff, texto.length);
    if (off < 0) {
      anunciar('Clique no texto, no ponto exato em que a outra pessoa começa a falar, e então use “separar”.');
      campo.focus();
      return;
    }
    const antes = texto.slice(0, off).trim();
    const depois = texto.slice(off).trim();
    if (!antes || !depois) {
      anunciar('Posicione o cursor no MEIO do trecho: separar precisa deixar texto dos dois lados.');
      return;
    }
    guardarPasso();
    const corte = tempoDoCorte(el, off, texto);
    const fimAntigo = parseFloat(el.dataset.end) || corte.t;
    campo.textContent = antes;
    el._ultimoOff = null;            // o texto encurtou: a posição velha não vale mais
    el.dataset.end = corte.t;

    const novo = criarBloco({
      origem: origemDe(el),
      parte: (parseInt(el.dataset.parte, 10) || 0) + 1,
      off0: (parseInt(el.dataset.off0, 10) || 0) + off,
      speaker: el.dataset.speaker,
      start: corte.t, end: fimAntigo, texto: depois,
      estimado: corte.estimado,
    });
    el.after(novo);
    atualizarEstadoBotoes();
    anunciar('Separado em ' + fmtHMS(corte.t) + (corte.estimado ? ' (tempo estimado)' : '') +
             ' — agora escolha o interlocutor do trecho de baixo.');
    const sel = novo.querySelector('.seg-spk');
    if (sel) { novo.scrollIntoView({ block: 'nearest' }); sel.focus(); }
    salvarRascunho();
  }

  // ---- Juntar: aglutina o bloco ao anterior -----------------------------
  function juntar(el) {
    const ant = el.previousElementSibling;
    if (!ant || !ant.classList.contains('edit-turno')) return;
    guardarPasso();
    const ca = ant.querySelector('.edit-texto'), cb = el.querySelector('.edit-texto');
    const trocou = (ant.dataset.speaker || '') !== (el.dataset.speaker || '');
    ca.textContent = (ca.innerText.trim() + ' ' + cb.innerText.trim()).trim();
    ant.dataset.end = el.dataset.end;
    const uniao = origemDe(ant).slice();
    origemDe(el).forEach(i => { if (uniao.indexOf(i) < 0) uniao.push(i); });
    uniao.sort((a, b) => a - b);
    ant.dataset.origem = uniao.join(',');
    el.remove();
    atualizarEstadoBotoes();
    anunciar(trocou ? 'Trechos aglutinados em ' + nomeDe(ant.dataset.speaker) + '.'
                    : 'Trechos aglutinados.');
    salvarRascunho();
  }

  // =====================================================================
  // DESFAZER (pilha de passos estruturais)
  // =====================================================================
  const pilha = [];
  const btnDesfazer = document.getElementById('desfazer');

  function lerEstado() {
    return {
      blocos: blocos().map(el => ({
        origem: origemDe(el),
        parte: parseInt(el.dataset.parte, 10) || 0,
        off0: parseInt(el.dataset.off0, 10) || 0,
        speaker: el.dataset.speaker || '',
        start: parseFloat(el.dataset.start) || 0,
        end: parseFloat(el.dataset.end) || 0,
        estimado: el.dataset.estimado === '1',
        texto: el.querySelector('.edit-texto').innerText.trim(),
      })),
      locutores: locutores.map(l => ({ id: l.id, nome: l.nome, novo: !!l.novo })),
      merges: Object.assign({}, merges),
      conferencista: window.__CONFERENCISTA__ || '',
    };
  }

  function aplicarEstado(st) {
    if (!st) return;
    if (st.locutores) locutores = st.locutores.map(l => ({ id: l.id, nome: l.nome || '', novo: !!l.novo }));
    merges = Object.assign({}, st.merges || {});
    renderLocutores();
    renderBlocos(st.blocos || []);
    aplicarNomes();
  }

  function guardarPasso() {
    pilha.push(JSON.stringify(lerEstado()));
    if (pilha.length > 60) pilha.shift();
    if (btnDesfazer) btnDesfazer.disabled = false;
  }

  if (btnDesfazer) btnDesfazer.addEventListener('click', () => {
    const st = pilha.pop();
    if (!st) return;
    aplicarEstado(JSON.parse(st));
    btnDesfazer.disabled = !pilha.length;
    anunciar('Última alteração de interlocutor desfeita.');
    salvarRascunho();
  });

  let avisoTimer;
  function anunciar(msg) {
    if (!avisoEdicao) return;
    avisoEdicao.textContent = msg;
    clearTimeout(avisoTimer);
    avisoTimer = setTimeout(() => { avisoEdicao.textContent = ''; }, 6000);
  }

  // =====================================================================
  // Sincronia com o áudio
  // =====================================================================
  function indiceEm(t) {
    let lo = 0, hi = inicios.length - 1, ans = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1;
      if (inicios[m] <= t) { ans = m; lo = m + 1; } else { hi = m - 1; } }
    return ans;
  }

  let atual = -1, blocoAtivo = null;
  audio.addEventListener('timeupdate', () => {
    const t = audio.currentTime;
    const i = indiceEm(t);
    if (i !== atual) {
      if (atual >= 0 && palavras[atual]) palavras[atual].classList.remove('atual');
      atual = i;
      if (i >= 0 && palavras[i]) {
        const w = palavras[i];
        w.classList.add('atual');
        if (seguir.checked) {
          const r = w.getBoundingClientRect();
          const cont = document.getElementById('conferencia');
          const rc = cont.getBoundingClientRect();
          if (r.top < rc.top + 40 || r.bottom > rc.bottom - 10)
            w.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
      }
    }
    // O bloco ativo é achado pelo TEMPO, não pelo índice do segmento: depois de
    // separar/aglutinar, um segmento original pode virar vários blocos (ou vários
    // virarem um só), e só o tempo continua valendo.
    const b = blocoEm(t);
    if (b !== blocoAtivo) {
      if (blocoAtivo) blocoAtivo.classList.remove('ativo');
      blocoAtivo = b;
      if (b) {
        b.classList.add('ativo');
        if (seguir.checked) b.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  });

  function blocoEm(t) {
    let achado = null;
    for (const el of blocos()) {
      if ((parseFloat(el.dataset.start) || 0) <= t + 0.001) achado = el; else break;
    }
    return achado;
  }

  // --- Modal: nome do conferencista ---
  const modal = document.getElementById('modalConf');
  const inpConf = document.getElementById('inpConferencista');
  function iniciar() {
    window.__CONFERENCISTA__ = (inpConf.value || '').trim();
    modal.style.display = 'none';
    audio.focus && audio.focus();
  }
  document.getElementById('btnIniciar').addEventListener('click', iniciar);
  inpConf.addEventListener('keydown', e => { if (e.key === 'Enter') iniciar(); });
  setTimeout(() => inpConf.focus(), 50);

  // --- Controles de reprodução ---
  const velLabel = document.getElementById('velLabel');
  function setVel(v) {
    v = Math.min(3, Math.max(0.25, Math.round(v * 100) / 100));
    audio.playbackRate = v;
    velLabel.textContent = v.toFixed(2).replace(/\\.?0+$/, '') + '×';
  }
  function toggle() { audio.paused ? audio.play() : audio.pause(); }
  function pular(s) { audio.currentTime = Math.min(audio.duration || 1e9, Math.max(0, audio.currentTime + s)); }

  document.getElementById('play').addEventListener('click', toggle);
  document.getElementById('volta').addEventListener('click', () => pular(-10));
  document.getElementById('avanca').addEventListener('click', () => pular(10));

  // Teclado (ignora quando o foco está no editor/inputs):
  function editando(el) {
    return el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
  }
  document.addEventListener('keydown', e => {
    if (modal.style.display !== 'none') return;      // modal aberto
    // Separar funciona COM o cursor no texto — é o único atalho que precisa do
    // foco dentro do editor, então vem antes da guarda de digitação.
    if (e.key === 'Enter' && e.shiftKey && e.target && e.target.classList &&
        e.target.classList.contains('edit-texto')) {
      e.preventDefault();
      separar(e.target.closest('.edit-turno'));
      return;
    }
    if (editando(e.target)) return;                  // digitando correção/nome
    if (e.key === ' ') { e.preventDefault(); toggle(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); pular(-10); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); pular(10); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setVel(audio.playbackRate + 0.25); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); setVel(audio.playbackRate - 0.25); }
  });

  // =====================================================================
  // Salvar
  // =====================================================================
  function coletarCorrecao() {
    const st = lerEstado();
    const segmentos = st.blocos.map(b => {
      const e = {
        seg: b.origem.length ? b.origem[0] : null,
        origem: b.origem,
        parte: b.parte,
        speaker: resolver(b.speaker) || null,
        start: b.start, end: b.end,
        texto: b.texto,
      };
      if (b.estimado) e.tempo_estimado = true;
      return e;
    });
    const nomes = {}, novos = {};
    locutores.forEach(l => {
      if (merges[l.id]) return;
      const n = l.nome.trim();
      if (n) nomes[l.id] = n;
      if (l.novo) novos[l.id] = n || l.id;
    });
    return {
      schema: 'degravador-correcao/1.1', arquivo: window.__ARQUIVO__,
      conferencista: window.__CONFERENCISTA__ || '',
      segmentos, locutores: nomes, novos_locutores: novos, merges: merges,
    };
  }

  document.getElementById('salvar').addEventListener('click', async () => {
    const dados = coletarCorrecao();
    if (window.pywebview && window.pywebview.api && window.pywebview.api.salvar_correcao) {
      try { const r = await window.pywebview.api.salvar_correcao(dados);
        salvo.textContent = '✓ salvo: ' + (r || 'ok'); }
      catch (e) { salvo.textContent = 'erro ao salvar: ' + e; }
    } else {
      const blob = new Blob([JSON.stringify(dados, null, 2)], { type:'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (window.__BASE__ || 'degravacao') + '.correcao.json';
      a.click();
      salvo.innerHTML = 'Cópia portátil: baixamos os <b>dados</b> da correção (' + a.download +
        '). Para gerar o <b>PDF corrigido</b>, abra esta conferência pelo aplicativo VOX.';
    }
  });

  // =====================================================================
  // Busca (Ctrl+F)
  // =====================================================================
  const busca = document.getElementById('busca');
  const buscaInfo = document.getElementById('buscaInfo');
  let hits = [], hitIdx = -1;
  function limparBusca() { hits.forEach(w => w.classList.remove('busca-hit', 'busca-atual')); hits = []; hitIdx = -1; }
  function fazerBusca() {
    limparBusca();
    const q = busca.value.trim().toLowerCase();
    if (q.length < 2) { buscaInfo.textContent = ''; return; }
    palavras.forEach(w => { if ((w.textContent || '').toLowerCase().includes(q)) { w.classList.add('busca-hit'); hits.push(w); } });
    if (hits.length) irHit(0); else buscaInfo.textContent = 'nada encontrado';
  }
  function irHit(i) {
    if (!hits.length) return;
    hits.forEach(w => w.classList.remove('busca-atual'));
    hitIdx = (i + hits.length) % hits.length;
    hits[hitIdx].classList.add('busca-atual');
    hits[hitIdx].scrollIntoView({ block: 'center', behavior: 'smooth' });
    buscaInfo.textContent = (hitIdx + 1) + ' / ' + hits.length;
  }
  let buscaTimer;
  busca.addEventListener('input', () => { clearTimeout(buscaTimer); buscaTimer = setTimeout(fazerBusca, 250); });
  busca.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); irHit(hitIdx + (e.shiftKey ? -1 : 1)); } });
  document.getElementById('buscaPrev').addEventListener('click', () => irHit(hitIdx - 1));
  document.getElementById('buscaNext').addEventListener('click', () => irHit(hitIdx + 1));
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) { e.preventDefault(); busca.focus(); busca.select(); }
  });

  // =====================================================================
  // Rascunho automático
  // =====================================================================
  const CHAVE = 'vox-rascunho:' + (window.__ARQUIVO__ || 'degravacao');
  const rascunhoAviso = document.getElementById('rascunhoAviso');
  const estadoInicial = JSON.stringify({
    blocos: (window.__BLOCOS__ || []),
    locutores: locutores.map(l => ({ id: l.id, nome: l.nome, novo: false })),
    merges: {}, conferencista: '',
  });

  let saveTimer;
  function salvarRascunho() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      try {
        localStorage.setItem(CHAVE, JSON.stringify(lerEstado()));
        rascunhoAviso.textContent = 'rascunho salvo';
        setTimeout(() => { if (rascunhoAviso.textContent === 'rascunho salvo') rascunhoAviso.textContent = ''; }, 1500);
      } catch (e) {}
    }, 500);
  }

  function restaurarRascunho() {
    let d; try { d = JSON.parse(localStorage.getItem(CHAVE) || 'null'); } catch (e) { d = null; }
    // Rascunho do formato antigo (texto por índice de segmento): aproveitamos o
    // texto, que é o trabalho humano; a estrutura recomeça da transcrição.
    if (d && !d.blocos && d.segs) {
      const base = JSON.parse(estadoInicial);
      base.blocos.forEach(b => {
        const k = b.origem && b.origem.length ? b.origem[0] : null;
        if (k != null && d.segs[k] !== undefined) b.texto = d.segs[k];
      });
      if (d.nomes) base.locutores.forEach(l => { if (d.nomes[l.id] !== undefined) l.nome = d.nomes[l.id]; });
      base.merges = d.merges || {};
      base.conferencista = d.conferencista || '';
      d = base;
    }
    if (!d || !d.blocos) return;
    aplicarEstado(d);
    if (d.conferencista && inpConf && !inpConf.value) inpConf.value = d.conferencista;
    rascunhoAviso.innerHTML = 'rascunho restaurado <button id="descartarR" type="button">descartar</button>';
    const bd = document.getElementById('descartarR');
    if (bd) bd.addEventListener('click', () => {
      try { localStorage.removeItem(CHAVE); } catch (e) {}
      pilha.length = 0;
      if (btnDesfazer) btnDesfazer.disabled = true;
      aplicarEstado(JSON.parse(estadoInicial));
      rascunhoAviso.textContent = '(rascunho descartado)';
    });
  }

  // ---- Partida ----
  renderLocutores();
  renderBlocos(window.__BLOCOS__ || []);
  aplicarNomes();
  restaurarRascunho();
})();
</script>
"""


def _esc(t: str) -> str:
    return _html.escape(t or "", quote=True)


def _tem_multiplos_locutores(doc: dict) -> bool:
    speakers = {s.get("speaker") for s in doc.get("segments", [])}
    speakers.discard(None)
    return len(speakers) > 1


def exportar(
    doc: dict,
    caminho: str | Path,
    *,
    mapa_locutores: dict | None = None,
    audio_src: str | None = None,
    **_opts,
) -> Path:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    meta = doc.get("metadata", {})
    if audio_src is None:
        audio_src = meta.get("audio_arquivo") or ""

    identificar = _tem_multiplos_locutores(doc)
    conf: list[str] = []

    # Locutores distintos, na ordem de aparição (para o painel de nomear).
    locutores_ordem: list[str] = []
    for s in doc.get("segments", []):
        spk = s.get("speaker")
        if spk and spk not in locutores_ordem:
            locutores_ordem.append(spk)

    def _nome_disp(spk):
        # Começa no rótulo técnico; nome real só se o usuário já tiver atribuído.
        return _esc(rotulo_locutor(spk, mapa_locutores) or spk or "")

    # Índice global de cada segmento (liga palavra da conferência ↔ bloco de correção).
    seg_idx = {id(s): i for i, s in enumerate(doc.get("segments", []))}

    # --- painel de CONFERÊNCIA: agrupado por turno (leitura fluida) ---
    for turno in iter_turnos(doc):
        conf.append('<div class="turno">')
        if identificar:
            spk = turno["speaker"] or ""
            conf.append(
                f'<span class="locutor" data-speaker="{_esc(spk)}" data-seek="{turno["start"]:.3f}">'
                f'<span class="nome-loc">{_nome_disp(spk)}</span> '
                f'<span class="ts">({fmt_hms(turno["start"])})</span></span> '
            )
        for seg in turno["segmentos"]:
            si = seg_idx[id(seg)]
            flags = set(seg.get("flags", []))
            if "inaudivel" in flags:
                conf.append(
                    f'<span class="marca" data-seek="{seg.get("start", 0.0):.3f}" '
                    f'data-seg="{si}">[inaudível – {fmt_hms(seg.get("start", 0.0))}]</span> '
                )
                continue
            palavras = seg.get("words") or []
            if not palavras:
                # Sem alinhamento por palavra (idioma sem modelo wav2vec2): o
                # segmento inteiro vira uma unidade clicável. Sem isto o painel
                # de leitura ficaria VAZIO — o texto só apareceria na correção.
                texto_seg = _esc(texto_segmento(seg))
                if texto_seg:
                    s_ini = seg.get("start")
                    s_fim = seg.get("end")
                    classe = "w baixa" if "baixa_confianca" in flags else "w"
                    if s_ini is not None:
                        conf.append(
                            f'<span class="{classe}" data-start="{float(s_ini):.3f}" '
                            f'data-end="{float(s_fim if s_fim is not None else s_ini):.3f}" '
                            f'data-seek="{float(s_ini):.3f}" data-seg="{si}">{texto_seg}</span> '
                        )
                    else:
                        conf.append(f'<span class="{classe}" data-seg="{si}">{texto_seg}</span> ')
                if "vozes_sobrepostas" in flags:
                    conf.append('<span class="marca">[vozes sobrepostas]</span> ')
                continue
            for w in palavras:
                texto = _esc((w.get("word") or "").strip())
                if not texto:
                    continue
                ini, fim = w.get("start"), w.get("end")
                classe = "w baixa" if "baixa_confianca" in set(w.get("flags", [])) else "w"
                if ini is not None:
                    conf.append(
                        f'<span class="{classe}" data-start="{float(ini):.3f}" '
                        f'data-end="{float(fim if fim is not None else ini):.3f}" '
                        f'data-seek="{float(ini):.3f}" data-seg="{si}">{texto}</span> '
                    )
                else:
                    conf.append(f'<span class="{classe}">{texto}</span> ')
            if "vozes_sobrepostas" in flags:
                conf.append('<span class="marca">[vozes sobrepostas]</span> ')
        conf.append("</div>")

    # --- painel de CORREÇÃO: montado pelo JS a partir destes blocos ---
    # Um bloco por segmento na carga; separar/aglutinar reescrevem a lista sem
    # nunca perder 'origem', que é o vínculo com a transcrição probatória.
    blocos = []
    palavras_por_seg: dict[int, list] = {}
    for si, seg in enumerate(doc.get("segments", [])):
        ini = float(seg.get("start") or 0.0)
        fim = seg.get("end")
        blocos.append({
            "origem": [si],
            "parte": 0,
            "off0": 0,
            "speaker": seg.get("speaker") or "",
            "start": round(ini, 3),
            "end": round(float(fim if fim is not None else ini), 3),
            "texto": texto_segmento(seg),
        })
        marcas = [
            [round(float(w["start"]), 3), (w.get("word") or "").strip()]
            for w in (seg.get("words") or [])
            if w.get("start") is not None and (w.get("word") or "").strip()
        ]
        if marcas:
            palavras_por_seg[si] = marcas

    locutores_js = [
        {"id": spk,
         "nome": (rotulo_locutor(spk, mapa_locutores) or "") if
                 (rotulo_locutor(spk, mapa_locutores) or spk) != spk else ""}
        for spk in locutores_ordem
    ]

    titulo = _esc(meta.get("arquivo") or "Degravação")
    base_nome = Path(meta.get("arquivo") or "degravacao").stem
    _a = audio_src or ""
    # Aceita URI absoluto (file://…, já codificado) ou nome relativo (a codificar).
    audio_url = _esc(_a if _a.startswith(("file:", "http:", "https:")) else _url_quote(_a))
    logo_uri = branding.logo_data_uri()
    # O subtítulo institucional é opcional: vazio, o <span> nem é emitido.
    sub_conf = (
        f'<span class="sub">{_esc(branding.SUBTITULO)}</span>'
        if branding.SUBTITULO else ""
    )
    marca_conf = (
        f'<div class="marca-conf"><img src="{logo_uri}" alt="VOX">'
        f'<span class="nome">{branding.NOME}</span>{sub_conf}</div>'
    ) if logo_uri else (
        f'<div class="marca-conf"><span class="nome">{branding.NOME}</span>{sub_conf}</div>'
    )

    # Sem alinhamento por palavra não existe realce palavra a palavra: o
    # conferente precisa saber que a ausência de marcas é medição não feita, e
    # não transcrição limpa.
    params_meta = meta.get("params") or {}
    aviso_alinhamento = ""
    if params_meta.get("alinhamento_por_palavra") is False:
        idioma_txt = rotulo_idioma(params_meta) or "este idioma"
        aviso_alinhamento = (
            '<div class="aviso-alinhamento">⚠ Sem <b>alinhamento por palavra</b> '
            f'para {_esc(idioma_txt)}: o áudio acompanha por <b>trecho de fala</b>, '
            'não palavra a palavra, e não há realce de baixa confiança por palavra. '
            '<b>A ausência de realces aqui não significa transcrição conferida</b> — '
            'significa que essa medição não foi feita. Confira ouvindo o áudio inteiro.</div>'
        )

    # O painel de interlocutores aparece SEMPRE: quando a diarização junta duas
    # pessoas num rótulo só (ou não roda), criar e atribuir vozes é justamente o
    # conserto que o conferente precisa fazer.
    ren_bloco = (
        '<details class="ren-painel" open><summary>Interlocutores — nomear, criar e mesclar'
        ' (o sistema só separa as vozes; a atribuição final é sua)</summary>'
        '<div class="ren-grade" id="renGrade"></div>'
        '<div style="margin-top:8px">'
        '<button type="button" id="btnNovoLoc" title="Para uma voz que a máquina não separou">'
        '✚ Novo interlocutor</button></div></details>'
    )

    doc_html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conferência — {titulo}</title>
<style>{_CSS}
</head>
<body>
<div id="modalConf" class="modal-conf">
  <div class="modal-cartao">
    <div class="mt">Conferência — {branding.NOME}</div>
    <p>Informe o responsável pela conferência (conferencista). O nome constará no
       PDF corrigido (pós-conferência).</p>
    <input type="text" id="inpConferencista" placeholder="Seu nome completo">
    <button id="btnIniciar" type="button">Iniciar conferência</button>
  </div>
</div>
<header>
  {marca_conf}
  <h1>Conferência &amp; correção — {titulo}</h1>
  <div id="avisoPortatil" class="aviso-portatil">📄 Esta é uma <b>cópia portátil</b> (para ouvir e ler em qualquer computador). Para <b>gerar o PDF corrigido</b>, abra esta conferência pelo aplicativo <b>VOX</b> (botão “Conferir e corrigir”).</div>
  {aviso_alinhamento}
  <audio id="audio" controls preload="metadata" src="{audio_url}"></audio>
  <div class="barra">
    <button id="play" type="button">▶ / ⏸ <small>espaço</small></button>
    <button id="volta" type="button">⏪ 10s <small>←</small></button>
    <button id="avanca" type="button">10s ⏩ <small>→</small></button>
    <span class="vel">Velocidade <b id="velLabel">1.0×</b> <small>↑/↓</small></span>
    <button id="salvar" type="button" class="primario">Salvar correção</button>
    <button id="desfazer" type="button" disabled title="Desfaz a última separação, aglutinação ou troca de interlocutor">↶ desfazer</button>
    <label><input type="checkbox" id="seguir" checked> seguir o áudio</label>
    <span class="amostra" style="background:var(--baixa)"></span> baixa confiança
    <span class="amostra" style="background:var(--atual)"></span> palavra atual
    <span id="salvo"></span>
  </div>
  <div class="barra2">
    <input id="busca" type="text" placeholder="Buscar no texto…  (Ctrl+F)">
    <button id="buscaPrev" type="button" title="anterior">↑</button>
    <button id="buscaNext" type="button" title="próxima">↓</button>
    <span id="buscaInfo"></span>
    <span id="rascunhoAviso"></span>
    <span id="avisoEdicao"></span>
  </div>
  {ren_bloco}
</header>
<main>
  <section id="conferencia" class="painel">
    <p class="painel-titulo">Conferência (original — não editável)
      <span class="dica-painel">preserva a transcrição e a atribuição de vozes como a máquina entregou</span></p>
    {''.join(conf)}
  </section>
  <section id="correcao" class="painel">
    <p class="painel-titulo">Correção (edite aqui enquanto ouve)
      <span class="dica-painel">✂ separar divide a fala no cursor (Shift+Enter) · ⬆ juntar aglutina ao bloco de cima · a caixa de nome reatribui o trecho</span></p>
  </section>
</main>
<script type="application/json" id="vox-dados">{json.dumps(doc, ensure_ascii=False)}</script>
<script>
window.__ARQUIVO__ = {json.dumps(meta.get('arquivo') or '')};
window.__BASE__ = {json.dumps(base_nome)};
window.__BLOCOS__ = {json.dumps(blocos, ensure_ascii=False)};
window.__LOCUTORES__ = {json.dumps(locutores_js, ensure_ascii=False)};
window.__PALAVRAS__ = {json.dumps(palavras_por_seg, ensure_ascii=False)};
</script>
{_JS}
</body>
</html>
"""
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(doc_html)
    return caminho
