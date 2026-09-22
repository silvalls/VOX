# VOX

**Degravação local, fiel e auditável de áudios e vídeos** — com identificação de
quem falou o quê e quando, timestamps por palavra e um espaço de conferência
humana para revisar tudo ouvindo o áudio.

Versão **1.1** · Windows · Python 3.10–3.12 · GPL-3.0

> O **produto** se chama VOX. O **pacote Python** continua se chamando
> `degravador` — é o nome interno do projeto e não muda por compatibilidade.

---

## Os três compromissos

| | |
|---|---|
| **Fidelidade** | Pipeline **não-generativo**. Nenhuma IA "melhora", resume ou reescreve a fala. Correções são **determinísticas** (glossário) ou **humanas** (conferência). |
| **Privacidade** | Todo o processamento acontece na máquina. Depois de instalado, funciona **100% offline** — nada de áudio ou texto sai dali. |
| **Auditabilidade** | O **JSON bruto** (palavras, timestamps, scores de confiança, SHA-256 do original) é a fonte de verdade. Todos os outros formatos derivam dele, e o original nunca é sobrescrito. |

O alvo é **português do Brasil**, mas a fala pode estar em outro idioma. Os
documentos gerados saem sempre em português: **não há tradução em ponto algum do
pipeline**.

---

## O que ele faz

- **Transcreve** com Whisper `large-v3` / `large-v3-turbo` (via WhisperX +
  faster-whisper), com VAD contra alucinação.
- **Alinha palavra a palavra** (wav2vec2), dando timestamps e score de confiança
  por palavra — é o que faz o player de conferência funcionar.
- **Separa as vozes** (diarização com pyannote `speaker-diarization-community-1`;
  fallback SpeechBrain ECAPA sem token).
- **Marca o que é incerto**: `[inaudível]`, `[vozes sobrepostas]` e realce visual
  dos trechos de baixa confiança — a conferência humana vai direto ao ponto.
- **Conferência e correção** em dois painéis sincronizados pelo áudio.
- **Documenta**: PDF oficial (ABNT + Manual de Redação), PDF corrigido
  pós-conferência e um **relatório comparativo** do que a pessoa alterou.

### Conferência: a máquina separa, o humano decide

O painel de cima é **a prova** — a transcrição e a divisão de vozes exatamente
como saíram da máquina, não editáveis. O de baixo é onde se corrige, ouvindo:

- **texto**, segmento a segmento, com rascunho salvo automaticamente;
- **quem falou o quê** — a diarização erra nos dois sentidos, e os dois se
  consertam:
  - **separar** um trecho no ponto do cursor, quando duas pessoas caíram no mesmo
    rótulo (o instante do corte vem da *palavra alinhada*; sem alinhamento, o
    trecho é marcado como *tempo estimado*);
  - **juntar (aglutinar)** trechos vizinhos, inclusive de segmentos diferentes,
    quando a fala de uma pessoa só foi picotada;
  - **reatribuir** um trecho, **criar** um interlocutor que a máquina não separou,
    **mesclar** dois rótulos que são a mesma pessoa, e **desfazer** qualquer passo.

Nada disso é silencioso: cada separação, aglutinação, reatribuição, mesclagem e
interlocutor criado sai **listado no relatório de conferência**. E o sistema
**nunca inventa nomes** — usa rótulos técnicos (`SPEAKER_00`…) até que uma pessoa
atribua os nomes reais.

### Diagnóstico da placa de vídeo

Na abertura, o VOX confere a GPU e o driver NVIDIA instalados e mostra uma faixa:
apta (verde), há driver mais novo (amarela), driver antigo demais — o trabalho
vai cair na CPU (vermelha), ou sem GPU NVIDIA (cinza).

O veredito é **offline**, comparando com o mínimo publicado pela NVIDIA, para
funcionar em rede isolada. Se houver internet, consulta também o catálogo público
(GeForce, RTX/Quadro ou Data Center, conforme a placa) — e qualquer falha vira
"não sei", nunca um alarme falso. Desligue com `VOX_SEM_CHECAGEM_ONLINE=1`.

---

## Requisitos

- **Python 3.10–3.12**
- **ffmpeg** no PATH (inclui o `ffprobe`)
- **GPU NVIDIA** com 4 GB de VRAM ou mais — *recomendado, não obrigatório*. Sem
  ela o VOX roda na CPU: o resultado é o mesmo, só demora bem mais.
- **Token do Hugging Face** (gratuito) apenas para baixar os modelos de diarização
  **uma vez**. Depois disso, nunca mais.

```powershell
winget install Gyan.FFmpeg     # Windows
```
```bash
sudo apt install ffmpeg        # Linux
brew install ffmpeg            # macOS
```

---

## Instalação (desenvolvimento)

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # Linux/macOS

pip install -r requirements.txt
pip install -e .               # expõe os comandos `degravador` e `degravador-app`
```

### PyTorch com CUDA — por último, sempre

A **versão** do PyTorch está fixada no `requirements.txt` (auditabilidade), mas o
**build** — cu128, cu121 ou CPU — depende da sua GPU.

> ⚠️ **A ordem importa.** O `pyannote` puxa `torchvision` do PyPI, que no Windows
> é **CPU-only** e sobrescreve um torch de GPU instalado antes. Instale o trio do
> índice CUDA **depois** do `requirements`, com versões fixas, para que ele ganhe
> a resolução:

| Hardware | Comando |
|---|---|
| **NVIDIA Blackwell (RTX 50xx)** | `pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128` |
| NVIDIA anterior (alvo 4 GB) | `pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu121` |
| Sem GPU | nada a fazer — o `requirements` já instala o torch de CPU |

Blackwell (`sm_120`) **exige** wheels CUDA 12.8+; versões antigas falham com
*"no kernel image is available for execution"*.

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
# esperado:  True 12.8
```

### Token do Hugging Face (só para o primeiro download)

1. Crie uma conta em <https://huggingface.co>.
2. Aceite os termos de [`pyannote/segmentation-3.0`](https://huggingface.co/pyannote/segmentation-3.0)
   e [`pyannote/speaker-diarization-community-1`](https://huggingface.co/pyannote/speaker-diarization-community-1).
3. Gere um token em *Settings → Access Tokens*.
4. `cp .env.example .env` e cole o token em `HF_TOKEN`.

Os modelos são baixados sob demanda no primeiro uso e ficam em cache. Depois,
tudo roda offline.

---

## Uso

### Aplicativo

```bash
python -m degravador.app
```

Escolher arquivo → transcrever (com progresso e cancelamento) → conferir,
corrigir e atribuir vozes → exportar.

### Linha de comando

```bash
# Básico — detecta o hardware, transcreve e diariza
degravador audiencia.mp4

# Força o perfil de produção 4 GB mesmo numa GPU grande (para validar)
degravador arquivo.mp4 --perfil recomendado

# Fixa o nº de interlocutores (melhora a diarização)
degravador reuniao.mkv --num-speakers 3

# Escolhe formatos de saída
degravador entrevista.mp3 --formatos json,txt,srt,pdf,html

# Nomeia os locutores, na ordem em que aparecem
degravador audiencia.mp4 --formatos pdf --locutores "Juiz,Testemunha,Promotor"

# Glossário determinístico (correção exata, sem IA)
degravador oitiva.mp4 --glossario termos.csv

# Fala em outro idioma (qualquer código ISO; padrão: pt)
degravador entrevista.mp4 --idioma es
degravador material.mp4 --idioma auto     # deixa o Whisper detectar

# Re-exporta a partir do JSON, SEM reprocessar o áudio
degravador --reexportar audiencia.json --formatos pdf,html

# Aplica uma correção humana feita na conferência
degravador --reexportar audiencia.json --corrigir audiencia.correcao.json --formatos pdf
```

Sem instalar o pacote: `python -m degravador.cli ...`

### Perfis de hardware (automáticos)

| Perfil | Hardware | Modelo | Quantização |
|---|---|---|---|
| `maximo` | GPU ≥ 10 GB | `large-v3` | `float16` |
| `recomendado` | GPU 4–8 GB (**alvo**) | `large-v3-turbo` | `int8_float16` |
| `cpu` | Sem GPU | `large-v3-turbo` | `int8` |

No perfil de 4 GB a diarização é **sequencial**: o modelo de transcrição é
descarregado da VRAM antes, para os dois não disputarem memória.

---

## Formatos de saída

| Formato | Para quê |
|---|---|
| `json` | **Fonte de verdade** — texto bruto, timestamps por palavra, scores, metadados e SHA-256 |
| `pdf` | Documento oficial (ABNT + Manual de Redação): Arial 12, justificado, A4, margens 3/3/2/2 cm |
| `docx` | O mesmo documento, editável |
| `html` | **Conferência**: player offline, clique na palavra para ouvir, correção de texto e de interlocutores |
| `txt` | Texto corrido com locutores e timestamps |
| `srt` / `vtt` | Legendas com identificação de locutor |

---

## Idiomas

Suportar um idioma significa coisas diferentes em cada camada:

| Camada | Cobertura | Se faltar |
|---|---|---|
| Transcrição (Whisper) | **99 idiomas** | não transcreve |
| Alinhamento por palavra (wav2vec2) | **41 idiomas** | sem timestamps/scores **por palavra** |
| Bundle do instalador offline | **6**: pt, es, en, fr, de, it | idem, numa máquina sem internet |

A CLI aceita qualquer código ISO; a interface oferece os 6 embutidos mais
"detectar automaticamente", porque numa máquina instalada não há download.

Sem alinhamento por palavra a degravação **sai assim mesmo** — com timestamps por
trecho — e o PDF, o DOCX e a conferência **dizem isso explicitamente**. A
distinção importa: sem essa marcação, a ausência de realces de baixa confiança se
leria como "transcrição limpa" quando na verdade é "não foi medida".

---

## Estrutura

```
degravador/
├── config.py        perfis de fidelidade, parâmetros, limiares
├── perfis.py        detecção de GPU/VRAM → perfil
├── gpu_driver.py    diagnóstico do driver NVIDIA/CUDA
├── extracao.py      ffmpeg: extração, loudnorm, WAV 16k, SHA-256
├── transcricao.py   WhisperX: modelo + VAD + alinhamento wav2vec2
├── diarizacao.py    pyannote (padrão) ou speechbrain (sem token)
├── fidelidade.py    marcações de baixa confiança / inaudível / sobreposição
├── glossario.py     substituições determinísticas
├── vocabulario.py   viés de reconhecimento (initial_prompt)
├── correcao.py      aplica a correção humana (texto + atribuição de fala)
├── relatorio.py     comparativo original × corrigido
├── pipeline.py      pipeline reutilizável, com progresso
├── cli.py           linha de comando
├── app.py           aplicativo desktop (pywebview)
├── webui/           tela inicial do app
├── saidas/          exportadores (json, txt, srt, vtt, docx, pdf, html)
└── _offline.py      modo offline / modelos embutidos
empacotar/           PyInstaller + Inno Setup (instalador offline)
estilos/             estilo do documento oficial
tests/               testes (pytest), sem modelos pesados
```

---

## Instalador offline

`empacotar/` monta um instalador de dois cliques que roda em máquinas **sem
Python, sem internet e sem token** — modelos e ffmpeg vão embutidos (~6,9 GB).
O passo a passo do build está em [`empacotar/README.md`](empacotar/README.md).

---

## Testes

```bash
pip install -e ".[dev]"
pytest -q
```

Cobrem marcações de fidelidade, round-trip do JSON, todos os exportadores,
glossário, correção humana, **edição de interlocutores** e **diagnóstico de
driver** — tudo sem baixar modelos pesados.

O JavaScript da conferência não é coberto pelo pytest. Para exercitá-lo num DOM
real (separar, juntar, criar, mesclar, desfazer, rascunho), gere uma conferência
com `saidas/html.py` e carregue-a sob `jsdom`, suprindo `innerText`,
`scrollIntoView` e `HTMLMediaElement.play`, que o jsdom não implementa.

---

## Histórico de versões

[`empacotar/Novidades do VOX.txt`](empacotar/Novidades%20do%20VOX.txt) — o que
mudou em cada versão, em linguagem de usuário final.

---

## Licença

**GNU General Public License v3.0** — veja [`LICENSE`](LICENSE).

A GPL-3.0 é **copyleft**: você pode usar, estudar, modificar e redistribuir o
VOX, mas qualquer trabalho derivado que for distribuído precisa ser liberado sob
a mesma licença, com o código-fonte disponível.

Os modelos usados (Whisper, wav2vec2, pyannote, SpeechBrain) têm licenças
próprias, distintas desta — verifique-as antes de redistribuir um pacote com os
pesos embutidos.
