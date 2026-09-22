"""Diagnóstico do driver NVIDIA/CUDA.

O veredito precisa ser correto offline (é o que vale no instalador air-gap) e a
consulta ao catálogo da NVIDIA precisa ser um extra que NUNCA quebra nada: sem
rede, com proxy no caminho ou com o site mudando de formato, o resultado é
"não sei", jamais uma exceção ou um falso alarme.
"""

from __future__ import annotations

import pytest

from degravador import gpu_driver as g


# ---------------------------------------------------------------------------
# Comparação de versões e leitura da tabela
# ---------------------------------------------------------------------------
def test_versoes_comparam_por_numero_e_nao_por_texto():
    # "596.36" < "60.1" como texto; como driver, é o contrário.
    assert g._tupla("596.36") > g._tupla("60.1")
    assert g._tupla("570.65") > g._tupla("527.41")
    assert g._tupla("527.41") == g._tupla("527.41")
    assert g._tupla(None) == (0,)          # ausente perde de tudo
    assert g._tupla("sei lá") == (0,)


def test_cuda_estimado_pelo_driver():
    assert g._cuda_estimado("596.36") == "13.0"
    assert g._cuda_estimado("560.90") == "12.6"
    assert g._cuda_estimado("400.00") is None


@pytest.mark.parametrize("nome, linha", [
    ("NVIDIA GeForce RTX 5090", "geforce"),
    ("NVIDIA GeForce GTX 1660 Ti", "geforce"),
    ("Quadro P2000", "profissional"),
    ("NVIDIA RTX A4000", "profissional"),
    ("Tesla T4", "datacenter"),
    ("NVIDIA A100-SXM4-40GB", "datacenter"),
    ("NVIDIA H100 PCIe", "datacenter"),
    ("placa esquisita sem nome conhecido", "geforce"),
])
def test_classificacao_da_linha_de_driver(nome, linha):
    assert g.classificar_linha(nome) == linha


def test_blackwell_reconhecida():
    assert g._blackwell("NVIDIA GeForce RTX 5090")
    assert not g._blackwell("NVIDIA GeForce RTX 4090")


# ---------------------------------------------------------------------------
# Veredito (offline)
# ---------------------------------------------------------------------------
def _fingir(monkeypatch, gpus, driver, cuda="12.8"):
    monkeypatch.setattr(g, "detectar", lambda: {
        "gpus": gpus, "driver": driver, "cuda_driver": cuda, "fonte": "teste"})


def test_sem_gpu_nvidia_avisa_que_vai_de_cpu(monkeypatch):
    _fingir(monkeypatch, [], None, None)
    r = g.verificar(online=False)
    assert r["estado"] == "sem_gpu"
    assert "CPU" in r["mensagem"]
    assert r["acao"] is None          # não há driver a instalar


def test_driver_abaixo_do_minimo_e_critico(monkeypatch):
    _fingir(monkeypatch, [{"nome": "NVIDIA GeForce GTX 1080", "vram_gb": 8.0}], "470.00")
    r = g.verificar(online=False)
    assert r["estado"] == "critico"
    assert g.DRIVER_MINIMO in r["mensagem"]
    assert r["acao"]["url"] == g.URL_DOWNLOAD


def test_blackwell_exige_o_ramo_570_ainda_que_o_minimo_geral_passe(monkeypatch):
    # 560 passa do mínimo do CUDA 12.x, mas não enxerga uma RTX 50xx: o veredito
    # não pode dizer "apto" para uma placa que o driver nem reconhece.
    _fingir(monkeypatch, [{"nome": "NVIDIA GeForce RTX 5090", "vram_gb": 32.0}], "560.94")
    r = g.verificar(online=False)
    assert r["estado"] == "critico"
    assert "Blackwell" in r["mensagem"]


def test_driver_acima_do_minimo_mas_antigo_pede_atualizacao(monkeypatch):
    _fingir(monkeypatch, [{"nome": "NVIDIA GeForce RTX 3060", "vram_gb": 12.0}], "531.14")
    r = g.verificar(online=False)
    assert r["estado"] == "atencao"
    assert r["acao"] is not None


def test_driver_em_dia_offline_nao_inventa_veredito_sobre_atualizacao(monkeypatch):
    _fingir(monkeypatch, [{"nome": "NVIDIA GeForce RTX 4070", "vram_gb": 12.0}], "596.36")
    r = g.verificar(online=False)
    assert r["estado"] == "ok"
    assert r["driver_mais_recente"] is None    # sem rede, nada a afirmar
    assert r["online"] is False
    assert "RTX 4070" in r["mensagem"]


def test_driver_ilegivel_nao_vira_acusacao(monkeypatch):
    _fingir(monkeypatch, [{"nome": "NVIDIA GeForce RTX 4070", "vram_gb": 12.0}], None, None)
    r = g.verificar(online=False)
    assert r["estado"] == "desconhecido"


# ---------------------------------------------------------------------------
# Veredito (online) — o extra
# ---------------------------------------------------------------------------
def test_driver_novo_publicado_vira_aviso_e_nao_erro(monkeypatch):
    _fingir(monkeypatch, [{"nome": "NVIDIA GeForce RTX 5090", "vram_gb": 32.0}], "596.36")
    monkeypatch.setattr(g, "consultar_nvidia", lambda linha, **kw: "617.14")
    r = g.verificar(online=True)
    assert r["estado"] == "atencao"
    assert r["driver_mais_recente"] == "617.14"
    assert r["online"] is True
    assert "opcional" in r["mensagem"]


def test_driver_ja_e_o_mais_recente(monkeypatch):
    _fingir(monkeypatch, [{"nome": "NVIDIA GeForce RTX 5090", "vram_gb": 32.0}], "617.14")
    monkeypatch.setattr(g, "consultar_nvidia", lambda linha, **kw: "617.14")
    r = g.verificar(online=True)
    assert r["estado"] == "ok"
    assert "mais recente" in r["mensagem"]


def test_falha_de_rede_nao_derruba_o_diagnostico(monkeypatch):
    _fingir(monkeypatch, [{"nome": "NVIDIA GeForce RTX 5090", "vram_gb": 32.0}], "596.36")

    def explode(*a, **k):
        raise OSError("sem rota para o host")
    monkeypatch.setattr("urllib.request.urlopen", explode)
    monkeypatch.setattr(g, "_ler_cache", lambda linha: None)

    assert g.consultar_nvidia("geforce", timeout=0.1) is None
    r = g.verificar(online=True, timeout=0.1)
    assert r["estado"] == "ok"          # o driver serve; o resto é silêncio
    assert r["driver_mais_recente"] is None


def test_resposta_estranha_da_nvidia_e_descartada(monkeypatch):
    # Se o catálogo mudar de formato, o pior que pode acontecer é não saber.
    monkeypatch.setattr(g, "_ler_cache", lambda linha: None)
    for corpo in (b"{}", b'{"IDS": []}', b'{"IDS":[{"downloadInfo":{"Version":"vem nao"}}]}',
                  b"nem json"):
        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self_inner): return corpo
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Resp())
        assert g.consultar_nvidia("geforce", timeout=0.1) is None


def test_desligar_a_consulta_online_por_ambiente(monkeypatch):
    monkeypatch.setenv("VOX_SEM_CHECAGEM_ONLINE", "1")

    def nao_deveria(*a, **k):
        raise AssertionError("consultou a NVIDIA com a checagem desligada")
    monkeypatch.setattr("urllib.request.urlopen", nao_deveria)
    assert g.consultar_nvidia("geforce") is None


def test_linha_desconhecida_nao_consulta():
    assert g.consultar_nvidia("linha que não existe") is None


def test_resumo_texto_nao_quebra_com_campos_vazios():
    # Vai para log e para o suporte técnico: tem de sair mesmo com meia detecção.
    texto = g.resumo_texto({"estado": "desconhecido", "titulo": "t",
                            "mensagem": "m", "gpus": []})
    assert "[DESCONHECIDO]" in texto
    assert "não consultado" in texto
