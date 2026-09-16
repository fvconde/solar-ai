"""Mascaramento auditavel de PII antes das chamadas externas.

O mapa vive somente durante um turno. Formatos numericos compactos sao
ambiguos no Brasil (CPF, telefone e CEP podem ter 8 ou 11 digitos), portanto o
rotulo escrito pelo lead decide o tipo quando nao ha pontuacao distintiva.
"""

import re
from collections import defaultdict
from typing import Literal

TipoPII = Literal["CPF", "TELEFONE", "EMAIL", "CEP"]

_EMAIL = re.compile(r"(?<![\w.+-])[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])", re.IGNORECASE)
_CPF_PONTUADO = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
_TELEFONE_FORMATADO = re.compile(
    r"(?<!\d)(?:"
    r"\([1-9]\d\)\s*(?:9\d{4}|[2-5]\d{3})[-\s]?\d{4}"
    r"|[1-9]\d[ .](?:9\d{4}|[2-5]\d{3})[-\s]\d{4}"
    r"|(?:9\d{4}|[2-5]\d{3})-\d{4}"
    r")(?!\d)"
)
_CEP_PONTUADO = re.compile(r"(?<!\d)\d{5}-\d{3}(?!\d)")
_COMPACTO_COM_ROTULO = re.compile(
    r"(?P<rotulo>\b(?:cpf|telefone|fone|celular|whatsapp|whats|cep)\b"
    r"(?:\s*(?:e|é|:|=|n[ºo.]*)\s*|\s+))"
    r"(?P<valor>\d{8,11})(?!\d)",
    re.IGNORECASE,
)
_NUMERO_LONGO = re.compile(r"(?<!\d)\d{10,11}(?!\d)")
_DDDS = {
    *range(11, 20),
    21,
    22,
    24,
    27,
    28,
    *range(31, 36),
    37,
    38,
    *range(41, 47),
    49,
    51,
    53,
    54,
    55,
    *range(61, 70),
    71,
    73,
    74,
    75,
    77,
    79,
    *range(81, 90),
    *range(91, 100),
}


class MascaradorPII:
    """Troca PII por tokens estaveis e reversiveis dentro de um unico turno."""

    def __init__(self) -> None:
        self._contadores: defaultdict[TipoPII, int] = defaultdict(int)
        self._token_por_valor: dict[tuple[TipoPII, str], str] = {}
        self._valor_por_token: dict[str, str] = {}

    @property
    def mapa(self) -> dict[str, str]:
        """Copia do mapa token -> valor, principalmente para auditoria e testes."""
        return dict(self._valor_por_token)

    def mascarar(self, texto: str) -> str:
        mascarado = _EMAIL.sub(lambda achado: self._token("EMAIL", achado.group()), texto)
        mascarado = _CPF_PONTUADO.sub(
            lambda achado: self._token("CPF", achado.group()), mascarado
        )
        mascarado = _TELEFONE_FORMATADO.sub(
            lambda achado: self._token("TELEFONE", achado.group()), mascarado
        )
        mascarado = _CEP_PONTUADO.sub(
            lambda achado: self._token("CEP", achado.group()), mascarado
        )
        mascarado = _COMPACTO_COM_ROTULO.sub(self._mascarar_compacto, mascarado)
        return _NUMERO_LONGO.sub(self._mascarar_numero_longo, mascarado)

    def desmascarar(self, texto: str) -> str:
        restaurado = texto

        for token, valor in self._valor_por_token.items():
            restaurado = restaurado.replace(token, valor)

        return restaurado

    def _token(self, tipo: TipoPII, valor: str) -> str:
        chave = (tipo, valor)

        if chave not in self._token_por_valor:
            self._contadores[tipo] += 1
            token = f"[{tipo}_{self._contadores[tipo]}]"
            self._token_por_valor[chave] = token
            self._valor_por_token[token] = valor

        return self._token_por_valor[chave]

    def _mascarar_compacto(self, achado: re.Match[str]) -> str:
        rotulo = achado.group("rotulo")
        valor = achado.group("valor")
        chave = rotulo.lower()

        if "cpf" in chave and len(valor) == 11:
            tipo: TipoPII = "CPF"
        elif "cep" in chave and len(valor) == 8:
            tipo = "CEP"
        elif any(
            nome in chave
            for nome in ("telefone", "fone", "celular", "whatsapp", "whats")
        ) and len(valor) in (8, 9, 10, 11):
            tipo = "TELEFONE"
        else:
            return achado.group()

        return f"{rotulo}{self._token(tipo, valor)}"

    def _mascarar_numero_longo(self, achado: re.Match[str]) -> str:
        valor = achado.group()

        if len(valor) == 11 and _cpf_valido(valor):
            return self._token("CPF", valor)

        ddd = int(valor[:2])
        telefone = ddd in _DDDS and (
            (len(valor) == 11 and valor[2] == "9")
            or (len(valor) == 10 and valor[2] in "2345")
        )
        return self._token("TELEFONE", valor) if telefone else valor


def _cpf_valido(valor: str) -> bool:
    """Valida os digitos verificadores para reduzir falso positivo sem rotulo."""
    if len(set(valor)) == 1:
        return False

    numeros = [int(digito) for digito in valor]

    for tamanho in (9, 10):
        soma = sum(
            numero * peso
            for numero, peso in zip(numeros[:tamanho], range(tamanho + 1, 1, -1))
        )
        resto = (soma * 10) % 11
        esperado = 0 if resto == 10 else resto

        if numeros[tamanho] != esperado:
            return False

    return True
