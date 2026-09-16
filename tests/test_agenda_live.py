"""Amostra live da leitura de linguagem natural sobre a agenda.

Os gates de seguranca e ids inventados ficam nos testes offline; aqui gastamos
apenas duas chamadas para confirmar a interpretacao que depende do modelo.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.contrato import PerfilLead, SlotOferecido, TurnoRequest
from app.lia.grafo import responder


CONVERSA = UUID("6b2611ec-df4a-4f1f-a443-96059cc5e1cd")


def _requisicao(mensagem: str) -> TurnoRequest:
    horarios = (
        (41, datetime(2026, 9, 17, 12, tzinfo=timezone.utc)),
        (42, datetime(2026, 9, 17, 18, tzinfo=timezone.utc)),
        (43, datetime(2026, 9, 18, 14, tzinfo=timezone.utc)),
    )

    return TurnoRequest(
        conversa_id=CONVERSA,
        mensagem=mensagem,
        perfil_lead=PerfilLead(
            nome="Marina",
            intencao="compra",
            regiao="zona sul",
            preco_max=700000,
        ),
        agenda=[
            SlotOferecido(id=id_, inicio=inicio, fim=inicio + timedelta(hours=1))
            for id_, inicio in horarios
        ],
    )


@pytest.mark.llm
def test_escolhe_o_unico_horario_descrito_em_linguagem_natural(ritmo) -> None:
    resposta = responder(_requisicao("quinta-feira as tres da tarde fica otimo"))

    assert resposta.slot_escolhido == 42, resposta.resposta


@pytest.mark.llm
def test_expressao_ambigua_nao_escolhe_slot(ritmo) -> None:
    resposta = responder(_requisicao("pode ser na semana que vem"))

    assert resposta.slot_escolhido is None, resposta.resposta
