"""Módulo OPCIONAL de revisão assistida (fora do fluxo padrão).

⚠️ NÃO faz parte do fluxo padrão e NUNCA altera texto automaticamente.

Por decisão de projeto, nenhuma IA generativa participa do caminho do texto por
padrão. Quando (e se) ativado, este módulo deve operar sob restrições rígidas:

  - Escopo limitado: apenas sugestões de PONTUAÇÃO e formatação de parágrafos.
    Proibido adicionar, remover ou substituir palavras.
  - Nada é aplicado automaticamente: gera um DIFF lado a lado (original ×
    sugestão); o usuário aprova ou rejeita cada mudança individualmente.
  - Rastreabilidade total: a transcrição bruta é sempre preservada no JSON.
  - Backend configurável: modelo local pequeno (llama.cpp) ou API externa.

Este pacote é um ESQUELETO nesta versão. A implementação virá na v1.2.
"""

from __future__ import annotations


def disponivel() -> bool:
    """Indica que a revisão assistida ainda não está implementada."""
    return False
