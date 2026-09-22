# Empacotamento do VOX — build e implantação

Gera o **instalador offline** do VOX (app + modelos + ffmpeg embutidos), que roda
em máquinas **sem Python, sem internet e sem token**.

## Estrutura

```
empacotar/
├── vox_main.py     # ponto de entrada do executável (GUI; --diag p/ teste)
├── vox.spec        # PyInstaller (congela o app + libs)
├── vox.iss         # Inno Setup (monta o instalador)
├── vox.ico         # ícone (gerado da logo)
├── gera_manual.py  # gera o "Manual do Usuario - VOX.pdf" (entregue ao lado do instalador)
├── Novidades do VOX.txt   # histórico de versões p/ o usuário (editar a cada release)
├── modelos/        # modelos embutidos (baixados 1x; ver abaixo)  [ignorado no git]
├── ffmpeg/         # ffmpeg.exe + ffprobe.exe                      [ignorado no git]
├── dist/VOX/       # saída do PyInstaller (app congelado)          [ignorado no git]
└── saida_instalador/  # instalador final                          [ignorado no git]
```

## Pré-requisitos (máquina de build)

- Ambiente do projeto instalado (venv com torch cu128 + requirements + speechbrain + pywebview).
- PyInstaller e fpdf2 (`pip install pyinstaller fpdf2`).
- ffmpeg no PATH (Gyan.FFmpeg) e **Inno Setup 6** (`ISCC.exe`).

## Passos

### 0. Subir a versão (três lugares)

A versão vive em **três** arquivos e eles precisam casar — até a 1.0 não casavam
(o instalador dizia `1.0` enquanto todo PDF gerado carimbava `Versão do VOX:
0.1.0`, porque só o `.iss` havia sido atualizado). Suba os três juntos:

| Arquivo | Campo | Onde aparece |
|---|---|---|
| `degravador/__init__.py` | `__version__` | **no rodapé de todo PDF** ("Versão do VOX") |
| `pyproject.toml` | `version` | metadados do pacote Python |
| `empacotar/vox.iss` | `MyAppVersion` | nome do instalador e Adicionar/Remover Programas |

Atualize também, para o usuário final:
- `empacotar/Novidades do VOX.txt` — o que mudou desta versão para a anterior;
- `empacotar/gera_manual.py` (a linha "Versão X.Y" da capa) e **rode-o** para
  regerar o `Manual do Usuario - VOX.pdf`.

### 1. Modelos embutidos (uma vez)

**a) Hugging Face** — copie do cache para `empacotar/modelos/huggingface/hub/`:
- `models--mobiuslabsgmbh--faster-whisper-large-v3-turbo` (transcrição, multilíngue)
- `models--jonatasgrosman--wav2vec2-large-xlsr-53-portuguese` (alinhamento **pt**)
- `models--pyannote--speaker-diarization-community-1` (diarização)
- `models--pyannote--segmentation-3.0`
- `models--speechbrain--spkrec-ecapa-voxceleb` (diarização sem-token / plano B)

> **Cuidado com snapshots duplicados.** O cache do HF pode guardar mais de uma
> revisão do mesmo modelo. O `wav2vec2-...-portuguese` chega com dois snapshots:
> o de `refs/main` (`config.json` + `pytorch_model.bin`) e um de `refs/pr/4` que
> só tem `model.safetensors` — 1,2 GB inúteis, porque sem `config.json` ele não
> carrega e nada aponta para ele. Mantenha **apenas** o snapshot que `refs/main`
> nomeia; confira com `type refs\main` e apague os demais de `snapshots/`.

**b) torchaudio** — modelos de alinhamento de es/en/fr/de/it. Ao contrário do pt,
não vêm do Hugging Face: são bundles do torchaudio (~360 MB cada), que o
`whisperx.load_align_model()` busca em `TORCH_HOME/hub/checkpoints`. Baixe-os
apontando o `TORCH_HOME` para o bundle:

```python
import os
os.environ["TORCH_HOME"] = r"empacotar\modelos\torch"
import torchaudio
for nome in ("WAV2VEC2_ASR_BASE_960H",        # en
             "VOXPOPULI_ASR_BASE_10K_ES",     # es
             "VOXPOPULI_ASR_BASE_10K_FR",     # fr
             "VOXPOPULI_ASR_BASE_10K_DE",     # de
             "VOXPOPULI_ASR_BASE_10K_IT"):    # it
    torchaudio.pipelines.__dict__[nome].get_model()
```

A lista de idiomas oferecidos na interface vive em `degravador/config.py`
(`IDIOMAS_INTERFACE`) e **tem de casar com o que está embutido aqui**: numa
máquina instalada o `HF_HUB_OFFLINE=1` impede download, e um idioma fora do
bundle degrada para "sem alinhamento por palavra" — a degravação sai assim mesmo,
com timestamps por trecho em vez de por palavra, e o PDF, o DOCX e a conferência
declaram isso explicitamente (o JSON grava `"alinhamento_por_palavra": false`).

**c) ffmpeg:**
```
copy ffmpeg.exe, ffprobe.exe  ->  empacotar/ffmpeg/
```

### 2. Congelar o app
```
python -m PyInstaller empacotar/vox.spec --distpath empacotar/dist --workpath empacotar/build --noconfirm
```

### 3. Validar o pacote (sem GUI)
Crie junções temporárias e rode o diagnóstico:
```
mklink /J empacotar\dist\VOX\modelos  empacotar\modelos
mklink /J empacotar\dist\VOX\ffmpeg   empacotar\ffmpeg
empacotar\dist\VOX\VOX.exe --diag "C:\caminho\audio.ogg"
```
Confira `empacotar\dist\VOX\vox_diagnostico.txt` → deve terminar em `=== SUCESSO ===`.

**Valide também os idiomas**, um por caminho de modelo — o pt resolve pelo
Hugging Face e os demais pelo torchaudio (`TORCH_HOME`), e só o executável
congelado prova que os dois funcionam ali dentro:
```
empacotar\dist\VOX\VOX.exe --diag "audio.ogg" --idioma pt
empacotar\dist\VOX\VOX.exe --diag "audio.ogg" --idioma es
```
O log traz `alinhamento por palavra: True` e `segmentos com palavras: N/N`.
Se vier `False`, o modelo daquele idioma **não** está no bundle — a degravação
sai mesmo assim, mas sem timestamps por palavra.
**Limpe o `dist` antes de compilar o instalador.** O `.iss` empacota
`dist\VOX\*` recursivamente, então tudo o que a validação deixou para trás vai
junto para a máquina do usuário:
```
rmdir empacotar\dist\VOX\modelos          :: junção — senão os modelos entram em dobro
rmdir empacotar\dist\VOX\ffmpeg           :: junção
del   empacotar\dist\VOX\vox_diagnostico.txt
rmdir /s /q empacotar\dist\VOX\diag_saida :: a degravação inteira do áudio de teste!
```
> Use `rmdir` (sem `/s`) nas **junções**: remove só o link. Um apagamento
> recursivo pode atravessá-las e levar junto os 4,6 GB de `empacotar\modelos`.

### 4. Montar o instalador
```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" empacotar\vox.iss
```
Saída em `empacotar\saida_instalador\`: o instalador é **dividido** em
`Instalador VOX <versão>.exe` + fatias `.bin` (disk spanning), porque um `.exe`
único não comporta o pacote.

> **Não misture versões na mesma pasta.** As fatias `.bin` são nomeadas pela
> versão, então um build novo **não** sobrescreve o anterior: os dois ficam
> lado a lado e quem for implantar pode copiar o conjunto errado. Compile cada
> release numa subpasta própria com `/O`:
> ```
> "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /O"empacotar\saida_instalador\VOX 1.1" empacotar\vox.iss
> ```

Tamanhos medidos na **1.1** (2026-09-22, 6 idiomas): **6,87 GB** em 1 `.exe`
(4,5 MB) + 4 `.bin`, a partir de 12,6 GB brutos (`dist/VOX` 7,61 + `modelos` 4,56
+ `ffmpeg` 0,45). Compilar levou **9,1 min** (544 s), além de **7,1 min** do
PyInstaller. Praticamente idêntico à 1.0 — as duas melhorias da 1.1 são código,
não modelos.

## Como funciona o modo offline

`degravador/_offline.py` (`configurar()`) roda no início do app: se existe uma pasta
`modelos/` ao lado do executável, aponta `HF_HOME`/`TORCH_HOME` para lá, liga
`HF_HUB_OFFLINE=1` e coloca o `ffmpeg` embutido no PATH. Também define `VOX_OFFLINE=1`,
o que (a) fixa o perfil no **turbo** (large-v3 completo não vai no bundle) e
(b) permite o **pyannote carregar sem token** (o modelo já está no cache local).

## Implantação (máquina de destino)

1. Copie **toda a pasta da versão** (o `.exe` **e** os `.bin`, ~6,9 GB) para a
   máquina. O `.exe` sozinho tem ~5 MB e **não funciona** sem as fatias.
2. Execute `Instalador VOX <versão>.exe`.
3. Como o instalador **não é assinado**, o Windows SmartScreen pode alertar → *Mais
   informações → Executar assim mesmo*.
4. Pronto: **VOX** no Menu Iniciar / Área de Trabalho. Funciona 100% offline.

> Requisitos da máquina de destino: Windows 10/11 64-bit. GPU NVIDIA (4 GB+) acelera;
> sem GPU, roda em CPU (mais lento). O runtime WebView2 já vem no Windows 11.
