"""Testes da avaliacao em numeros (scripts/avaliar.py), sem chamar o Gemini.

Cobrem as metricas, a integridade do conjunto rotulado da busca e o juizo
`falhas` que o script compartilha com tests/test_extracao.py.
"""

import json
import pathlib
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.contrato import CamposExtraidos
from app.lia import qualificacao
from scripts.avaliar import (
    CONSULTAS_BUSCA,
    K,
    MARCA_FIM,
    MARCA_INICIO,
    acerto_em_k,
    com_bloco_trocado,
    percentil,
    reciproco_da_posicao,
    recall_em_k,
)
from tests.test_extracao import CASOS, Caso, falhas

RAIZ = pathlib.Path(__file__).resolve().parents[1]
ORDEM = ["IMV-009", "IMV-002", "IMV-031", "IMV-004", "IMV-050", "IMV-077", "IMV-001"]


def test_acerto_em_k_olha_so_o_topo() -> None:
    assert acerto_em_k(ORDEM, frozenset({"IMV-050"})) == 1.0
    assert acerto_em_k(ORDEM, frozenset({"IMV-077"})) == 0.0
    assert acerto_em_k(ORDEM, frozenset({"IMV-077"}), k=6) == 1.0


def test_recall_em_k_e_a_fracao_dos_relevantes_no_topo() -> None:
    assert recall_em_k(ORDEM, frozenset({"IMV-002", "IMV-077"})) == 0.5
    assert recall_em_k(ORDEM, frozenset({"IMV-002", "IMV-004"})) == 1.0
    assert recall_em_k(ORDEM, frozenset({"IMV-099"})) == 0.0


def test_recall_sem_relevante_e_erro_e_nao_zero() -> None:
    with pytest.raises(ValueError):
        recall_em_k(ORDEM, frozenset())


def test_reciproco_usa_o_primeiro_relevante() -> None:
    assert reciproco_da_posicao(ORDEM, frozenset({"IMV-009"})) == 1.0
    assert reciproco_da_posicao(ORDEM, frozenset({"IMV-031", "IMV-002"})) == 0.5
    assert reciproco_da_posicao(ORDEM, frozenset({"IMV-001"})) == pytest.approx(1 / 7)
    assert reciproco_da_posicao(ORDEM, frozenset({"IMV-099"})) == 0.0


def test_percentil_por_posicao_mais_proxima() -> None:
    valores = [float(v) for v in range(1, 21)]
    assert percentil(valores, 0.95) == 19.0
    assert percentil(valores, 0.5) == 10.0
    assert percentil([7.0], 0.95) == 7.0
    with pytest.raises(ValueError):
        percentil([], 0.95)


def test_consultas_da_busca_apontam_para_imoveis_do_acervo() -> None:
    acervo = {
        imovel["id"]
        for imovel in json.loads((RAIZ / "data" / "imoveis.json").read_text(encoding="utf-8"))
    }

    for consulta in CONSULTAS_BUSCA:
        assert consulta.relevantes, consulta.texto
        assert consulta.relevantes <= acervo, consulta.texto
        # Com mais de K relevantes o recall@K nunca chega a 1 e o numero engana.
        assert len(consulta.relevantes) <= K, consulta.texto


def test_consultas_da_busca_nao_se_repetem() -> None:
    textos = [consulta.texto.casefold() for consulta in CONSULTAS_BUSCA]
    assert len(textos) == len(set(textos))
    assert len(CONSULTAS_BUSCA) >= 20


def _resposta_certa(caso: Caso, **trocas) -> SimpleNamespace:
    """Resposta que acerta tudo o que o caso pede, com `trocas` para estragar."""
    campos = dict(caso.extrai)
    for nome, trecho in caso.contem.items():
        campos.setdefault(nome, trecho)

    intencao = trocas.pop("intencao", caso.intencao or "indefinida")
    campos.update(trocas.pop("campos", {}))
    extraidos = CamposExtraidos(**campos)
    perfil = qualificacao.fundir(caso.requisicao().perfil_lead, intencao, extraidos)
    extraidos = extraidos.model_copy(update={"score": qualificacao.pontuar(perfil)})

    return SimpleNamespace(
        intencao=intencao,
        proxima_acao=trocas.pop("proxima_acao", caso.proxima_acao),
        campos_extraidos=extraidos,
    )


CASO = next(caso for caso in CASOS if caso.extrai and caso.intencao)


def test_falhas_vazia_quando_a_resposta_acerta() -> None:
    assert falhas(CASO, _resposta_certa(CASO)) == []


def test_falhas_lista_cada_erro_em_vez_de_parar_no_primeiro() -> None:
    outra = "aluguel" if CASO.intencao != "aluguel" else "compra"
    nao_pedido = next(
        nome for nome in CamposExtraidos.model_fields if nome not in CASO.permitidos()
    )
    valor = 3 if nome_numerico(nao_pedido) else "inventado"

    erros = falhas(CASO, _resposta_certa(CASO, intencao=outra, campos={nao_pedido: valor}))

    assert any(erro.startswith("intencao:") for erro in erros)
    assert any("ninguem mencionou" in erro for erro in erros)


def test_falhas_pega_score_fora_da_regua() -> None:
    resposta = _resposta_certa(CASO)
    errado = (resposta.campos_extraidos.score or 0) + 1
    resposta.campos_extraidos = resposta.campos_extraidos.model_copy(update={"score": errado})

    assert falhas(CASO, resposta) == ["o score nao veio da regua"]


def test_falhas_respeita_campo_esperado_ausente() -> None:
    nome = next(iter(CASO.extrai))
    caso = replace(CASO, tolera=())

    erros = falhas(caso, _resposta_certa(caso, campos={nome: None}))

    assert any(erro.startswith(f"{nome}:") for erro in erros)


def nome_numerico(nome: str) -> bool:
    return CamposExtraidos.model_fields[nome].annotation not in (str, str | None)


def test_bloco_do_readme_troca_so_o_que_esta_entre_os_marcadores() -> None:
    texto = f"antes\n{MARCA_INICIO}\nvelho\n{MARCA_FIM}\ndepois\n"

    novo = com_bloco_trocado(texto, "\nnovo\n")

    assert novo == f"antes\n{MARCA_INICIO}\nnovo\n{MARCA_FIM}\ndepois\n"
    assert com_bloco_trocado(novo, "novo") == novo


def test_bloco_do_readme_sem_marcadores_e_erro() -> None:
    with pytest.raises(ValueError):
        com_bloco_trocado(f"{MARCA_FIM}\n{MARCA_INICIO}", "x")


def test_readme_tem_os_marcadores_da_avaliacao() -> None:
    texto = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert texto.count(MARCA_INICIO) == 1 and texto.count(MARCA_FIM) == 1
    com_bloco_trocado(texto, "x")
