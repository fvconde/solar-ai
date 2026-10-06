"""Teste de falha intencional determinística para validação do gate de CI do agente.

Card: S-28 (Execução: 91454301-5111-4a21-82f9-7d47a4ea0cce)
Objetivo: Prova vermelha para comprovar que o workflow ci.yml bloqueia o pipeline quando um teste falha.
Esta branch (teste/S-28-gate-vermelho) é descartável e NÃO deve ser integrada à feature ou main.
"""


def test_s28_gate_vermelho_falha_intencional():
    """Falha intencional determinística sem dependência de LLM, rede, chave ou dados."""
    assert False, "Falha intencional para validacao do gate de CI (S-28)"
