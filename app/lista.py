"""Lê a planilha do comprador: coluna A = COD, coluna B = NOME (cabeçalho opcional)."""
import io
import openpyxl


def ler_lista(data: bytes) -> dict:
    ws = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True).worksheets[0]
    lista = {}
    for n, row in enumerate(ws.iter_rows(min_row=1, max_col=2, values_only=True), 1):
        cod, nome = (str(c).strip() if c is not None else "" for c in (row + (None, None))[:2])
        if not cod and not nome:
            continue
        if n == 1 and cod.lower().startswith("cod"):  # cabeçalho
            continue
        if not cod or not nome:
            raise ValueError(f"Linha {n}: preencha o código e o nome")
        if cod in lista:
            raise ValueError(f"Código repetido na lista: {cod}")
        lista[cod] = nome
    if not lista:
        raise ValueError("A lista está vazia")
    return lista
