"""Contrato do POST /turn.

Espelhado em solar-ai-api/src/Solar.Api/Contracts/ContratoTurno.cs.
Mudanca aqui exige commit coordenado nos dois repositorios.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Papel = Literal["lead", "agente"]
Intencao = Literal["compra", "aluguel", "investimento", "indefinida"]
Urgencia = Literal["alta", "media", "baixa"]
ProximaAcao = Literal[
    "continuar_conversa",
    "sugerir_imoveis",
    "agendar_visita",
    "encerrar",
    "escalar_humano",
]

LIMITE_MENSAGEM = 4000
LIMITE_HISTORICO = 50
LIMITE_IMOVEIS = 5


class _Contrato(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class MensagemHistorico(_Contrato):
    papel: Papel
    texto: str
    em: datetime


class PerfilLead(_Contrato):
    """Perfil acumulado do lead, do qual a API .NET e dona."""

    nome: str | None = None
    intencao: Intencao | None = None
    preco_min: int | None = None
    preco_max: int | None = None
    quartos: int | None = None
    regiao: str | None = None
    urgencia: Urgencia | None = None
    score: int | None = Field(default=None, ge=0, le=100)


class CamposExtraidos(_Contrato):
    """O que este turno acrescentou ao perfil. Campo nulo = nao mencionado."""

    nome: str | None = None
    preco_min: int | None = None
    preco_max: int | None = None
    quartos: int | None = None
    regiao: str | None = None
    urgencia: Urgencia | None = None
    score: int | None = Field(default=None, ge=0, le=100)


class ImovelSugerido(_Contrato):
    id: str
    tipo: str
    bairro: str
    quartos: int
    metragem: int
    preco_venda: int | None = None
    preco_aluguel: int | None = None
    motivo: str


class TurnoRequest(_Contrato):
    conversa_id: UUID
    mensagem: str = Field(min_length=1, max_length=LIMITE_MENSAGEM)
    historico: list[MensagemHistorico] = Field(default_factory=list, max_length=LIMITE_HISTORICO)
    perfil_lead: PerfilLead = Field(default_factory=PerfilLead)


class TurnoResponse(_Contrato):
    resposta: str
    intencao: Intencao
    campos_extraidos: CamposExtraidos
    proxima_acao: ProximaAcao
    imoveis_sugeridos: list[ImovelSugerido] = Field(default_factory=list, max_length=LIMITE_IMOVEIS)
