"""Etapa 1 — Extração e normalização de áudio (ffmpeg).

- Aceita qualquer formato suportado pelo ffmpeg (vídeo ou áudio).
- Extrai a trilha e converte para WAV PCM 16 kHz mono (ótimo para os modelos).
- Aplica ``loudnorm`` para consistência de volume.
- Nunca carrega o vídeo inteiro em memória: o ffmpeg faz streaming; só o WAV
  extraído (áudio) é processado adiante.
- Calcula o SHA-256 do arquivo ORIGINAL (auditabilidade / cadeia de custódia).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


class FFmpegNaoEncontrado(RuntimeError):
    pass


def _exigir(binario: str) -> str:
    caminho = shutil.which(binario)
    if not caminho:
        raise FFmpegNaoEncontrado(
            f"'{binario}' não encontrado no PATH. Instale o ffmpeg "
            "(inclui ffprobe) e garanta que esteja acessível no terminal.\n"
            "  Windows:  winget install Gyan.FFmpeg   (ou choco install ffmpeg)\n"
            "  Linux:    sudo apt install ffmpeg\n"
            "  macOS:    brew install ffmpeg"
        )
    return caminho


def sha256_arquivo(caminho: str | Path, _bloco: int = 1024 * 1024) -> str:
    """SHA-256 do arquivo, lido em blocos (não carrega tudo em memória)."""
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for pedaco in iter(lambda: f.read(_bloco), b""):
            h.update(pedaco)
    return h.hexdigest()


def duracao_segundos(caminho: str | Path) -> float:
    """Duração da mídia via ffprobe (segundos)."""
    ffprobe = _exigir("ffprobe")
    proc = subprocess.run(
        [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(caminho),
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe falhou: {proc.stderr.strip()}")
    try:
        return float(json.loads(proc.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return 0.0


def extrair_audio(
    entrada: str | Path,
    saida_wav: str | Path,
    *,
    normalizar: bool = True,
    taxa_hz: int = 16000,
) -> Path:
    """Extrai/normaliza o áudio de ``entrada`` para WAV PCM 16 kHz mono.

    Retorna o caminho do WAV gerado.
    """
    ffmpeg = _exigir("ffmpeg")
    entrada = Path(entrada)
    saida_wav = Path(saida_wav)
    if not entrada.exists():
        raise FileNotFoundError(f"Arquivo de entrada não existe: {entrada}")
    saida_wav.parent.mkdir(parents=True, exist_ok=True)

    filtros = []
    if normalizar:
        # loudnorm (EBU R128): melhora consistência sem alterar conteúdo falado.
        filtros.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    cmd = [
        ffmpeg, "-y",
        "-i", str(entrada),
        "-vn",                       # descarta vídeo
        "-ac", "1",                  # mono
        "-ar", str(taxa_hz),         # 16 kHz
        "-c:a", "pcm_s16le",         # WAV PCM 16-bit
    ]
    if filtros:
        cmd += ["-af", ",".join(filtros)]
    cmd += [str(saida_wav)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg falhou na extração de áudio:\n" + proc.stderr.strip()
        )
    if not saida_wav.exists() or saida_wav.stat().st_size == 0:
        raise RuntimeError("ffmpeg terminou mas o WAV de saída está vazio.")
    return saida_wav
