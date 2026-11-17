"""Extração via API do Claude. Aceita PDF, imagem, xlsx/csv/txt/eml."""
import base64, io, os
from pathlib import Path
from .schema import COTACAO_TOOL

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
PROMPT = ("Extraia todos os itens desta cotação de fornecedor. Copie valores exatamente como aparecem. "
          "Não invente: se um campo não aparecer, use null. Preços e totais são números (ponto decimal).\n\n"
          "Lista de produtos do comprador (COD | NOME):\n{lista}\n\n"
          "Para cada item da cotação, preencha `cod` com o COD da lista se for claramente o MESMO produto "
          "(nomes em outro idioma, abreviações ou tamanho de embalagem diferente não mudam o produto). "
          "Produto parecido mas diferente (outro tipo de meio de cultura, por exemplo) NÃO é o mesmo: use null. "
          "Se ficar em dúvida, escolha o mais provável e explique em `duvida`.\n"
          "O nome na lista pode trazer restrições ou observações (marca, fornecedor, armazenamento, \"verificar ...\"). "
          "Compare com a marca e o fornecedor da cotação: se o item contrariar a restrição, ou se não der para confirmar "
          "(ex.: a lista exige uma marca e a cotação é de outra), mantenha o `cod` e explique em `duvida`.\n\n"
          "`quantidade` e `preco_unitario` seguem a unidade de venda da cotação (KG, LITRO, FR...). Preencha `fator_base` e "
          "`unidade_base` com o conteúdo dessa unidade em g ou mL (preço por KG -> 1000 g; por LITRO -> 1000 mL). "
          "Se o preço estiver em dólar, use moeda=USD e informe o total em R$ do documento, se houver.\n\n"
          "Entregue o resultado chamando a ferramenta registrar_cotacao.")
IMG = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}


def _xlsx_text(data: bytes) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    out = []
    for ws in wb:
        out.append(f"## Planilha: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            if any(c is not None for c in row):
                out.append(" | ".join("" if c is None else str(c) for c in row))
    return "\n".join(out)


def tipo_imagem(data: bytes, ext: str) -> str:
    """Tipo real pelo conteúdo (a extensão pode mentir: .png que na verdade é JPEG)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return IMG[ext]


def build_content(filename: str, data: bytes, lista: dict) -> list:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": base64.standard_b64encode(data).decode()}}
    elif ext in IMG:
        block = {"type": "image", "source": {"type": "base64", "media_type": tipo_imagem(data, ext),
                                             "data": base64.standard_b64encode(data).decode()}}
    elif ext in (".xlsx", ".xlsm"):
        block = {"type": "text", "text": _xlsx_text(data)}
    elif ext in (".csv", ".txt", ".eml", ".md"):
        block = {"type": "text", "text": data.decode("utf-8", errors="replace")}
    else:
        raise ValueError(f"Formato não suportado: {ext}")
    txt = "\n".join(f"{c} | {n}" for c, n in lista.items())
    return [block, {"type": "text", "text": PROMPT.format(lista=txt)}]


def extract(filename: str, data: bytes, lista: dict) -> dict:
    import anthropic  # import tardio: testes não precisam do SDK
    client = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente
    resp = client.messages.create(
        model=MODEL, max_tokens=16000, tools=[COTACAO_TOOL],  # sem tool_choice forçado: não suportado por todos os modelos
        messages=[{"role": "user", "content": build_content(filename, data, lista)}])
    for b in resp.content:
        if b.type == "tool_use":
            return b.input
    raise ValueError("A IA não devolveu os dados da cotação (sem chamada da ferramenta). Tente novamente.")
