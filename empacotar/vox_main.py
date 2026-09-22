"""Ponto de entrada do executável empacotado (PyInstaller) do VOX.

Modo normal: abre o app (GUI).
Modo diagnóstico: `VOX.exe --diag <audio> [--idioma ISO]` roda o pipeline
completo e grava o resultado/traceback em `vox_diagnostico.txt` ao lado do
executável (útil para validar o empacotamento sem depender da interface).

O `--idioma` existe para validar o bundle offline idioma a idioma: o modelo de
alinhamento do pt vem do Hugging Face e o de es/en/fr/de/it do torchaudio
(TORCH_HOME) — caminhos distintos, que precisam ser exercitados no executável
congelado, não só em desenvolvimento.
"""

import sys
from pathlib import Path


def _diagnostico() -> None:
    import traceback
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    log = base / "vox_diagnostico.txt"

    def w(msg):
        with open(log, "a", encoding="utf-8") as f:
            f.write(str(msg) + "\n")

    try:
        log.write_text("=== VOX diagnóstico ===\n", encoding="utf-8")
        from degravador._offline import configurar
        w("offline configurado: " + str(configurar()))
        import os
        w("HF_HOME=" + str(os.environ.get("HF_HOME")))
        w("TORCH_HOME=" + str(os.environ.get("TORCH_HOME")))
        w("HF_HUB_OFFLINE=" + str(os.environ.get("HF_HUB_OFFLINE")))

        audio = None
        idioma = None
        args = sys.argv[1:]
        for i, a in enumerate(args):
            if a == "--idioma":
                idioma = args[i + 1] if i + 1 < len(args) else None
            elif a not in ("--diag", idioma):
                audio = a
        if not audio:
            w("ERRO: informe o áudio: VOX.exe --diag <caminho> [--idioma ISO]")
            return
        w("idioma pedido: " + str(idioma or "(padrão)"))

        from degravador.pipeline import degravar
        saida = base / "diag_saida"
        res = degravar(audio, str(saida), perfil_nome="recomendado",
                       diarizador="pyannote", idioma=idioma, salvar_json=False,
                       progresso=lambda p, m: w(f"[{p:3}%] {m}"))
        meta = res["doc"]["metadata"]
        params = meta.get("params", {})
        segs = res["doc"]["segments"]
        w("OK — segmentos: %d | locutores: %s" % (len(segs), meta.get("num_speakers")))
        w("idioma efetivo: %s | alinhamento por palavra: %s | segmentos com palavras: %d/%d"
          % (params.get("idioma"), params.get("alinhamento_por_palavra"),
             sum(1 for s in segs if s.get("words")), len(segs)))
        w("=== SUCESSO ===")
    except Exception:
        w("=== FALHOU ===")
        w(traceback.format_exc())


def main() -> None:
    if "--diag" in sys.argv:
        _diagnostico()
        return
    from degravador.app import main as app_main
    app_main()


if __name__ == "__main__":
    main()
