"""S-34: regex, mapa por turno e as duas fronteiras de saida ao Google."""

from collections.abc import Sequence

import pytest
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.contrato import TurnoRequest
from app.lia import grafo
from app.lia.grafo import CamposExtraidosLLM, SaidaApresentacao, SaidaLia
from app.lia.indice import Embutidor, Imovel, Indice
from app.lia.mascaramento import MascaradorPII

CPF = "111.222.333-44"
TELEFONE = "(11) 90000-0000"


@pytest.mark.parametrize(
    "frase,tokens",
    [
        ("Meu CPF e 111.222.333-44.", ["[CPF_1]"]),
        ("CPF: 11122233344", ["[CPF_1]"]),
        ("Meu telefone e (11) 90000-0000.", ["[TELEFONE_1]"]),
        ("11900000000", ["[TELEFONE_1]"]),
        ("Pode ligar no 90000-0000.", ["[TELEFONE_1]"]),
        ("Telefone 900000000", ["[TELEFONE_1]"]),
        ("E-mail: pessoa@example.test", ["[EMAIL_1]"]),
        ("Meu CEP e 00000-000.", ["[CEP_1]"]),
        ("CEP 00000000", ["[CEP_1]"]),
        ("Quero 3 quartos por ate R$ 800.000; protocolo 12345678901.", []),
    ],
)
def test_dez_frases(frase: str, tokens: list[str]) -> None:
    mascarador = MascaradorPII()
    mascarada = mascarador.mascarar(frase)

    assert list(mascarador.mapa) == tokens
    assert mascarador.desmascarar(mascarada) == frase


def test_nome_fica_em_texto_claro_por_decisao_de_produto() -> None:
    assert MascaradorPII().mascarar("Meu nome e Marina.") == "Meu nome e Marina."


class _Duble:
    def __init__(self, *saidas):
        self.saidas = list(saidas)
        self.chamadas: list[list[BaseMessage]] = []

    def invoke(self, mensagens: list[BaseMessage]):
        self.chamadas.append(mensagens)
        return self.saidas.pop(0)


def _texto(mensagens: Sequence[BaseMessage]) -> str:
    return "\n".join(
        mensagem.content for mensagem in mensagens if isinstance(mensagem.content, str)
    )


def test_payloads_de_geracao_e_embedding_sao_mascarados_e_resposta_e_restaurada(
    monkeypatch,
) -> None:
    duble = _Duble(
        SaidaLia(
            resposta="Vou procurar e manter [CPF_1] e [TELEFONE_1] protegidos.",
            intencao="compra",
            campos_extraidos=CamposExtraidosLLM(
                nome="Marina", preco_max=600000, quartos=2, regiao="zona sul"
            ),
            proxima_acao="sugerir_imoveis",
        ),
        SaidaApresentacao(
            resposta="Confirme [CPF_1] e [TELEFONE_1].",
            motivos=[],
        ),
    )
    consultas: list[str] = []

    def consultar(texto: str) -> list[float]:
        consultas.append(texto)
        return [1.0, 0.0]

    indice = Indice(
        imoveis=(
            Imovel(
                id="IMV-001",
                tipo="apartamento",
                bairro="Campo Belo",
                zona="sul",
                quartos=2,
                banheiros=1,
                vagas=1,
                metragem=68,
                preco_venda=590000,
                preco_aluguel=None,
                condominio=600,
                iptu=180,
                descricao="Imovel ficticio para teste.",
            ),
        ),
        vetores=((1.0, 0.0),),
        embutidor=Embutidor(documentos=lambda _textos: [], consulta=consultar),
        modelo="injetado",
        origem="injetado",
    )
    monkeypatch.setattr(grafo, "_modelo", lambda: duble)
    monkeypatch.setattr(grafo, "_modelo_apresentacao", lambda: duble)
    monkeypatch.setattr(grafo.indice_imoveis, "atual", lambda: indice)

    resposta = grafo.responder(
        TurnoRequest.model_validate(
            {
                "conversaId": "0f0d4f6c-2b3a-4f1e-9a77-5c1e2b8d4a10",
                "mensagem": f"Meu CPF e {CPF}, telefone {TELEFONE}. Quero comprar.",
                "perfilLead": {"nome": "Marina"},
            }
        )
    )

    payloads = [_texto(chamada) for chamada in duble.chamadas]
    assert all(CPF not in payload and TELEFONE not in payload for payload in payloads)
    assert all("[CPF_1]" in payload and "[TELEFONE_1]" in payload for payload in payloads)
    assert "Marina" in payloads[0]
    assert consultas == [
        "Meu CPF e [CPF_1], telefone [TELEFONE_1]. Quero comprar.\n\n"
        "Imovel de 2 quartos na regiao zona sul para comprar."
    ]
    assert resposta.resposta == f"Confirme {CPF} e {TELEFONE}."


@pytest.mark.llm
def test_payload_pii_tokenizado_ao_vivo_e_resposta_restaurada(ritmo) -> None:
    class Espiao:
        def __init__(self, modelo) -> None:
            self.modelo = modelo
            self.mensagens: list[BaseMessage] = []

        def invoke(self, mensagens: list[BaseMessage]):
            self.mensagens = mensagens
            return self.modelo.invoke(mensagens)

    mascarador = MascaradorPII()
    espiao = Espiao(grafo._modelo())
    saida = grafo._invocar(
        espiao,
        [
            SystemMessage(
                content="Devolva a saida estruturada solicitada. Preserve literalmente os tokens entre colchetes."
            ),
            HumanMessage(
                content=(
                    f"Responda confirmando exatamente meu CPF {CPF} e telefone {TELEFONE}. "
                    "Use intencao indefinida, camposExtraidos vazio e proximaAcao continuar_conversa."
                )
            ),
        ],
        SaidaLia,
        mascarador,
    )

    payload = _texto(espiao.mensagens)
    assert CPF not in payload and TELEFONE not in payload
    assert "[CPF_1]" in payload and "[TELEFONE_1]" in payload
    assert CPF in saida.resposta and TELEFONE in saida.resposta
