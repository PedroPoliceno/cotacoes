"""Lê a planilha do comprador: coluna A = COD, coluna B = NOME (cabeçalho opcional)."""
import io
import openpyxl


def ler_lista(data: bytes) -> dict:
    # Salva o arquivo no buffer da memória para facilitar a leitura
    ws = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True).worksheets[0]
    lista = {}

    # Faz a contagem da quantidade de linhas e atribui para 'n', depois atribui os valores originais (tuplas) extraídas da planilha e atribui no 'row'.
    for n, row in enumerate(ws.iter_rows(min_row=1, max_col=2, values_only=True), 1): #
        # Faz um tratamento, caso os valores forem nulos das células, atribui um valor vazio
        # Concatena os valores retirados da tupla com None, None para tratar linhas vazias
        cod, nome = (str(c).strip() if c is not None else "" for c in (row + (None, None))[:2])

        # Se os dados estiverem vazios pulam para a próxima linha
        if not cod and not nome:
            continue

        if n == 1 and cod.lower().startswith("cod"):  # cabeçalho
            continue

        # Aviso quando ou o código ou o nome não estão preenchidos
        if not cod or not nome:
            raise ValueError(f"Linha {n}: preencha o codigo e o nome")

        # Aviso quando os códigos estão repetidos
        if cod in lista:
            raise ValueError(f"Codigo repetido na lista: {cod}")

        # Atribui o nome a chave cod
        lista[cod] = nome

    # Aviso quando a lista está vazia
    if not lista:
        raise ValueError("A lista esta vazia")

    return lista
