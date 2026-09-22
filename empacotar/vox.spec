# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec do VOX (onedir). Modelos e ffmpeg são colocados ao lado do
executável pelo instalador (Inno), não por aqui, para o build ficar mais leve."""

import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

RAIZ = SPECPATH                   # empacotar/ (SPECPATH já é a pasta do .spec)
PROJ = os.path.dirname(SPECPATH)  # raiz do projeto

datas, binaries, hiddenimports = [], [], []

# METADADOS (dist-info): o transformers/lightning/etc. usam importlib.metadata
# para detectar dependências (ex.: is_torch_available). Sem isso no app congelado,
# o transformers acha que o torch "não está disponível" e falha ao importar
# classes ("Could not import module 'Pipeline'"). Copiamos os metadados:
_METADADOS = [
    "torch", "torchaudio", "torchvision", "transformers", "tokenizers",
    "huggingface-hub", "safetensors", "numpy", "tqdm", "regex", "pyyaml",
    "filelock", "packaging", "requests", "ctranslate2", "faster-whisper",
    "onnxruntime", "sentencepiece", "speechbrain", "pyannote.audio",
    "pyannote.core", "pyannote.database", "pyannote.metrics", "pyannote.pipeline",
    "lightning", "pytorch-lightning", "lightning-utilities", "scipy",
    "scikit-learn", "pandas", "fsspec", "sympy", "networkx", "optuna",
    "omegaconf", "hyperpyyaml", "einops", "soundfile", "av", "protobuf",
    "asteroid-filterbanks", "julius", "primePy", "antlr4-python3-runtime",
    "rich", "torchmetrics", "torch-audiomentations", "pytorch-metric-learning",
]
for _m in _METADADOS:
    try:
        datas += copy_metadata(_m, recursive=True)
    except Exception as _e:
        print("  [spec] metadados ausentes:", _m, "->", _e)

_PACOTES = [
    "torch", "torchaudio", "torchvision", "torchmetrics",
    "whisperx", "pyannote", "pyannote.audio", "pyannote.core", "pyannote.database",
    "pyannote.metrics", "pyannote.pipeline", "faster_whisper", "ctranslate2",
    "speechbrain", "lightning", "pytorch_lightning", "lightning_fabric",
    "transformers", "huggingface_hub", "tokenizers", "safetensors",
    "sklearn", "scipy", "pandas", "numpy", "asteroid_filterbanks",
    "torch_audiomentations", "torch_pitch_shift", "julius", "omegaconf", "antlr4",
    "soundfile", "av", "onnxruntime", "webview", "fpdf", "docx", "dotenv",
    "sentencepiece", "regex", "hyperpyyaml", "ruamel", "pytorch_metric_learning",
    "einops", "primePy", "sympy", "networkx", "filelock", "yaml", "tqdm",
    "nltk", "optuna", "sortedcontainers", "semver", "tabulate",
]
for _pkg in _PACOTES:
    try:
        d, b, h = collect_all(_pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as _e:
        print("  [spec] pulando", _pkg, "->", _e)

# Dados da aplicação (interface e estilos)
datas += [
    (os.path.join(PROJ, "degravador", "webui"), "degravador/webui"),
    (os.path.join(PROJ, "estilos"), "estilos"),
]

# Submódulos que às vezes escapam da análise
hiddenimports += [
    "sklearn.utils._typedefs", "sklearn.utils._heap", "sklearn.utils._sorting",
    "sklearn.neighbors._partition_nodes", "scipy.special.cython_special",
    "sklearn.metrics._pairwise_distances_reduction._datasets_pair",
    "sklearn.metrics._pairwise_distances_reduction._middle_term_computer",
    # Alinhamento por wav2vec2 (transformers) — importado dinamicamente:
    "transformers.models.wav2vec2",
    "transformers.models.wav2vec2.modeling_wav2vec2",
    "transformers.models.wav2vec2.processing_wav2vec2",
    "transformers.models.wav2vec2.tokenization_wav2vec2",
    "transformers.models.wav2vec2.feature_extraction_wav2vec2",
    "transformers.pipelines",
    "sentencepiece",
    # Importado dentro de Api.checar_gpu(), não no topo do app: garantimos que
    # o diagnóstico de driver NVIDIA entre no pacote mesmo assim.
    "degravador.gpu_driver",
]

a = Analysis(
    [os.path.join(RAIZ, "vox_main.py")],
    pathex=[PROJ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "IPython", "notebook", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="VOX",
    debug=False,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(RAIZ, "vox.ico"),
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="VOX",
)
