"""No consultor do S-15: roteamento, consulta e montagem dos cartoes.

Nada aqui chama o Gemini. O LLM entra por duble e o indice por embutidor
injetado, entao o que se afirma e o comportamento do grafo, nao o do modelo.
"""

import json
import math
from dataclasses import replace

import pytest

from app.contrato import PerfilLead, TurnoRequest
from app.lia import grafo, prompts
from app.lia import indice as indice_imoveis
from app.lia.grafo import (
    IMOVEIS_POR_SUGESTAO,
    MotivoDoImovel,
    SaidaApresentacao,
    SaidaLia,
)
from app.lia.indice import Embutidor, Filtro, Resultado

CONVERSA = "0f0d4f6c-2b3a-4f1e-9a77-5c1e2b8d4a10"
PEDIDO = "Quero apartamento de 2 quartos na zona sul ate 600 mil"


def _registro(**alteracoes) -> dict:
    registro = {
        "id": "IMV-001",
        "tipo": "apartamento",
        "bairro": "Campo Belo",
        "zona": "sul",
        "quartos": 2,
        "banheiros": 1,
        "vagas": 1,
        "metragem": 68,
        "precoVenda": 590000,
        "precoAluguel": 3200,
        "condominio": 640,
        "iptu": 180,
        "descricao": "Apartamento reformado a tres quadras do metro.",
    }
    registro.update(alteracoes)
    return registro


@pytest.fixture
def base(tmp_path):
    registros = [
        _registro(),
        _registro(id="IMV-002", bairro="Saude", metragem=72, precoVenda=560000,
                  descricao="Apartamento de esquina com sol da manha."),
        _registro(id="IMV-003", bairro="Vila Mariana", metragem=64, precoVenda=598000,
                  descricao="Apartamento com varanda e vaga coberta."),
        _registro(id="IMV-004", bairro="Higienopolis", zona="centro", quartos=4,
                  metragem=180, precoVenda=2100000,
                  descricao="Apartamento amplo em predio dos anos 50."),
    ]
    caminho = tmp_path / "imoveis.json"
    caminho.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    return caminho


@pytest.fixture
def embutidor():
    """Vetor por posicao na base: a ordem do resultado nao depende do modelo."""
    ordem: dict[str, int] = {}

    def _vetor(semente: int) -> list[float]:
        return [math.cos(semente + eixo) for eixo in range(8)]

    def documentos(textos: list[str]) -> list[list[float]]:
        for posicao, texto in enumerate(textos):
            ordem[texto] = posicao
        return [_vetor(posicao) for posicao in range(len(textos))]

    def consulta(texto: str) -> list[float]:
        return _vetor(ordem.get(texto, 0))

    return Embutidor(documentos=documentos, consulta=consulta)


@pytest.fixture
def indice(base, embutidor):
    construido = indice_imoveis.construir(embutidor=embutidor, caminho=base)
    yield construido
    indice_imoveis.descartar()


class _Duble:
    """Devolve as saidas na ordem em que o grafo pedir, e conta as chamadas."""

    def __init__(self, *saidas):
        self.saidas = list(saidas)
        self.mensagens = []

    def invoke(self, mensagens):
        self.mensagens.append(mensagens)
        saida = self.saidas.pop(0)

        if isinstance(saida, Exception):
            raise saida

        return saida

    @property
    def chamadas(self) -> int:
        return len(self.mensagens)


def _saida(**alteracoes) -> SaidaLia:
    corpo = {
        "resposta": "Vou separar algumas opcoes.",
        "intencao": "compra",
        "camposExtraidos": {"precoMax": 600000, "quartos": 2, "regiao": "zona sul"},
        "proximaAcao": "sugerir_imoveis",
    }
    corpo.update(alteracoes)
    return SaidaLia.model_validate(corpo)


def _apresentacao(*ids: str, resposta: str = "Separei estas tres.") -> SaidaApresentacao:
    return SaidaApresentacao(
        resposta=resposta,
        motivos=[MotivoDoImovel(id=identificador, motivo=f"combina por {identificador}") for identificador in ids],
    )


def _requisicao(mensagem: str = PEDIDO, **perfil) -> TurnoRequest:
    return TurnoRequest.model_validate(
        {"conversaId": CONVERSA, "mensagem": mensagem, "perfilLead": perfil}
    )


@pytest.fixture
def dublar(monkeypatch):
    """Troca as duas chamadas ao Gemini por um duble unico e devolve ele."""

    def _dublar(*saidas) -> _Duble:
        duble = _Duble(*saidas)
        monkeypatch.setattr(grafo, "_modelo", lambda: duble)
        monkeypatch.setattr(grafo, "_modelo_apresentacao", lambda: duble)
        return duble

    return _dublar


class TestTextoDaConsulta:
    def test_sem_perfil_a_consulta_e_a_mensagem(self):
        assert indice_imoveis.texto_da_consulta(PEDIDO, PerfilLead()) == PEDIDO

    def test_perfil_completa_a_mensagem_curta(self):
        perfil = PerfilLead(intencao="compra", quartos=2, regiao="zona sul")

        texto = indice_imoveis.texto_da_consulta("pode ser", perfil)

        assert texto.startswith("pode ser")
        assert texto.endswith("Imovel de 2 quartos na regiao zona sul para comprar.")

    def test_um_quarto_no_singular(self):
        texto = indice_imoveis.texto_da_consulta("oi", PerfilLead(quartos=1))

        assert "de 1 quarto" in texto

    def test_preco_fica_fora_do_texto_embutido(self):
        perfil = PerfilLead(intencao="compra", preco_min=400000, preco_max=600000)

        texto = indice_imoveis.texto_da_consulta("oi", perfil)

        assert "400000" not in texto
        assert "600000" not in texto

    def test_intencao_indefinida_nao_entra(self):
        texto = indice_imoveis.texto_da_consulta("oi", PerfilLead(intencao="indefinida"))

        assert texto == "oi"


class TestTipoPedido:
    """`tipo` nao existe no PerfilLead, e o contrato esta congelado desde o S-05."""

    def _fala(self, texto: str):
        return type("Fala", (), {"papel": "lead", "texto": texto})()

    @pytest.mark.parametrize(
        "fala,esperado",
        [
            ("quero um apartamento", "apartamento"),
            ("procuro apto de 2 quartos", "apartamento"),
            ("uma casa com quintal", "casa"),
            ("um sobrado seria otimo", "casa"),
            ("cobertura com terraco", "cobertura"),
            ("um studio perto do metro", "studio"),
            ("uma quitinete barata", "studio"),
            ("APARTAMENTO na zona sul", "apartamento"),
            ("apartamento", "apartamento"),
        ],
    )
    def test_reconhece_o_tipo_e_seus_sinonimos(self, fala: str, esperado: str):
        assert indice_imoveis.tipo_pedido(fala) == esperado

    def test_fala_sem_tipo_devolve_none(self):
        assert indice_imoveis.tipo_pedido("quero algo ate 600 mil na zona sul") is None

    @pytest.mark.parametrize(
        "fala",
        ["nao quero apartamento", "qualquer coisa menos casa", "sem ser studio", "nada de cobertura"],
    )
    def test_negacao_nao_vira_filtro(self, fala: str):
        """A mesma pedra do bug de negacao do S-11, agora do lado da busca."""
        assert indice_imoveis.tipo_pedido(fala) is None

    def test_negacao_longe_da_palavra_nao_contamina(self):
        assert indice_imoveis.tipo_pedido("nao tenho pressa, procuro um apartamento") == "apartamento"

    def test_a_mensagem_de_agora_ganha_do_historico(self):
        historico = [self._fala("queria uma casa"), self._fala("na verdade prefiro cobertura")]

        assert indice_imoveis.tipo_pedido("quero um apartamento", historico) == "apartamento"

    def test_o_historico_sustenta_o_turno_que_nao_repete_o_tipo(self):
        historico = [self._fala("quero um apartamento"), self._fala("na zona sul")]

        assert indice_imoveis.tipo_pedido("ate 600 mil", historico) == "apartamento"

    def test_a_fala_mais_recente_do_lead_ganha(self):
        historico = [self._fala("quero uma casa"), self._fala("pensando melhor, um apartamento")]

        assert indice_imoveis.tipo_pedido("ate 600 mil", historico) == "apartamento"

    def test_fala_da_lia_nao_conta_como_pedido(self):
        fala_dela = type("Fala", (), {"papel": "agente", "texto": "temos coberturas otimas"})()

        assert indice_imoveis.tipo_pedido("ate 600 mil", [fala_dela]) is None

    def test_os_sinonimos_cobrem_todo_tipo_da_base_real(self):
        """Tipo novo na base sem sinonimo aqui vira imovel que a busca nunca acha."""
        da_base = {imovel.tipo for imovel in indice_imoveis.carregar()}

        assert da_base <= set(indice_imoveis.SINONIMOS_DE_TIPO.values())


class TestFiltroDeTipo:
    def test_casa_nao_entra_para_quem_pediu_apartamento(self, indice, dublar):
        dublar(_saida(), _apresentacao("IMV-001", "IMV-002", "IMV-003", "IMV-004"))

        resposta = grafo.responder(_requisicao("Quero apartamento de 2 quartos na zona sul"))

        assert all(imovel.tipo == "apartamento" for imovel in resposta.imoveis_sugeridos)

    def test_sem_tipo_na_conversa_todos_os_tipos_concorrem(self, base, embutidor):
        registros = indice_imoveis.carregar(base)
        construido = indice_imoveis.construir(embutidor=embutidor, caminho=base)

        achados = construido.buscar(registros[0].texto, k=10, filtro=Filtro())

        assert len(achados) == 4
        indice_imoveis.descartar()

    def test_o_criterio_de_tipo_aparece_na_negociacao_da_lista_vazia(self):
        bloco = prompts._imoveis([], Filtro(tipo="apartamento", preco_max=100000))

        assert "apartamento" in bloco
        assert "ate R$ 100.000" in bloco


class TestBlocoDeImoveis:
    def _resultados(self, base, quantos: int) -> list[Resultado]:
        imoveis = indice_imoveis.carregar(base)
        return [Resultado(imovel, 0.9 - posicao / 100) for posicao, imovel in enumerate(imoveis[:quantos])]

    def test_ficha_traz_o_id_e_os_numeros(self, base):
        bloco = prompts._imoveis(self._resultados(base, 1), Filtro())

        assert "IMV-001" in bloco
        assert "apartamento no Campo Belo, zona sul" in bloco
        assert "2 quartos, 1 banheiro, 1 vaga, 68 m2" in bloco
        assert "venda R$ 590.000" in bloco
        assert "Apartamento reformado a tres quadras do metro." in bloco

    def test_ordem_da_busca_e_a_ordem_do_bloco(self, base):
        bloco = prompts._imoveis(self._resultados(base, 3), Filtro())

        assert bloco.index("IMV-001") < bloco.index("IMV-002") < bloco.index("IMV-003")

    def test_preco_ausente_nao_vira_zero(self, base):
        imovel = indice_imoveis.carregar(base)[0]
        sem_aluguel = [Resultado(replace(imovel, preco_aluguel=None), 0.9)]

        assert "aluguel" not in prompts._imoveis(sem_aluguel, Filtro())

    def test_lista_vazia_nomeia_os_criterios(self, base):
        filtro = Filtro(intencao="compra", preco_max=600000, quartos=2, regiao="zona sul")

        bloco = prompts._imoveis([], filtro)

        assert "Nenhum." in bloco
        assert "a partir de 2 quartos" in bloco
        assert "regiao zona sul" in bloco
        assert "ate R$ 600.000" in bloco
        assert "para compra" in bloco

    def test_lista_vazia_sem_filtro_diz_que_nao_havia_criterio(self):
        assert prompts.SEM_CRITERIO in prompts._imoveis([], Filtro())

    def test_o_prompt_recebe_o_bloco_e_a_mensagem(self, base):
        texto = prompts.apresentacao(
            PerfilLead(intencao="compra", regiao="zona sul"),
            [],
            PEDIDO,
            self._resultados(base, 2),
            Filtro(regiao="zona sul"),
        )

        assert PEDIDO in texto
        assert "IMV-002" in texto
        assert "{imoveis}" not in texto
        assert "{perfil}" not in texto


PERFIL_FECHADO = {"intencao": "compra", "regiao": "zona sul", "precoMax": 600000}


def _vago(**alteracoes) -> SaidaLia:
    """Turno que nao fecha nada: nenhum essencial da trilha de moradia entra."""
    corpo = {"proximaAcao": "continuar_conversa", "intencao": "indefinida", "camposExtraidos": {"nome": "Rafael"}}
    corpo.update(alteracoes)
    return _saida(**corpo)


class TestRoteamento:
    def test_turno_comum_nao_consulta_nem_gasta_segunda_chamada(self, indice, dublar):
        duble = dublar(_vago())

        resposta = grafo.responder(_requisicao("oi, estou comecando a procurar"))

        assert duble.chamadas == 1
        assert resposta.imoveis_sugeridos == []
        assert resposta.proxima_acao == "continuar_conversa"

    def test_sugerir_imoveis_dispara_busca_e_segunda_chamada(self, indice, dublar):
        duble = dublar(_saida(), _apresentacao("IMV-001", "IMV-002", "IMV-003"))

        resposta = grafo.responder(_requisicao())

        assert duble.chamadas == 2
        assert len(resposta.imoveis_sugeridos) == 3
        assert resposta.proxima_acao == "sugerir_imoveis"

    def test_agendar_reuniao_nao_dispara_busca(self, indice, dublar):
        duble = dublar(_saida(proximaAcao="agendar_reuniao"))

        resposta = grafo.responder(_requisicao())

        assert duble.chamadas == 1
        assert resposta.proxima_acao == "agendar_reuniao"

    def test_indice_fora_do_ar_devolve_o_turno_sem_imoveis(self, dublar):
        indice_imoveis.descartar()
        duble = dublar(_saida())

        resposta = grafo.responder(_requisicao())

        assert duble.chamadas == 1
        assert resposta.imoveis_sugeridos == []
        assert resposta.resposta == "Vou separar algumas opcoes."

    def test_indice_fora_do_ar_nao_derruba_o_turno(self, dublar):
        indice_imoveis.descartar()
        dublar(_saida())

        assert grafo.responder(_requisicao()).resposta


class TestGatilhoDaRegua:
    """O achado do S-12: o turno que fecha o piso ve o piso aberto.

    O modelo montou as lacunas antes de ler a mensagem, entao ele pede mais uma
    pergunta justamente no turno em que ja daria para mostrar imovel. Quem
    desempata e a regua, depois de fundir o perfil.
    """

    def test_o_turno_que_fecha_os_essenciais_busca_mesmo_sem_o_modelo_pedir(self, indice, dublar):
        duble = dublar(
            _saida(proximaAcao="continuar_conversa"),
            _apresentacao("IMV-001", "IMV-002", "IMV-003"),
        )

        resposta = grafo.responder(_requisicao())

        assert duble.chamadas == 2
        assert len(resposta.imoveis_sugeridos) == 3

    def test_e_a_proxima_acao_conta_o_que_aconteceu(self, indice, dublar):
        dublar(
            _saida(proximaAcao="continuar_conversa"),
            _apresentacao("IMV-001", "IMV-002", "IMV-003"),
        )

        assert grafo.responder(_requisicao()).proxima_acao == "sugerir_imoveis"

    def test_perfil_que_ja_estava_fechado_nao_busca_de_novo(self, indice, dublar):
        """Senao toda conversa qualificada custaria duas chamadas por mensagem."""
        duble = dublar(_saida(proximaAcao="continuar_conversa", camposExtraidos={}))

        resposta = grafo.responder(_requisicao("e tem vaga coberta?", **PERFIL_FECHADO))

        assert duble.chamadas == 1
        assert resposta.imoveis_sugeridos == []

    def test_perfil_que_continua_aberto_nao_busca(self, indice, dublar):
        duble = dublar(_vago(camposExtraidos={"regiao": "zona sul"}))

        resposta = grafo.responder(_requisicao("queria na zona sul"))

        assert duble.chamadas == 1
        assert resposta.proxima_acao == "continuar_conversa"

    def test_pedido_de_humano_no_mesmo_turno_ganha_da_regua(self, indice, dublar):
        duble = dublar(_saida(proximaAcao="agendar_reuniao"))

        resposta = grafo.responder(_requisicao())

        assert duble.chamadas == 1
        assert resposta.proxima_acao == "agendar_reuniao"

    def test_investidor_fechado_vai_para_o_especialista_e_nao_para_a_vitrine(self, indice, dublar):
        duble = dublar(
            _saida(
                proximaAcao="direcionar_especialista",
                intencao="investimento",
                camposExtraidos={"precoMax": 600000, "expectativaRetorno": "0,8% ao mes"},
            )
        )

        resposta = grafo.responder(_requisicao("tenho 600 mil e quero 0,8% ao mes"))

        assert duble.chamadas == 1
        assert resposta.proxima_acao == "direcionar_especialista"


class TestBuscaDoTurno:
    def test_o_filtro_sai_do_perfil_ja_fundido_com_este_turno(self, indice, dublar):
        """O aceite do card: os tres criterios chegam todos na mensagem de agora."""
        dublar(_saida(), _apresentacao("IMV-001", "IMV-002", "IMV-003"))

        resposta = grafo.responder(_requisicao())

        assert {imovel.id for imovel in resposta.imoveis_sugeridos} == {
            "IMV-001",
            "IMV-002",
            "IMV-003",
        }

    def test_imovel_fora_do_filtro_nao_entra(self, indice, dublar):
        dublar(_saida(), _apresentacao("IMV-001", "IMV-002", "IMV-003", "IMV-004"))

        resposta = grafo.responder(_requisicao())

        assert "IMV-004" not in {imovel.id for imovel in resposta.imoveis_sugeridos}

    def test_no_maximo_tres_imoveis(self, indice, dublar):
        dublar(
            _saida(camposExtraidos={}),
            _apresentacao("IMV-001", "IMV-002", "IMV-003", "IMV-004"),
        )

        resposta = grafo.responder(_requisicao())

        assert len(resposta.imoveis_sugeridos) <= IMOVEIS_POR_SUGESTAO

    def test_busca_vazia_vira_negociacao_e_nao_sugestao(self, indice, dublar):
        duble = dublar(
            _saida(camposExtraidos={"precoMax": 100000, "quartos": 2, "regiao": "zona sul"}),
            SaidaApresentacao(resposta="Nao achei nada ate 100 mil. Da para subir?"),
        )

        resposta = grafo.responder(_requisicao())

        assert duble.chamadas == 2
        assert resposta.imoveis_sugeridos == []
        assert resposta.proxima_acao == "continuar_conversa"
        assert resposta.resposta.startswith("Nao achei nada")

    def test_a_fala_da_apresentacao_substitui_a_do_primeiro_no(self, indice, dublar):
        dublar(_saida(), _apresentacao("IMV-001", resposta="Separei uma no Campo Belo."))

        assert grafo.responder(_requisicao()).resposta == "Separei uma no Campo Belo."


class TestCartoes:
    def test_o_cartao_copia_a_ficha_e_o_motivo_do_llm(self, indice, dublar):
        dublar(_saida(), _apresentacao("IMV-001"))

        imovel = grafo.responder(_requisicao()).imoveis_sugeridos[0]

        assert imovel.id == "IMV-001"
        assert imovel.tipo == "apartamento"
        assert imovel.bairro == "Campo Belo"
        assert imovel.quartos == 2
        assert imovel.metragem == 68
        assert imovel.preco_venda == 590000
        assert imovel.motivo == "combina por IMV-001"

    def test_imovel_sem_motivo_fica_de_fora(self, indice, dublar):
        dublar(_saida(), _apresentacao("IMV-002"))

        ids = [imovel.id for imovel in grafo.responder(_requisicao()).imoveis_sugeridos]

        assert ids == ["IMV-002"]

    def test_motivo_de_imovel_que_a_busca_nao_achou_e_ignorado(self, indice, dublar):
        dublar(_saida(), _apresentacao("IMV-001", "IMV-999"))

        ids = [imovel.id for imovel in grafo.responder(_requisicao()).imoveis_sugeridos]

        assert ids == ["IMV-001"]

    def test_a_ordem_e_a_da_busca_e_nao_a_do_llm(self, indice, dublar):
        dublar(_saida(), _apresentacao("IMV-003", "IMV-001", "IMV-002"))

        ids = [imovel.id for imovel in grafo.responder(_requisicao()).imoveis_sugeridos]

        assert ids == ["IMV-001", "IMV-002", "IMV-003"]


class TestFalhaDaApresentacao:
    def test_segunda_chamada_falha_e_o_turno_sobrevive_sem_imoveis(self, indice, dublar):
        duble = dublar(_saida(), grafo.LiaIndisponivelError("429 quota", cota=True))

        resposta = grafo.responder(_requisicao())

        assert duble.chamadas == 2
        assert resposta.imoveis_sugeridos == []
        assert resposta.resposta == "Vou separar algumas opcoes."
        assert resposta.proxima_acao == "continuar_conversa"

    def test_primeira_chamada_falha_e_o_turno_falha_alto(self, indice, dublar):
        dublar(grafo.LiaIndisponivelError("429 quota", cota=True))

        with pytest.raises(grafo.LiaIndisponivelError):
            grafo.responder(_requisicao())

    def test_campos_extraidos_e_score_sobrevivem_a_apresentacao(self, indice, dublar):
        dublar(_saida(), _apresentacao("IMV-001"))

        resposta = grafo.responder(_requisicao())

        assert resposta.campos_extraidos.preco_max == 600000
        assert resposta.campos_extraidos.regiao == "zona sul"
        assert resposta.campos_extraidos.score == 75
