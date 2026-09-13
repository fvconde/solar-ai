"""Resumo para o corretor. Testes determinísticos: nunca chamam o Gemini."""

from app.contrato import ImovelSugerido, MensagemHistorico, PerfilLead
from app.lia import prompts


def test_prompt_resumo_inclui_perfil_historico_e_imoveis():
    perfil = PerfilLead(intencao="compra", regiao="Pinheiros", preco_max=900000)
    historico = [
        MensagemHistorico(
            papel="lead",
            texto="Quero morar em Pinheiros, mas não quero térreo.",
            em="2026-09-13T20:00:00Z",
        )
    ]
    imoveis = [
        ImovelSugerido(
            id="SOL-42",
            tipo="apartamento",
            bairro="Pinheiros",
            quartos=2,
            metragem=72,
            preco_venda=850000,
            motivo="Dentro da faixa e da região",
        )
    ]

    prompt = prompts.resumo(perfil, historico, imoveis)

    assert "intencao: compra" in prompt
    assert "regiao: Pinheiros" in prompt
    assert "não quero térreo" in prompt
    assert "SOL-42" in prompt
    assert "Dentro da faixa e da região" in prompt
    assert all(
        secao in prompt
        for secao in ("### perfil", "### orcamento", "### imoveis", "### objecoes", "### proximoPasso")
    )
    assert "Não narre a conversa" in prompt
    assert "devolva `null`" in prompt
