"""Extracao estruturada de campos e intencao — card S-11.

Cada caso e um turno isolado contra o Gemini de verdade: perfil e historico ja
montados, uma mensagem, asseracoes sobre o que voltou em camposExtraidos.

A asserção que da nome ao card e a negativa: todo campo que o caso nao declara
em `extrai` ou `contem` tem que voltar nulo. `tolera` isenta um campo do juizo
quando a leitura dele e legitimamente ambigua.

    pytest -m llm            # roda esta suite; ~1 chamada por caso
    pytest -m llm -k negacao # roda um caso so
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.contrato import CamposExtraidos, TurnoRequest
from app.lia import responder

SEMPRE_PREENCHIDO = frozenset({"score"})


@dataclass(frozen=True)
class Caso:
    nome: str
    mensagem: str
    perfil: dict = field(default_factory=dict)
    historico: tuple[tuple[str, str], ...] = ()
    intencao: str | None = None
    proxima_acao: str | None = None
    extrai: dict = field(default_factory=dict)
    contem: dict = field(default_factory=dict)
    tolera: tuple[str, ...] = ()

    def requisicao(self) -> TurnoRequest:
        base = datetime.now(timezone.utc) - timedelta(minutes=len(self.historico))

        return TurnoRequest.model_validate(
            {
                "conversaId": str(uuid4()),
                "mensagem": self.mensagem,
                "perfilLead": self.perfil,
                "historico": [
                    {"papel": papel, "texto": texto, "em": base + timedelta(minutes=i)}
                    for i, (papel, texto) in enumerate(self.historico)
                ],
            }
        )

    def permitidos(self) -> set[str]:
        return set(self.extrai) | set(self.contem) | set(self.tolera) | SEMPRE_PREENCHIDO


CASOS = [
    Caso(
        nome="saudacao-sem-dado",
        mensagem="oi, boa tarde",
        intencao="indefinida",
    ),
    Caso(
        nome="pergunta-institucional",
        mensagem="voces cobram taxa pra intermediar?",
        intencao="indefinida",
    ),
    Caso(
        nome="so-a-regiao",
        mensagem="queria alguma coisa na Vila Madalena",
        contem={"regiao": "Vila Madalena"},
    ),
    Caso(
        nome="recusa-orcamento-nao-vira-preco",
        perfil={"intencao": "compra", "regiao": "Moema"},
        historico=(
            ("lead", "quero comprar em Moema"),
            ("agente", "Qual faixa de preco voce tem em mente?"),
        ),
        mensagem="prefiro nao falar de valores agora",
        intencao="compra",
    ),
    Caso(
        nome="nao-copia-o-perfil",
        perfil={"intencao": "compra", "precoMax": 650000, "regiao": "Butanta", "nome": "Rafael"},
        historico=(
            ("lead", "sou o Rafael, quero comprar no Butanta ate 650 mil"),
            ("agente", "Anotado. Quantos quartos voce precisa?"),
        ),
        mensagem="preciso de 3 quartos",
        intencao="compra",
        extrai={"quartos": 3},
    ),
    Caso(
        nome="teto-de-compra-em-reais",
        perfil={"intencao": "compra"},
        historico=(
            ("lead", "quero comprar um apartamento"),
            ("agente", "Qual faixa de preco voce tem em mente?"),
        ),
        mensagem="meu teto e 500 mil",
        intencao="compra",
        extrai={"preco_max": 500000},
    ),
    Caso(
        nome="aluguel-lido-como-mensal",
        perfil={"intencao": "aluguel"},
        historico=(
            ("lead", "preciso alugar um apartamento"),
            ("agente", "Quanto voce pretende pagar por mes?"),
        ),
        mensagem="ate 3 mil de aluguel",
        intencao="aluguel",
        extrai={"preco_max": 3000},
    ),
    Caso(
        nome="piso-nao-vira-teto",
        perfil={"intencao": "compra"},
        historico=(
            ("lead", "quero comprar um apartamento"),
            ("agente", "Qual faixa de preco voce tem em mente?"),
        ),
        mensagem="nao quero nada abaixo de 300 mil",
        intencao="compra",
        extrai={"preco_min": 300000},
    ),
    Caso(
        nome="faixa-com-dois-limites",
        perfil={"intencao": "compra"},
        historico=(
            ("lead", "quero comprar um apartamento"),
            ("agente", "Qual faixa de preco voce tem em mente?"),
        ),
        mensagem="entre 400 e 600 mil",
        intencao="compra",
        extrai={"preco_min": 400000, "preco_max": 600000},
    ),
    Caso(
        nome="negacao-de-regiao-nao-vira-regiao",
        perfil={"intencao": "compra"},
        historico=(
            ("lead", "quero comprar um apartamento"),
            ("agente", "Tem alguma regiao em mente?"),
        ),
        mensagem="qualquer lugar menos a zona leste",
        intencao="compra",
    ),
    Caso(
        nome="retificacao-substitui-o-valor-antigo",
        perfil={"intencao": "compra", "quartos": 2, "regiao": "Santana"},
        historico=(
            ("lead", "quero 2 quartos em Santana"),
            ("agente", "Anotado. Qual faixa de preco voce tem em mente?"),
        ),
        mensagem="na verdade me enganei, sao 3 quartos",
        intencao="compra",
        extrai={"quartos": 3},
    ),
    Caso(
        nome="intencao-compra-para-morar",
        mensagem="quero comprar um apartamento pra morar com a familia",
        intencao="compra",
    ),
    Caso(
        nome="intencao-investimento-disfarcada-de-compra",
        mensagem="quero comprar um apto pra por pra alugar depois",
        intencao="investimento",
    ),
    Caso(
        nome="intencao-ambigua-nao-chuta",
        mensagem="to dando uma olhada em imoveis",
        intencao="indefinida",
    ),
    Caso(
        nome="follow-up-nao-zera-a-intencao",
        perfil={"intencao": "compra", "regiao": "Tatuape", "precoMax": 500000, "quartos": 2},
        historico=(
            ("lead", "quero comprar um apto de 2 quartos no Tatuape ate 500 mil"),
            ("agente", "Anotado. Quando voce pretende se mudar?"),
            ("lead", "ainda nao sei, vou pensar melhor"),
            ("agente", "Sem problema. Quando quiser retomar e so me chamar."),
        ),
        mensagem="oi, voltei. ainda tem alguma coisa naquela faixa?",
        intencao="compra",
    ),
    Caso(
        nome="expectativa-de-retorno-verbatim",
        perfil={"intencao": "investimento", "precoMax": 400000},
        historico=(
            ("lead", "quero investir, tenho ate 400 mil"),
            ("agente", "Que retorno voce espera desse valor?"),
        ),
        mensagem="uns 0,8% ao mes de aluguel liquido",
        intencao="investimento",
        contem={"expectativa_retorno": "0,8"},
    ),
    Caso(
        nome="valorizacao-de-quem-vai-morar-nao-e-expectativa",
        perfil={"intencao": "compra", "regiao": "Perdizes"},
        historico=(
            ("lead", "quero comprar em Perdizes pra morar"),
            ("agente", "Quantos quartos voce precisa?"),
        ),
        mensagem="2 quartos. e bom que valorize com o tempo, ne",
        intencao="compra",
        extrai={"quartos": 2},
    ),
    Caso(
        nome="cpf-oferecido-nao-vira-campo",
        perfil={"intencao": "compra", "regiao": "Vila Mariana"},
        historico=(
            ("lead", "quero comprar uma casa na Vila Mariana"),
            ("agente", "Quantos quartos voce precisa?"),
        ),
        mensagem="meu CPF e 123.456.789-00, ja pode adiantar o cadastro",
        intencao="compra",
    ),
    Caso(
        nome="prazo-curto-e-urgencia-alta",
        perfil={"intencao": "aluguel", "regiao": "Pinheiros"},
        historico=(
            ("lead", "preciso alugar em Pinheiros"),
            ("agente", "Para quando voce precisa?"),
        ),
        mensagem="preciso entrar no dia 30 desse mes",
        intencao="aluguel",
        extrai={"urgencia": "alta"},
    ),
    Caso(
        nome="sem-pressa-e-urgencia-baixa",
        perfil={"intencao": "compra"},
        historico=(
            ("lead", "quero comprar um apartamento"),
            ("agente", "Quando voce pretende decidir?"),
        ),
        mensagem="sem pressa nenhuma, ano que vem talvez",
        intencao="compra",
        extrai={"urgencia": "baixa"},
    ),
    Caso(
        nome="handoff-lead-vago-nao-vai-para-corretor",
        historico=(
            ("lead", "oi"),
            ("agente", "Ola. Voce procura um imovel para comprar ou para alugar?"),
            ("lead", "sei la, to so olhando"),
            ("agente", "Tem alguma regiao que chama mais a sua atencao?"),
            ("lead", "nao sei ainda"),
            ("agente", "Tudo bem. Qual faixa de preco voce tem em mente?"),
        ),
        mensagem="depende do preco",
        intencao="indefinida",
        proxima_acao="continuar_conversa",
    ),
    Caso(
        nome="handoff-lead-sem-nenhum-dado-nao-vai-para-corretor",
        historico=(
            ("lead", "oi"),
            ("agente", "Ola. Voce procura um imovel para comprar ou para alugar?"),
            ("lead", "sei la, to so olhando"),
            ("agente", "Tem alguma regiao que chama mais a sua atencao?"),
        ),
        mensagem="nao sei ainda",
        intencao="indefinida",
        proxima_acao="continuar_conversa",
    ),
    Caso(
        nome="handoff-pedido-explicito-de-humano",
        perfil={"intencao": "compra", "regiao": "Vila Mariana"},
        historico=(
            ("lead", "quero comprar uma casa na Vila Mariana"),
            ("agente", "Quantos quartos voce precisa?"),
        ),
        mensagem="prefiro falar com uma pessoa de verdade",
        intencao="compra",
        proxima_acao="agendar_reuniao",
    ),
    Caso(
        nome="handoff-investidor-completo-vai-ao-especialista",
        perfil={
            "intencao": "investimento",
            "precoMax": 400000,
            "expectativaRetorno": "0,8% ao mes",
        },
        historico=(
            ("lead", "quero investir, tenho ate 400 mil"),
            ("agente", "Que retorno voce espera desse valor?"),
            ("lead", "uns 0,8% ao mes de aluguel liquido"),
            ("agente", "Anotado. Voce ja investe em imoveis hoje?"),
        ),
        mensagem="ainda nao, seria o primeiro",
        intencao="investimento",
        proxima_acao="direcionar_especialista",
    ),
    Caso(
        nome="nome-so-o-primeiro",
        perfil={"intencao": "compra"},
        historico=(
            ("lead", "quero comprar um apartamento"),
            ("agente", "Como voce se chama?"),
        ),
        mensagem="sou o Rafael Meneguelli, prazer",
        intencao="compra",
        extrai={"nome": "Rafael"},
    ),
]


def _igual(obtido, esperado) -> bool:
    if isinstance(esperado, str):
        return isinstance(obtido, str) and obtido.strip().casefold() == esperado.casefold()
    return obtido == esperado


@pytest.mark.llm
@pytest.mark.parametrize("caso", CASOS, ids=lambda caso: caso.nome)
def test_extrai_so_o_que_o_lead_disse(caso: Caso, ritmo) -> None:
    resposta = responder(caso.requisicao())
    campos = resposta.campos_extraidos.model_dump()

    if caso.intencao is not None:
        assert resposta.intencao == caso.intencao, f"resposta da Lia: {resposta.resposta}"

    if caso.proxima_acao is not None:
        assert resposta.proxima_acao == caso.proxima_acao, f"resposta da Lia: {resposta.resposta}"

    for nome, esperado in caso.extrai.items():
        assert _igual(campos[nome], esperado), f"{nome}: esperava {esperado!r}, veio {campos[nome]!r}"

    for nome, trecho in caso.contem.items():
        obtido = campos[nome]
        assert obtido is not None, f"{nome}: esperava conter {trecho!r}, veio nulo"
        assert trecho.casefold() in obtido.casefold(), f"{nome}: {obtido!r} nao contem {trecho!r}"

    permitidos = caso.permitidos()
    inventados = {
        nome: valor
        for nome, valor in campos.items()
        if valor is not None and nome not in permitidos
    }

    assert not inventados, f"campos que ninguem mencionou: {inventados}"
    assert campos["score"] is not None, "o score tem que sair em todo turno"


def test_todo_campo_do_contrato_tem_ao_menos_um_caso() -> None:
    cobertos = {nome for caso in CASOS for nome in (*caso.extrai, *caso.contem)}
    faltando = set(CamposExtraidos.model_fields) - cobertos - SEMPRE_PREENCHIDO

    assert not faltando, f"campos sem caso que os preencha: {sorted(faltando)}"
