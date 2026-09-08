"""Regua de qualificacao do S-12: score e lacunas. Nao chama o Gemini.

O que o S-11 nao podia afirmar — o valor do score — vira asserção aqui, porque
a regua e deterministica e nao passa pelo modelo.
"""

from typing import get_args

import pytest

from app.contrato import CamposExtraidos, PerfilLead, Urgencia
from app.lia import qualificacao
from app.lia.grafo import CamposExtraidosLLM
from app.lia.qualificacao import INVESTIMENTO, MORADIA

MORADOR_COMPLETO = {
    "intencao": "compra",
    "regiao": "Butanta",
    "preco_max": 650000,
    "urgencia": "alta",
    "quartos": 3,
    "nome": "Rafael",
}

INVESTIDOR_COMPLETO = {
    "intencao": "investimento",
    "preco_max": 400000,
    "expectativa_retorno": "0,8% ao mes",
    "regiao": "Tatuape",
    "urgencia": "alta",
    "nome": "Carla",
}


def _perfil(**campos) -> PerfilLead:
    return PerfilLead.model_validate(campos)


class TestTabelaDeSinais:
    @pytest.mark.parametrize("tabela", [MORADIA, INVESTIMENTO], ids=["moradia", "investimento"])
    def test_cada_trilha_soma_cem(self, tabela):
        assert sum(sinal.peso for sinal in tabela) == 100

    @pytest.mark.parametrize("tabela", [MORADIA, INVESTIMENTO], ids=["moradia", "investimento"])
    def test_pesos_em_ordem_decrescente(self, tabela):
        pesos = [sinal.peso for sinal in tabela]

        assert pesos == sorted(pesos, reverse=True)

    @pytest.mark.parametrize("tabela", [MORADIA, INVESTIMENTO], ids=["moradia", "investimento"])
    def test_nenhum_sinal_repetido(self, tabela):
        campos = [sinal.campo for sinal in tabela]

        assert len(campos) == len(set(campos))

    def test_todo_campo_do_perfil_e_coberto_por_alguma_trilha(self):
        cobertos = {sinal.campo for sinal in MORADIA + INVESTIMENTO}
        cobertos |= {"preco_min", "preco_max", "score"}
        cobertos.discard("preco")

        assert set(PerfilLead.model_fields) <= cobertos

    @pytest.mark.parametrize("tabela", [MORADIA, INVESTIMENTO], ids=["moradia", "investimento"])
    def test_graduacao_cobre_o_enum_e_topa_no_peso(self, tabela):
        for sinal in tabela:
            if sinal.graduacao is None:
                continue

            assert set(sinal.graduacao) == set(get_args(Urgencia))
            assert max(sinal.graduacao.values()) == sinal.peso

    def test_investimento_troca_quartos_por_expectativa(self):
        moradia = {sinal.campo for sinal in MORADIA}
        investimento = {sinal.campo for sinal in INVESTIMENTO}

        assert moradia - investimento == {"quartos"}
        assert investimento - moradia == {"expectativa_retorno"}


class TestTrilha:
    def test_investidor_usa_a_trilha_de_investimento(self):
        assert qualificacao.trilha(_perfil(intencao="investimento")) is INVESTIMENTO

    @pytest.mark.parametrize("intencao", ["compra", "aluguel", "indefinida", None])
    def test_o_resto_usa_moradia(self, intencao):
        assert qualificacao.trilha(_perfil(intencao=intencao)) is MORADIA


class TestPontuar:
    def test_perfil_vazio_vale_zero(self):
        assert qualificacao.pontuar(PerfilLead()) == 0

    def test_intencao_indefinida_nao_pontua(self):
        assert qualificacao.pontuar(_perfil(intencao="indefinida")) == 0

    def test_intencao_definida_vale_vinte_e_cinco(self):
        assert qualificacao.pontuar(_perfil(intencao="compra")) == 25

    @pytest.mark.parametrize("completo", [MORADOR_COMPLETO, INVESTIDOR_COMPLETO])
    def test_perfil_completo_com_urgencia_alta_fecha_em_cem(self, completo):
        assert qualificacao.pontuar(_perfil(**completo)) == 100

    def test_score_nunca_passa_de_cem(self):
        perfil = _perfil(**MORADOR_COMPLETO, preco_min=300000)

        assert qualificacao.pontuar(perfil) == 100

    @pytest.mark.parametrize(
        ("urgencia", "esperado"), [("alta", 15), ("media", 9), ("baixa", 5)]
    )
    def test_urgencia_pontua_por_fator(self, urgencia: str, esperado: int):
        assert qualificacao.pontuar(_perfil(urgencia=urgencia)) == esperado

    def test_urgencia_ausente_nao_pontua(self):
        assert qualificacao.pontuar(PerfilLead()) == 0

    @pytest.mark.parametrize("campo", ["preco_min", "preco_max"])
    def test_qualquer_ponta_da_faixa_preenche_preco(self, campo: str):
        assert qualificacao.pontuar(_perfil(**{campo: 500000})) == 20

    def test_faixa_com_duas_pontas_nao_pontua_em_dobro(self):
        assert qualificacao.pontuar(_perfil(preco_min=400000, preco_max=600000)) == 20

    def test_quartos_nao_pontua_para_investidor(self):
        com_quartos = _perfil(intencao="investimento", quartos=2)

        assert qualificacao.pontuar(com_quartos) == 25

    def test_expectativa_nao_pontua_para_morador(self):
        com_expectativa = _perfil(intencao="compra", expectativa_retorno="0,8% ao mes")

        assert qualificacao.pontuar(com_expectativa) == 25

    def test_investidor_pronto_para_o_especialista_pontua_alto(self):
        perfil = _perfil(
            intencao="investimento", preco_max=400000, expectativa_retorno="0,8% ao mes"
        )

        assert qualificacao.pontuar(perfil) == 65

    def test_lead_vago_fica_embaixo_do_decidido(self):
        vago = _perfil(intencao="indefinida")
        decidido = _perfil(**MORADOR_COMPLETO)

        assert qualificacao.pontuar(vago) < qualificacao.pontuar(decidido)

    def test_score_e_reproduzivel(self):
        perfil = _perfil(**MORADOR_COMPLETO)

        assert qualificacao.pontuar(perfil) == qualificacao.pontuar(perfil)

    def test_preencher_campo_nunca_baixa_o_score(self):
        antes = qualificacao.pontuar(_perfil(intencao="compra", regiao="Moema"))
        depois = qualificacao.pontuar(
            _perfil(intencao="compra", regiao="Moema", quartos=2)
        )

        assert depois > antes


class TestLacunas:
    def test_perfil_vazio_abre_a_trilha_inteira(self):
        assert qualificacao.lacunas(PerfilLead()) == MORADIA

    def test_perfil_completo_nao_tem_lacuna(self):
        assert qualificacao.lacunas(_perfil(**MORADOR_COMPLETO)) == ()

    def test_investidor_completo_nao_tem_lacuna(self):
        assert qualificacao.lacunas(_perfil(**INVESTIDOR_COMPLETO)) == ()

    def test_a_primeira_lacuna_e_a_que_mais_vale(self):
        perfil = _perfil(intencao="compra", quartos=2, nome="Rafael")
        primeira = qualificacao.lacunas(perfil)[0]

        assert primeira.campo == "regiao"

    def test_intencao_indefinida_continua_sendo_lacuna(self):
        campos = [sinal.campo for sinal in qualificacao.lacunas(_perfil(intencao="indefinida"))]

        assert campos[0] == "intencao"

    def test_investidor_e_perguntado_sobre_retorno_antes_de_regiao(self):
        perfil = _perfil(intencao="investimento", preco_max=400000)
        campos = [sinal.campo for sinal in qualificacao.lacunas(perfil)]

        assert campos.index("expectativa_retorno") < campos.index("regiao")

    def test_investidor_nunca_e_perguntado_sobre_quartos(self):
        campos = {sinal.campo for sinal in qualificacao.lacunas(_perfil(intencao="investimento"))}

        assert "quartos" not in campos

    def test_urgencia_baixa_nao_e_lacuna(self):
        campos = {sinal.campo for sinal in qualificacao.lacunas(_perfil(urgencia="baixa"))}

        assert "urgencia" not in campos

    def test_essenciais_da_moradia_sao_intencao_regiao_e_preco(self):
        campos = {sinal.campo for sinal in MORADIA if sinal.essencial}

        assert campos == {"intencao", "regiao", "preco"}

    def test_essenciais_do_investimento_espelham_o_direcionar_especialista(self):
        campos = {sinal.campo for sinal in INVESTIMENTO if sinal.essencial}

        assert campos == {"intencao", "preco", "expectativa_retorno"}

    def test_investidor_com_ticket_e_expectativa_nao_tem_essencial_aberto(self):
        perfil = _perfil(
            intencao="investimento", preco_max=400000, expectativa_retorno="0,8% ao mes"
        )

        assert qualificacao.lacunas_essenciais(perfil) == ()
        assert qualificacao.lacunas(perfil) != ()

    def test_morador_sem_preco_ainda_tem_essencial_aberto(self):
        perfil = _perfil(intencao="compra", regiao="Moema", quartos=2, nome="Rafael")
        campos = {sinal.campo for sinal in qualificacao.lacunas_essenciais(perfil)}

        assert campos == {"preco"}

    @pytest.mark.parametrize("tabela", [MORADIA, INVESTIMENTO], ids=["moradia", "investimento"])
    def test_essencial_e_sempre_dos_sinais_que_mais_valem(self, tabela):
        essenciais = [sinal.essencial for sinal in tabela]

        assert essenciais == sorted(essenciais, reverse=True)

    def test_a_trilha_de_investimento_tem_desfecho(self):
        perfil = _perfil(intencao="investimento")

        assert qualificacao.desfecho_da_trilha(perfil) == "direcionar_especialista"

    @pytest.mark.parametrize("intencao", ["compra", "aluguel", "indefinida", None])
    def test_moradia_nao_tem_desfecho_proprio(self, intencao):
        assert qualificacao.desfecho_da_trilha(_perfil(intencao=intencao)) is None

    def test_o_desfecho_da_trilha_espelha_os_essenciais_do_investimento(self):
        perfil = _perfil(
            intencao="investimento", preco_max=400000, expectativa_retorno="0,8% ao mes"
        )

        assert qualificacao.lacunas_essenciais(perfil) == ()
        assert qualificacao.desfecho_da_trilha(perfil) == "direcionar_especialista"

    def test_lacuna_e_score_sao_a_mesma_regra(self):
        perfil = _perfil(intencao="compra", regiao="Moema")
        abertos = sum(sinal.peso for sinal in qualificacao.lacunas(perfil))

        assert qualificacao.pontuar(perfil) + abertos == 100


class TestFundir:
    def test_campo_novo_entra(self):
        fundido = qualificacao.fundir(
            _perfil(intencao="compra"), "compra", CamposExtraidosLLM(quartos=3)
        )

        assert fundido.quartos == 3

    def test_campo_nulo_nao_apaga_o_que_ja_se_sabia(self):
        fundido = qualificacao.fundir(
            _perfil(intencao="compra", regiao="Moema"), "compra", CamposExtraidosLLM()
        )

        assert fundido.regiao == "Moema"

    def test_valor_novo_substitui_o_antigo(self):
        fundido = qualificacao.fundir(
            _perfil(intencao="compra", quartos=2), "compra", CamposExtraidosLLM(quartos=3)
        )

        assert fundido.quartos == 3

    def test_indefinida_nao_apaga_intencao_conhecida(self):
        fundido = qualificacao.fundir(
            _perfil(intencao="compra"), "indefinida", CamposExtraidosLLM()
        )

        assert fundido.intencao == "compra"

    def test_intencao_nova_substitui(self):
        fundido = qualificacao.fundir(
            _perfil(intencao="compra"), "investimento", CamposExtraidosLLM()
        )

        assert fundido.intencao == "investimento"

    def test_nao_muta_o_perfil_recebido(self):
        perfil = _perfil(intencao="compra")
        qualificacao.fundir(perfil, "compra", CamposExtraidosLLM(quartos=3))

        assert perfil.quartos is None

    def test_todo_campo_do_llm_existe_no_perfil(self):
        assert set(CamposExtraidosLLM.model_fields) <= set(PerfilLead.model_fields)


class TestCamposExtraidosLLM:
    def test_e_o_contrato_menos_o_score(self):
        assert set(CamposExtraidosLLM.model_fields) == set(CamposExtraidos.model_fields) - {"score"}

    def test_o_modelo_nao_pode_devolver_score(self):
        with pytest.raises(Exception):
            CamposExtraidosLLM.model_validate({"score": 80})
