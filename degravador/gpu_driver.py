"""Diagnóstico do driver NVIDIA / CUDA da máquina.

Por que existe: o VOX transcreve na GPU. Um driver NVIDIA antigo demais não expõe
o CUDA que o PyTorch embutido espera — a GPU simplesmente *some*, o VOX cai para
CPU, e uma degravação de minutos passa a levar horas sem explicação visível.
Este módulo dá o veredito **antes** de a pessoa perder a tarde.

Duas perguntas, respondidas em camadas:

  1. **"O driver instalado serve para o VOX?"** — respondida *offline*, comparando
     a versão do driver com o mínimo publicado pela NVIDIA para o CUDA que o
     PyTorch do bundle usa. Funciona em rede isolada (air-gap), que é o alvo do
     instalador.
  2. **"Existe driver mais novo?"** — respondida *só se houver internet*,
     consultando o catálogo público da NVIDIA (as três linhas: GeForce,
     RTX/Quadro profissional e Data Center). É um extra: sem rede o módulo não
     opina sobre isso, nunca trava e nunca acusa nada.

Nada aqui instala nem altera driver: o VOX diagnostica e aponta o caminho; quem
instala é a pessoa. Desligue a consulta online com ``VOX_SEM_CHECAGEM_ONLINE=1``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Constantes de compatibilidade
# ---------------------------------------------------------------------------
# CUDA que o PyTorch distribuído com o VOX usa (roda cu128). Se o torch já
# estiver carregado, preferimos perguntar a ele — não importamos só para isto,
# porque este diagnóstico roda na abertura do app e torch custa segundos.
CUDA_REQUERIDO = "12.8"

# Mínimo absoluto (Windows). Pela *minor version compatibility* do CUDA 12.x,
# qualquer runtime 12.x roda sobre um driver do ramo 12.0 ou superior.
DRIVER_MINIMO = "527.41"

# Mínimo do ramo CUDA 12.8 nativo (Windows) — e também o piso das GPUs Blackwell
# (RTX 50xx), que drivers anteriores sequer reconhecem.
DRIVER_RECOMENDADO = "570.65"

# Driver mínimo publicado pela NVIDIA por ramo do CUDA (Windows). Usada apenas
# para ESTIMAR o "CUDA máximo suportado" quando o nvidia-smi não informa — ele
# informa na esmagadora maioria dos casos, então esta tabela envelhecer não
# compromete o veredito, só o texto exibido.
_CUDA_POR_DRIVER = [
    ("580.88", "13.0"),
    ("576.02", "12.9"),
    ("570.65", "12.8"),
    ("560.76", "12.6"),
    ("555.85", "12.5"),
    ("551.61", "12.4"),
    ("546.12", "12.3"),
    ("536.25", "12.2"),
    ("531.14", "12.1"),
    ("527.41", "12.0"),
    ("522.06", "11.8"),
]

URL_DOWNLOAD = "https://www.nvidia.com/pt-br/drivers/"

# Linhas de driver da NVIDIA, com os identificadores do catálogo público
# (psid = série do produto, pfid = produto). Dentro de cada linha o driver é
# unificado — a versão devolvida vale para todos os modelos daquela linha.
LINHAS = {
    "geforce": {
        "rotulo": "GeForce (Game Ready / Studio)",
        "psid": 120, "pfid": 942,
    },
    "profissional": {
        "rotulo": "NVIDIA RTX / Quadro (profissional)",
        "psid": 122, "pfid": 935,
    },
    "datacenter": {
        "rotulo": "Data Center (Tesla / A / H / L)",
        "psid": 129, "pfid": 1054,
    },
}

_API_NVIDIA = (
    "https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/"
    "AjaxDriverService.php?func=DriverManualLookup"
    "&psid={psid}&pfid={pfid}&osID=135&languageCode=1033"
    "&dch=1&dltype=-1&sort1=0&numberOfResults=1"
)

# Nomes de GPU de Data Center não trazem marca de linha no nome ("NVIDIA A100").
_PADRAO_DATACENTER = re.compile(
    r"\b(tesla|[abhl]\d{2,3}[sm]?|gb\d{3}|gh\d{3}|v100|t4|t10|p4|p40|p100|k80)\b",
    re.I,
)
_PADRAO_PROFISSIONAL = re.compile(r"\b(quadro|rtx\s*(pro|[a-z]\d{3,4})|nvs)\b", re.I)

_CACHE_DIAS = 7


# ---------------------------------------------------------------------------
# Versões
# ---------------------------------------------------------------------------
def _tupla(versao: str | None) -> tuple[int, ...]:
    """'596.36' → (596, 36). Inválido/ausente → (0,), que perde de tudo."""
    if not versao:
        return (0,)
    partes = re.findall(r"\d+", str(versao))
    return tuple(int(p) for p in partes) or (0,)


def _cuda_estimado(driver: str | None) -> str | None:
    """CUDA máximo que o driver suporta, pela tabela publicada (fallback)."""
    if not driver:
        return None
    alvo = _tupla(driver)
    for minimo, cuda in _CUDA_POR_DRIVER:
        if alvo >= _tupla(minimo):
            return cuda
    return None


def _blackwell(nome: str) -> bool:
    """RTX 50xx (Blackwell): drivers anteriores ao ramo 570 nem enxergam a placa."""
    return bool(re.search(r"\bRTX\s*50\d{2}\b", nome or "", re.I))


def classificar_linha(nome: str) -> str:
    """Qual linha de driver atende esta GPU (chave de ``LINHAS``)."""
    nome = nome or ""
    if re.search(r"geforce|gtx|titan", nome, re.I):
        return "geforce"
    if _PADRAO_DATACENTER.search(nome):
        return "datacenter"
    if _PADRAO_PROFISSIONAL.search(nome):
        return "profissional"
    return "geforce"  # público do VOX: na dúvida, é uma placa de consumo


# ---------------------------------------------------------------------------
# Detecção local (offline)
# ---------------------------------------------------------------------------
def _rodar(args: list[str], timeout: float = 8.0) -> str | None:
    """Executa um utilitário e devolve o stdout. Sem piscar console no app."""
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _via_nvidia_smi() -> dict | None:
    """GPUs, driver e CUDA do driver pelo nvidia-smi (acompanha todo driver NVIDIA)."""
    saida = _rodar([
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader,nounits",
    ])
    if not saida or not saida.strip():
        return None

    gpus: list[dict] = []
    driver = None
    for linha in saida.strip().splitlines():
        campos = [c.strip() for c in linha.split(",")]
        if len(campos) < 2:
            continue
        nome, driver = campos[0], campos[1]
        vram = None
        if len(campos) > 2:
            try:
                vram = round(float(campos[2]) / 1024, 1)  # MiB → GiB
            except ValueError:
                pass
        gpus.append({"nome": nome, "vram_gb": vram})
    if not gpus:
        return None

    # O cabeçalho do nvidia-smi informa o CUDA máximo do driver — mais fiel que
    # qualquer tabela nossa, porque vem do próprio driver instalado.
    cuda = None
    cabecalho = _rodar(["nvidia-smi"])
    if cabecalho:
        m = re.search(r"CUDA Version:\s*([\d.]+)", cabecalho)
        if m:
            cuda = m.group(1)
    return {"gpus": gpus, "driver": driver, "cuda_driver": cuda, "fonte": "nvidia-smi"}


def _via_registro() -> dict | None:
    """Fallback sem nvidia-smi: lê a classe de adaptadores de vídeo no registro.

    O Windows guarda a versão do *pacote de driver* ("32.0.15.9636"); a versão
    NVIDIA que a pessoa vê é formada pelos 5 últimos dígitos ("596.36").
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    classe = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    gpus: list[dict] = []
    driver = None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, classe) as raiz:
            for i in range(32):
                try:
                    sub = winreg.EnumKey(raiz, i)
                except OSError:
                    break
                if not sub.isdigit():
                    continue
                try:
                    with winreg.OpenKey(raiz, sub) as k:
                        fornecedor = str(winreg.QueryValueEx(k, "ProviderName")[0])
                        if "nvidia" not in fornecedor.lower():
                            continue
                        nome = str(winreg.QueryValueEx(k, "DriverDesc")[0])
                        bruto = str(winreg.QueryValueEx(k, "DriverVersion")[0])
                except OSError:
                    continue
                digitos = bruto.replace(".", "")
                if len(digitos) >= 5:
                    driver = f"{digitos[-5:-2]}.{digitos[-2:]}"
                gpus.append({"nome": nome, "vram_gb": None})
    except OSError:
        return None
    if not gpus:
        return None
    return {"gpus": gpus, "driver": driver,
            "cuda_driver": _cuda_estimado(driver), "fonte": "registro do Windows"}


def detectar() -> dict:
    """O que existe nesta máquina, sem tocar na rede.

    ``{"gpus": [...], "driver": "596.36", "cuda_driver": "13.2", "fonte": ...}``
    ou ``{"gpus": []}`` quando não há GPU NVIDIA.
    """
    for sonda in (_via_nvidia_smi, _via_registro):
        info = sonda()
        if info:
            if not info.get("cuda_driver"):
                info["cuda_driver"] = _cuda_estimado(info.get("driver"))
            return info
    return {"gpus": [], "driver": None, "cuda_driver": None, "fonte": None}


def cuda_requerido() -> str:
    """CUDA do PyTorch embutido — pergunta ao torch só se ele já estiver na memória."""
    torch = sys.modules.get("torch")
    versao = getattr(getattr(torch, "version", None), "cuda", None)
    return versao or CUDA_REQUERIDO


# ---------------------------------------------------------------------------
# Consulta online (opcional, best-effort)
# ---------------------------------------------------------------------------
def _pasta_cache() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "VOX"


def _ler_cache(linha: str) -> str | None:
    try:
        dados = json.loads((_pasta_cache() / "driver_nvidia.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    reg = (dados or {}).get(linha) or {}
    if time.time() - float(reg.get("em", 0)) > _CACHE_DIAS * 86400:
        return None
    return reg.get("versao") or None


def _gravar_cache(linha: str, versao: str) -> None:
    caminho = _pasta_cache() / "driver_nvidia.json"
    try:
        dados = json.loads(caminho.read_text("utf-8"))
        if not isinstance(dados, dict):
            dados = {}
    except (OSError, ValueError):
        dados = {}
    dados[linha] = {"versao": versao, "em": time.time()}
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(dados), encoding="utf-8")
    except OSError:
        pass  # cache é conveniência; falhar aqui não pode quebrar o diagnóstico


def consultar_nvidia(linha: str, *, timeout: float = 6.0, usar_cache: bool = True) -> str | None:
    """Última versão publicada para a linha. ``None`` = não deu para saber.

    Sem rede, com proxy bloqueando ou com o catálogo fora do ar, devolve ``None``
    — nunca levanta. O resultado fica em cache por uma semana para não bater na
    NVIDIA a cada abertura do VOX.
    """
    if linha not in LINHAS:
        return None
    if os.environ.get("VOX_SEM_CHECAGEM_ONLINE"):
        return None
    if usar_cache:
        em_cache = _ler_cache(linha)
        if em_cache:
            return em_cache

    from urllib.request import Request, urlopen

    url = _API_NVIDIA.format(**{k: LINHAS[linha][k] for k in ("psid", "pfid")})
    try:
        req = Request(url, headers={"User-Agent": "VOX/1.0 (verificador de driver)"})
        with urlopen(req, timeout=timeout) as resp:
            dados = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None  # rede é o extra: qualquer falha vira "não sei", não erro

    try:
        versao = str(dados["IDS"][0]["downloadInfo"]["Version"]).strip()
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if not re.fullmatch(r"\d+(\.\d+)+", versao):
        return None
    _gravar_cache(linha, versao)
    return versao


# ---------------------------------------------------------------------------
# Veredito
# ---------------------------------------------------------------------------
def verificar(*, online: bool = True, timeout: float = 6.0) -> dict:
    """Diagnóstico completo, pronto para a interface.

    ``estado`` é um de:
      - ``sem_gpu``   — nenhuma GPU NVIDIA: o VOX roda em CPU (funciona, mas lento);
      - ``critico``   — GPU NVIDIA presente, driver abaixo do mínimo: a GPU não
                        será usada até atualizar;
      - ``atencao``   — driver funciona, mas está atrás do recomendado ou do
                        último publicado;
      - ``ok``        — driver em dia;
      - ``desconhecido`` — não foi possível ler a versão do driver.
    """
    info = detectar()
    gpus = info.get("gpus") or []
    driver = info.get("driver")
    exigido = cuda_requerido()

    res = {
        "estado": "desconhecido",
        "titulo": "",
        "mensagem": "",
        "gpus": gpus,
        "driver": driver,
        "cuda_driver": info.get("cuda_driver"),
        "cuda_requerido": exigido,
        "driver_minimo": DRIVER_MINIMO,
        "driver_recomendado": DRIVER_RECOMENDADO,
        "fonte": info.get("fonte"),
        "linha": None,
        "linha_rotulo": None,
        "driver_mais_recente": None,
        "online": False,
        "url": URL_DOWNLOAD,
        "acao": None,
    }

    if not gpus:
        res.update(
            estado="sem_gpu",
            titulo="Nenhuma GPU NVIDIA detectada",
            mensagem="O VOX vai transcrever usando o processador (CPU). Funciona "
                     "normalmente, mas é bem mais lento em arquivos longos.",
        )
        return res

    nome = gpus[0]["nome"]
    linha = classificar_linha(nome)
    res["linha"] = linha
    res["linha_rotulo"] = LINHAS[linha]["rotulo"]

    if not driver:
        res.update(
            estado="desconhecido",
            titulo="Não foi possível ler a versão do driver",
            mensagem=f"A GPU {nome} foi encontrada, mas a versão do driver NVIDIA "
                     "não pôde ser lida. Se a transcrição ficar lenta, reinstale o "
                     "driver mais recente da NVIDIA.",
            acao={"rotulo": "Baixar driver NVIDIA", "url": URL_DOWNLOAD},
        )
        return res

    atual = _tupla(driver)
    piso = _tupla(DRIVER_RECOMENDADO) if _blackwell(nome) else _tupla(DRIVER_MINIMO)

    if atual < piso:
        exigencia = (
            f"Esta placa ({nome}) é da geração Blackwell e exige o driver "
            f"{DRIVER_RECOMENDADO} ou superior"
            if _blackwell(nome) else
            f"O VOX usa CUDA {exigido}, que exige o driver {DRIVER_MINIMO} ou superior"
        )
        res.update(
            estado="critico",
            titulo=f"Driver NVIDIA desatualizado ({driver})",
            mensagem=f"{exigencia}. Enquanto não atualizar, o VOX vai transcrever "
                     "pela CPU — muito mais lento. Atualize o driver e reabra o VOX.",
            acao={"rotulo": "Atualizar driver NVIDIA", "url": URL_DOWNLOAD},
        )
        return res

    # Daqui para baixo o driver SERVE. Só resta saber se é o mais recente — e
    # essa pergunta depende de rede: sem ela, não inventamos um veredito.
    if online:
        recente = consultar_nvidia(linha, timeout=timeout)
        if recente:
            res["driver_mais_recente"] = recente
            res["online"] = True
            if _tupla(recente) > atual:
                res.update(
                    estado="atencao",
                    titulo=f"Há driver NVIDIA mais recente ({recente})",
                    mensagem=f"Seu driver ({driver}) atende ao VOX e a degravação "
                             f"vai usar a GPU normalmente. A NVIDIA já publicou o "
                             f"{recente} para a linha {LINHAS[linha]['rotulo']} — "
                             "atualizar é opcional.",
                    acao={"rotulo": "Ver driver mais recente", "url": URL_DOWNLOAD},
                )
                return res

    if atual < _tupla(DRIVER_RECOMENDADO):
        res.update(
            estado="atencao",
            titulo=f"Driver NVIDIA antigo ({driver})",
            mensagem=f"O driver atende ao mínimo e a GPU será usada, mas o VOX foi "
                     f"testado a partir do driver {DRIVER_RECOMENDADO} "
                     f"(CUDA {exigido} nativo). Atualizar é recomendado.",
            acao={"rotulo": "Atualizar driver NVIDIA", "url": URL_DOWNLOAD},
        )
        return res

    vram = gpus[0].get("vram_gb")
    detalhe = f"{nome}" + (f" · {vram:.0f} GB de VRAM" if vram else "")
    res.update(
        estado="ok",
        titulo="GPU pronta para o VOX",
        mensagem=f"{detalhe} · driver {driver}"
                 + (" (o mais recente publicado pela NVIDIA)"
                    if res["driver_mais_recente"] else ""),
    )
    return res


def resumo_texto(res: dict) -> str:
    """Diagnóstico em texto, para log e suporte técnico."""
    linhas = [f"[{res['estado'].upper()}] {res['titulo']}", res["mensagem"], ""]
    for g in res.get("gpus") or []:
        vram = f" · {g['vram_gb']} GB" if g.get("vram_gb") else ""
        linhas.append(f"  GPU: {g['nome']}{vram}")
    linhas += [
        f"  Driver instalado: {res.get('driver') or '—'} (fonte: {res.get('fonte') or '—'})",
        f"  CUDA suportado pelo driver: {res.get('cuda_driver') or '—'}",
        f"  CUDA exigido pelo VOX: {res.get('cuda_requerido')}"
        f" (driver mínimo {res.get('driver_minimo')})",
        f"  Linha de driver: {res.get('linha_rotulo') or '—'}",
        f"  Último publicado pela NVIDIA: {res.get('driver_mais_recente') or 'não consultado'}",
    ]
    return "\n".join(linhas)
