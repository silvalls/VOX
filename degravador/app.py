"""App desktop (pywebview) do Degravador.

Fluxo: escolher arquivo → transcrever (com barra de progresso) → conferência +
correção (com renomear de locutores) → exportar DOCX corrigido + original.

A janela hospeda o mesmo player HTML de conferência (saidas/html.py); o botão
"Salvar correção" chama de volta o Python (bridge pywebview) para gerar o DOCX.

Rodar:  python -m degravador.app        (requer ffmpeg no PATH)
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import webview

from . import branding
from .saidas import html as _shtml
from .saidas import pdf as _spdf


def _carregar_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass


def _resolver_estilo() -> str | None:
    candidatos = []
    if getattr(sys, "_MEIPASS", None):  # app congelado (PyInstaller)
        candidatos.append(Path(sys._MEIPASS) / "estilos" / "oficial_abnt.json")
    candidatos.append(Path("estilos") / "oficial_abnt.json")
    candidatos.append(Path(__file__).resolve().parent.parent / "estilos" / "oficial_abnt.json")
    for c in candidatos:
        if c.exists():
            return str(c)
    return None


TIPOS_ARQ = (
    "Áudio e vídeo (*.mp3;*.wav;*.ogg;*.opus;*.m4a;*.aac;*.flac;*.wma;"
    "*.mp4;*.mkv;*.mov;*.avi;*.wmv;*.webm;*.flv)",
    "Todos os arquivos (*.*)",
)


def _erro_amigavel(e: Exception) -> str:
    msg = str(e)
    nome = type(e).__name__
    baixo = msg.lower()
    if "ffmpeg" in baixo or "FFmpeg" in nome:
        return ("Não foi possível ler o áudio deste arquivo. Verifique se o arquivo não "
                "está corrompido e se o formato é suportado (ou se o ffmpeg está instalado).")
    if "out of memory" in baixo or "cuda" in baixo:
        return ("A placa de vídeo ficou sem memória. Tente um arquivo menor, feche outros "
                "programas ou use uma máquina com mais VRAM.")
    if isinstance(e, FileNotFoundError):
        return "Arquivo não encontrado. Ele pode ter sido movido ou renomeado."
    return f"Ocorreu um erro ao processar ({nome}). Detalhe: {msg[:200]}"


class Api:
    def __init__(self) -> None:
        # Não guardar a janela como atributo: o pywebview introspecta o objeto
        # da API e uma referência à Window causa recursão infinita. Buscamos a
        # janela via webview.windows[0] dentro de cada método.
        self._ultimo: dict | None = None  # resultado do último degravar()
        self._cancelar = False

    def cancelar(self):
        """Solicita o cancelamento do processamento (efetivo ao fim da etapa atual)."""
        self._cancelar = True
        return True

    @property
    def _janela(self):
        return webview.windows[0]

    # -- seleção de arquivo (diálogo nativo) --
    def escolher_arquivo(self):
        res = self._janela.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=TIPOS_ARQ
        )
        if not res:
            return None
        return res[0] if isinstance(res, (list, tuple)) else res

    # -- seleção de PASTA (onde será criada a pasta de resultados) --
    def escolher_pasta(self):
        res = self._janela.create_file_dialog(webview.FOLDER_DIALOG)
        if not res:
            return None
        return res[0] if isinstance(res, (list, tuple)) else res

    # -- idiomas oferecidos (fonte: config.IDIOMAS_INTERFACE) --
    def idiomas(self):
        """Lista para o <select> da interface. Só idiomas presentes no bundle."""
        from .config import IDIOMA, IDIOMAS_INTERFACE
        return [
            {"codigo": codigo, "rotulo": rotulo, "padrao": codigo == IDIOMA}
            for codigo, rotulo in IDIOMAS_INTERFACE
        ]

    # -- validador de integridade (SHA-256) --
    def hash_arquivo(self, caminho):
        from .extracao import sha256_arquivo
        try:
            return {"ok": True, "sha256": sha256_arquivo(caminho)}
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    def escolher_e_hash(self):
        c = self.escolher_arquivo()
        if not c:
            return None
        r = self.hash_arquivo(c)
        r["arquivo"] = Path(c).name
        return r

    # -- processamento (roda na thread da chamada; empurra progresso via JS) --
    def transcrever(self, caminho, opts):
        from .pipeline import degravar, CanceladoError

        self._cancelar = False

        def prog(pct, msg):
            try:
                self._janela.evaluate_js(
                    f"window.progresso && window.progresso({int(pct)}, {json.dumps(str(msg))})"
                )
            except Exception:
                pass

        entrada = Path(caminho)
        # Pasta de resultados: <local escolhido>/<nome do áudio>/ (criada automaticamente).
        local = (opts or {}).get("destino") or str(entrada.parent)
        outdir = Path(local) / entrada.stem
        try:
            res = degravar(
                caminho, outdir,
                perfil_nome=(opts or {}).get("perfil") or None,
                diarizador=(opts or {}).get("diarizador", "auto"),
                num_speakers=(opts or {}).get("num_speakers") or None,
                idioma=(opts or {}).get("idioma") or None,
                salvar_json=False,
                progresso=prog,
                cancelado=lambda: self._cancelar,
            )
        except CanceladoError:
            return {"ok": False, "cancelado": True}
        except Exception as e:
            return {"ok": False, "erro": _erro_amigavel(e)}

        doc = res["doc"]
        if not doc.get("segments"):
            return {"ok": False, "erro": "Nenhuma fala foi detectada no áudio. "
                    "Verifique se o arquivo realmente contém voz audível."}

        base = Path(res["base"])
        estilo = _resolver_estilo()
        prog(100, "Gerando PDF e a conferência…")
        # DOIS arquivos na pasta: PDF (degravação) + HTML (conferência). O HTML
        # referencia o arquivo ORIGINAL (caminho absoluto) para tocar o áudio.
        audio_uri = entrada.resolve().as_uri()
        _spdf.exportar(doc, base.parent / (base.name + ".pdf"), caminho_estilo=estilo)
        review = base.parent / (base.name + ".conferencia.html")
        _shtml.exportar(doc, review, audio_src=audio_uri)
        # Fonte de verdade: transcrição bruta com timestamps e scores (auditoria).
        from .saidas import json as _sjson
        _sjson.salvar_em(doc, base.parent / (base.name + ".bruto.json"))
        # Legendas opcionais (para vídeo)
        if (opts or {}).get("legendas"):
            from .saidas import srt as _ssrt, vtt as _svtt
            _ssrt.exportar(doc, base.parent / (base.name + ".srt"))
            _svtt.exportar(doc, base.parent / (base.name + ".vtt"))
        # o WAV da extração é temporário — não é entregável
        try:
            Path(res["wav"]).unlink(missing_ok=True)
        except Exception:
            pass
        self._ultimo = {"doc": doc, "base": str(base), "entrada": str(entrada),
                        "review": review.as_uri(), "pasta": str(outdir)}
        # Não navega sozinho: a tela final informa a pasta e oferece os botões
        # "Abrir pasta" e "Conferir e corrigir" (este abre a conferência DENTRO do
        # app, mantendo a ponte da API para o "Salvar correção").
        return {"ok": True, "pasta": str(outdir)}

    def _navegar(self, url):
        try:
            self._janela.load_url(url)
        except Exception:
            pass

    def abrir_pasta(self, caminho=None):
        import os
        alvo = caminho or (self._ultimo or {}).get("pasta")
        try:
            if alvo and os.path.isdir(alvo):
                os.startfile(alvo)
        except Exception:
            pass
        return True

    def abrir_conferencia(self):
        # Abre a conferência no próprio app (load_url mantém a ponte da API).
        rev = (self._ultimo or {}).get("review")
        if rev:
            import threading
            threading.Timer(0.1, lambda: self._navegar(rev)).start()
        return True

    # -- salvar correção humana → PDF corrigido pós-conferência (bridge do player) --
    def salvar_correcao(self, dados):
        if not self._ultimo:
            return "erro: nada para salvar"
        from . import correcao

        doc = self._ultimo["doc"]
        base = Path(self._ultimo["base"])
        mapa = (dados or {}).get("locutores") or None
        conferencista = (dados or {}).get("conferencista") or None
        estilo = _resolver_estilo()

        doc_corr = correcao.aplicar(doc, dados or {}, revisado_por=conferencista)
        destino = base.parent / (base.name + ".corrigido.pdf")
        _spdf.exportar(
            doc_corr, destino,
            mapa_locutores=mapa, caminho_estilo=estilo,
            pos_conferencia=True, revisado_por=conferencista,
        )
        # Relatório diferencial comparativo (documento à parte). Recebe a própria
        # correção porque só ela sabe o que foi mesclagem de rótulo e o que foi
        # interlocutor criado na conferência.
        from . import relatorio
        comp = relatorio.comparar(doc, doc_corr, correcao=dados or {})
        relatorio.gerar_pdf(
            comp, base.parent / (base.name + ".relatorio-conferencia.pdf"),
            meta=doc.get("metadata", {}), conferencista=conferencista, mapa_locutores=mapa,
        )
        extra = ""
        n_ajustes = len(comp.get("ajustes") or []) + len(comp.get("merges") or {})
        if n_ajustes:
            extra = f", {n_ajustes} ajuste(s) de interlocutor"
        return (f"{destino.name}  (+ relatório: {comp['pct_texto_alterado']:.1f}% "
                f"do texto alterado{extra})")

    # -- diagnóstico do driver NVIDIA/CUDA (faixa da tela inicial) --
    def checar_gpu(self):
        """Estado do driver NVIDIA desta máquina. Nunca levanta: a tela inicial
        não pode deixar de abrir porque um diagnóstico falhou."""
        try:
            from . import gpu_driver
            return gpu_driver.verificar()
        except Exception as e:
            return {"estado": "desconhecido",
                    "titulo": "Não foi possível verificar o driver de vídeo",
                    "mensagem": f"({type(e).__name__}) O VOX funciona normalmente; "
                                "só não conseguiu diagnosticar a GPU.",
                    "acao": None}

    def abrir_url(self, url):
        """Abre um link no navegador do sistema (página de driver da NVIDIA)."""
        import webbrowser
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            try:
                webbrowser.open(url)
            except Exception:
                pass
        return True


def main() -> None:
    from ._offline import configurar
    configurar()          # modelos embutidos + offline, se instalado
    _carregar_env()
    api = Api()
    inicio = Path(__file__).parent / "webui" / "index.html"
    webview.create_window(
        branding.NOME, url=str(inicio), js_api=api,
        width=1120, height=820, min_size=(900, 640),
    )
    webview.start()


if __name__ == "__main__":
    main()
