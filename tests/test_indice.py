"""Indice vetorial do S-14. Os testes sem marker nao chamam o Gemini."""

import json
import math
import os

import pytest

from app.contrato import PerfilLead
from app.lia import indice as indice_imoveis
from app.lia.indice import (
    DIMENSAO,
    Embutidor,
    Filtro,
    Imovel,
    IndiceIndisponivelError,
)

CONSULTA_MORADIA = "apartamento reformado perto do metro para a familia"
CONSULTA_INVESTIMENTO = "studio compacto para alugar rapido, bom para investir"


def _imovel(**alteracoes) -> dict:
    registro = {
        "id": "IMV-001",
        "tipo": "apartamento",
        "bairro": "Moema",
        "zona": "sul",
        "quartos": 3,
        "banheiros": 2,
        "vagas": 2,
        "metragem": 98,
        "precoVenda": 1480000,
        "precoAluguel": 7200,
        "condominio": 1450,
        "iptu": 480,
        "descricao": "Apartamento reformado com varanda voltada para o poente.",
    }
    registro.update(alteracoes)
    return registro


@pytest.fixture
def base(tmp_path):
    registros = [
        _imovel(),
        _imovel(id="IMV-002", tipo="studio", bairro="Bela Vista", zona="centro", quartos=1,
                vagas=0, metragem=32, precoVenda=390000, precoAluguel=2400,
                descricao="Studio compacto a duas quadras da Paulista."),
        _imovel(id="IMV-003", tipo="casa", bairro="Tatuape", zona="leste", quartos=4,
                vagas=3, metragem=210, precoVenda=1250000, precoAluguel=None,
                descricao="Casa terrea com quintal e churrasqueira."),
        _imovel(id="IMV-004", tipo="cobertura", bairro="Pinheiros", zona="oeste", quartos=3,
                vagas=2, metragem=160, precoVenda=2400000, precoAluguel=11000,
                descricao="Cobertura duplex com terraco e vista aberta."),
    ]
    caminho = tmp_path / "imoveis.json"
    caminho.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    return caminho


@pytest.fixture
def embutidor_falso():
    """Vetor deterministico por id: a ordem esperada nao depende do modelo."""
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
def indice(base, embutidor_falso):
    construido = indice_imoveis.construir(embutidor=embutidor_falso, caminho=base)
    yield construido
    indice_imoveis.descartar()


class TestCarregarBase:
    def test_le_a_base_real_do_repositorio(self):
        imoveis = indice_imoveis.carregar()

        assert len(imoveis) == 80
        assert all(imovel.descricao.strip() for imovel in imoveis)
        assert all(imovel.preco_venda or imovel.preco_aluguel for imovel in imoveis)

    def test_camelcase_do_json_vira_snake_case(self, base):
        primeiro = indice_imoveis.carregar(base)[0]

        assert primeiro.preco_venda == 1480000
        assert primeiro.preco_aluguel == 7200

    def test_preco_ausente_e_none_e_nao_zero(self, base):
        casa = indice_imoveis.carregar(base)[2]

        assert casa.preco_aluguel is None

    def test_base_ilegivel_falha_alto(self, tmp_path):
        with pytest.raises(IndiceIndisponivelError):
            indice_imoveis.carregar(tmp_path / "nao-existe.json")

    def test_base_vazia_falha_alto(self, tmp_path):
        caminho = tmp_path / "vazia.json"
        caminho.write_text("[]", encoding="utf-8")

        with pytest.raises(IndiceIndisponivelError):
            indice_imoveis.carregar(caminho)


class TestTextoEmbutido:
    def test_cabecalho_estruturado_precede_a_descricao(self, base):
        texto = indice_imoveis.carregar(base)[0].texto

        assert texto.startswith("apartamento de 3 quartos e 2 vagas, 98 m2, no bairro Moema, zona sul.")
        assert texto.endswith("Apartamento reformado com varanda voltada para o poente.")

    def test_singular_de_quarto_e_vaga(self, base):
        studio = indice_imoveis.carregar(base)[1]

        assert studio.texto.startswith("studio de 1 quarto e 0 vagas,")


class TestConstrucao:
    def test_um_vetor_normalizado_por_imovel(self, indice):
        assert len(indice.vetores) == len(indice.imoveis) == 4

        for vetor in indice.vetores:
            assert math.isclose(math.sqrt(sum(v * v for v in vetor)), 1.0, rel_tol=1e-9)

    def test_atual_devolve_o_indice_construido(self, indice):
        assert indice_imoveis.atual() is indice

    def test_atual_sem_boot_falha_alto(self):
        indice_imoveis.descartar()

        with pytest.raises(IndiceIndisponivelError):
            indice_imoveis.atual()

    def test_contagem_divergente_de_vetores_falha_alto(self, base):
        torto = Embutidor(documentos=lambda textos: [[1.0, 0.0]], consulta=lambda texto: [1.0, 0.0])

        with pytest.raises(IndiceIndisponivelError):
            indice_imoveis.construir(embutidor=torto, caminho=base)

    def test_vetor_de_norma_zero_falha_alto(self, base):
        nulo = Embutidor(
            documentos=lambda textos: [[0.0, 0.0] for _ in textos],
            consulta=lambda texto: [0.0, 0.0],
        )

        with pytest.raises(IndiceIndisponivelError):
            indice_imoveis.construir(embutidor=nulo, caminho=base)


class TestBusca:
    def test_ordena_pelo_mais_similar(self, indice, base):
        alvo = indice_imoveis.carregar(base)[2]

        resultados = indice.buscar(alvo.texto)

        assert resultados[0].imovel.id == "IMV-003"
        assert math.isclose(resultados[0].similaridade, 1.0, rel_tol=1e-9)

    def test_similaridade_em_ordem_decrescente(self, indice, base):
        alvo = indice_imoveis.carregar(base)[0]

        similaridades = [r.similaridade for r in indice.buscar(alvo.texto)]

        assert similaridades == sorted(similaridades, reverse=True)

    def test_k_limita_o_resultado(self, indice, base):
        alvo = indice_imoveis.carregar(base)[0]

        assert len(indice.buscar(alvo.texto, k=2)) == 2

    def test_sem_filtro_todos_os_imoveis_concorrem(self, indice, base):
        alvo = indice_imoveis.carregar(base)[0]

        assert len(indice.buscar(alvo.texto, k=10)) == 4

    def test_consulta_de_dimensao_errada_falha_alto(self, base):
        descasado = Embutidor(
            documentos=lambda textos: [[1.0, 0.0, 0.0] for _ in textos],
            consulta=lambda texto: [1.0, 0.0],
        )
        construido = indice_imoveis.construir(embutidor=descasado, caminho=base)

        with pytest.raises(IndiceIndisponivelError):
            construido.buscar("qualquer coisa")

        indice_imoveis.descartar()


class TestFiltro:
    def _ids(self, indice, base, filtro):
        alvo = indice_imoveis.carregar(base)[0]
        return {r.imovel.id for r in indice.buscar(alvo.texto, k=10, filtro=filtro)}

    def test_quartos_e_piso_e_nao_igualdade(self, indice, base):
        assert self._ids(indice, base, Filtro(quartos=3)) == {"IMV-001", "IMV-003", "IMV-004"}

    def test_regiao_casa_com_bairro(self, indice, base):
        assert self._ids(indice, base, Filtro(regiao="Moema")) == {"IMV-001"}

    def test_regiao_casa_com_zona(self, indice, base):
        assert self._ids(indice, base, Filtro(regiao="zona oeste")) == {"IMV-004"}

    def test_regiao_ignora_acento_e_caixa(self, indice, base):
        assert self._ids(indice, base, Filtro(regiao="TATUAPE")) == {"IMV-003"}

    def test_compra_filtra_pelo_preco_de_venda(self, indice, base):
        filtro = Filtro(intencao="compra", preco_max=1300000)

        assert self._ids(indice, base, filtro) == {"IMV-002", "IMV-003"}

    def test_aluguel_filtra_pelo_preco_de_aluguel(self, indice, base):
        filtro = Filtro(intencao="aluguel", preco_max=8000)

        assert self._ids(indice, base, filtro) == {"IMV-001", "IMV-002"}

    def test_aluguel_descarta_imovel_so_de_venda(self, indice, base):
        filtro = Filtro(intencao="aluguel", preco_max=99000)

        assert "IMV-003" not in self._ids(indice, base, filtro)

    def test_preco_min_e_max_delimitam_a_faixa(self, indice, base):
        filtro = Filtro(intencao="compra", preco_min=1000000, preco_max=1500000)

        assert self._ids(indice, base, filtro) == {"IMV-001", "IMV-003"}

    def test_sem_intencao_o_preco_nao_filtra(self, indice, base):
        assert len(self._ids(indice, base, Filtro(preco_max=1))) == 4

    def test_intencao_indefinida_nao_filtra_preco(self, indice, base):
        assert len(self._ids(indice, base, Filtro(intencao="indefinida", preco_max=1))) == 4

    def test_filtros_se_somam(self, indice, base):
        filtro = Filtro(intencao="compra", preco_max=1500000, quartos=3, regiao="zona sul")

        assert self._ids(indice, base, filtro) == {"IMV-001"}

    def test_nada_na_base_devolve_lista_vazia(self, indice, base):
        filtro = Filtro(intencao="compra", preco_max=1000, quartos=1)

        assert self._ids(indice, base, filtro) == set()

    def test_do_perfil_copia_os_cinco_campos(self):
        perfil = PerfilLead(
            nome="Rafael",
            intencao="compra",
            preco_min=400000,
            preco_max=650000,
            quartos=3,
            regiao="Butanta",
            urgencia="alta",
            score=70,
        )

        assert Filtro.do_perfil(perfil) == Filtro(
            intencao="compra",
            preco_min=400000,
            preco_max=650000,
            quartos=3,
            regiao="Butanta",
        )

    def test_perfil_vazio_nao_filtra_nada(self, indice, base):
        assert len(self._ids(indice, base, Filtro.do_perfil(PerfilLead()))) == 4


class TestCache:
    """O cache e o que faz o boot nao gastar cota. Nada aqui chama a API."""

    def _vetores(self, imoveis) -> list[list[float]]:
        return [[math.cos(posicao + eixo) for eixo in range(DIMENSAO)] for posicao in range(len(imoveis))]

    @pytest.fixture
    def gravado(self, base, tmp_path):
        imoveis = indice_imoveis.carregar(base)
        caminho = tmp_path / "embeddings.json"
        indice_imoveis.escrever_cache(imoveis, self._vetores(imoveis), "gemini-embedding-001", caminho)
        return imoveis, caminho

    def test_ida_e_volta_devolve_os_vetores_normalizados(self, gravado):
        imoveis, caminho = gravado

        vetores = indice_imoveis.ler_cache(imoveis, "gemini-embedding-001", caminho)

        assert vetores is not None
        assert len(vetores) == len(imoveis)

        for vetor in vetores:
            assert math.isclose(math.sqrt(sum(v * v for v in vetor)), 1.0, rel_tol=1e-5)

    def test_impressao_muda_quando_a_base_muda(self, base, tmp_path):
        imoveis = indice_imoveis.carregar(base)
        outro = tmp_path / "outra.json"
        registros = json.loads(base.read_text(encoding="utf-8"))
        registros[0]["descricao"] = "Outra descricao inteiramente diferente."
        outro.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")

        assert indice_imoveis.impressao(imoveis) != indice_imoveis.impressao(
            indice_imoveis.carregar(outro)
        )

    def test_impressao_e_estavel_para_a_mesma_base(self, base):
        imoveis = indice_imoveis.carregar(base)

        assert indice_imoveis.impressao(imoveis) == indice_imoveis.impressao(imoveis)

    def test_cache_de_outro_modelo_e_recusado(self, gravado):
        imoveis, caminho = gravado

        assert indice_imoveis.ler_cache(imoveis, "outro-modelo", caminho) is None

    def test_cache_de_base_alterada_e_recusado(self, gravado, base, tmp_path):
        _, caminho = gravado
        registros = json.loads(base.read_text(encoding="utf-8"))
        registros[0]["descricao"] = "Descricao trocada depois de gerar o cache."
        mudada = tmp_path / "mudada.json"
        mudada.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")

        assert indice_imoveis.ler_cache(indice_imoveis.carregar(mudada), "gemini-embedding-001", caminho) is None

    def test_cache_sem_um_imovel_e_recusado(self, gravado):
        imoveis, caminho = gravado
        guardado = json.loads(caminho.read_text(encoding="utf-8"))
        del guardado["vetores"]["IMV-002"]
        caminho.write_text(json.dumps(guardado, ensure_ascii=False), encoding="utf-8")

        assert indice_imoveis.ler_cache(imoveis, "gemini-embedding-001", caminho) is None

    def test_cache_de_outra_dimensao_e_recusado(self, gravado):
        imoveis, caminho = gravado
        guardado = json.loads(caminho.read_text(encoding="utf-8"))
        guardado["dimensao"] = 1536
        caminho.write_text(json.dumps(guardado, ensure_ascii=False), encoding="utf-8")

        assert indice_imoveis.ler_cache(imoveis, "gemini-embedding-001", caminho) is None

    def test_cache_corrompido_e_recusado_sem_explodir(self, gravado):
        imoveis, caminho = gravado
        caminho.write_text("{nao e json", encoding="utf-8")

        assert indice_imoveis.ler_cache(imoveis, "gemini-embedding-001", caminho) is None

    def test_cache_ausente_devolve_none(self, base, tmp_path):
        imoveis = indice_imoveis.carregar(base)

        assert indice_imoveis.ler_cache(imoveis, "gemini-embedding-001", tmp_path / "nada.json") is None

    def test_cache_versionado_confere_com_a_base_real(self):
        modelo = os.getenv("GEMINI_EMBEDDING_MODEL", "").strip()

        if not indice_imoveis.CACHE.exists() or not modelo:
            pytest.skip("cache de embeddings ou GEMINI_EMBEDDING_MODEL ausente")

        assert indice_imoveis.ler_cache(indice_imoveis.carregar(), modelo) is not None

    def test_indice_injetado_ignora_o_cache(self, base, embutidor_falso):
        construido = indice_imoveis.construir(embutidor=embutidor_falso, caminho=base)

        assert construido.origem == "injetado"
        assert construido.modelo == "injetado"

        indice_imoveis.descartar()


@pytest.mark.llm
class TestBuscaReal:
    """Gasta cota de embedding: 80 unidades no boot sem cache, 1 por busca.

    O teto do free tier e 100 por minuto, entao esta classe inteira cabe numa
    janela — mas rodar duas vezes seguidas nao cabe.
    """

    @pytest.fixture(scope="class")
    def indice_real(self):
        if not os.getenv("GEMINI_EMBEDDING_MODEL", "").strip():
            pytest.skip("ausente no ambiente: GEMINI_EMBEDDING_MODEL")

        construido = indice_imoveis.construir()
        yield construido
        indice_imoveis.descartar()

    def test_indice_da_base_inteira_na_dimensao_esperada(self, gemini_configurado, indice_real):
        assert len(indice_real.imoveis) == 80
        assert indice_real.dimensao == DIMENSAO

    def test_boot_sem_cache_gera_os_vetores_pela_api(self, gemini_configurado, indice_real):
        pela_api = indice_imoveis.construir(cache=False)

        assert pela_api.origem == "api"
        assert len(pela_api.imoveis) == 80
        assert pela_api.dimensao == DIMENSAO

        for do_cache, da_api in zip(indice_real.vetores, pela_api.vetores):
            assert math.isclose(sum(a * b for a, b in zip(do_cache, da_api)), 1.0, abs_tol=1e-4)

    def test_texto_livre_traz_o_tipo_certo_no_topo(self, gemini_configurado, indice_real):
        resultados = indice_real.buscar("cobertura com terraco e vista aberta", k=5)

        assert resultados[0].imovel.tipo == "cobertura"
        assert resultados[0].similaridade > resultados[-1].similaridade

    def test_texto_livre_traz_a_regiao_certa(self, gemini_configurado, indice_real):
        resultados = indice_real.buscar("quero morar perto da Avenida Paulista", k=5)

        assert any(r.imovel.zona == "centro" for r in resultados)

    def test_busca_filtrada_respeita_o_recorte(self, gemini_configurado, indice_real):
        filtro = Filtro(intencao="aluguel", preco_max=3500, quartos=1)

        resultados = indice_real.buscar("studio compacto para alugar", k=5, filtro=filtro)

        assert resultados
        assert all(r.imovel.quartos >= 1 for r in resultados)
        assert all(r.imovel.preco_aluguel and r.imovel.preco_aluguel <= 3500 for r in resultados)

    def test_consultas_diferentes_ordenam_diferente(self, gemini_configurado, indice_real):
        moradia = [r.imovel.id for r in indice_real.buscar(CONSULTA_MORADIA, k=5)]
        investimento = [r.imovel.id for r in indice_real.buscar(CONSULTA_INVESTIMENTO, k=5)]

        assert moradia != investimento
