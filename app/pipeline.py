"""Validação, normalização e cálculo. Nada aqui usa IA: tudo é determinístico e auditável."""
import re

def prazo_pgto_dias(txt):
    """'30/60/90' -> 60 (média) | '28 DIAS' -> 28 | 'Pagamento Antecipado' -> 0 | desconhecido -> None"""
    t = (txt or "").lower()
    if not t.strip():
        return None
    if "antecip" in t or "vista" in t:
        return 0
    nums = [int(n) for n in re.findall(r"\d+", t)]
    return sum(nums) / len(nums) if nums else None


def tipo_frete(txt):
    t = (txt or "").upper()
    return "FOB" if "FOB" in t else "CIF" if "CIF" in t else None


_UNID = {"kg": (1000.0, "g"), "l": (1000.0, "mL"), "lt": (1000.0, "mL"), "lts": (1000.0, "mL"),
         "litro": (1000.0, "mL"), "litros": (1000.0, "mL")}
_TAM = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|gr|g|ml|lt|l)\b", re.I)


def conteudo_unidade(unidade, descricao, fator_ia=None, base_ia=None):
    """Quanto vale UMA unidade de venda em g ou mL.
    KG e LITRO são exatos (a IA não decide); frasco/unidade usa o tamanho da descrição; a IA é o último recurso."""
    u = re.sub(r"[^a-z]", "", (unidade or "").lower())
    if u in _UNID:
        return _UNID[u]
    achados = []
    for n, un in _TAM.findall(descricao or ""):
        v, un = float(n.replace(",", ".")), un.lower()
        achado = (v * 1000, "g") if un == "kg" else (v, "g") if un in ("g", "gr") else (v, "mL") if un == "ml" else (v * 1000, "mL")
        if achado not in achados:
            achados.append(achado)
    if achados and (len(achados) == 1 or not fator_ia):
        return achados[0]
    return (float(fator_ia), base_ia or "g") if fator_ia else (None, "g")


def custo_final(it: dict, rend: float = 0.0005, frete_fob: float = 0.05) -> float:
    """Mesma fórmula da planilha: K + M - K*rendimento*prazo   (K = preço por grama)."""
    h = it["preco_fr"] / it["fr_g"]
    m = h * frete_fob if it.get("frete") == "FOB" else 0
    return h + m - h * rend * (it.get("prazo_dias") or 0)


def _p(arq, forn, nivel, tipo, msg):
    return {"arquivo": arq, "fornecedor": forn, "nivel": nivel, "tipo": tipo, "msg": msg}


def process_doc(filename: str, doc: dict, lista: dict):
    forn = (doc.get("fornecedor_curto") or doc.get("fornecedor") or "DESCONHECIDO").strip().upper()
    items, pend = [], []
    dias, frete = prazo_pgto_dias(doc.get("condicao_pagamento")), tipo_frete(doc.get("tipo_frete"))
    cambio = 1.0
    if (doc.get("moeda") or "BRL").upper() == "USD":  # câmbio = o próprio documento (total em R$ / total em US$)
        brl, usd = doc.get("total_documento_brl"), doc.get("total_documento")
        cambio = brl / usd if brl and usd else None
        if cambio is None:
            pend.append(_p(filename, forn, "erro", "moeda", "Cotação em dólar sem total em R$ para converter: itens ficam fora da planilha"))
    if doc.get("conflito"):
        pend.append(_p(filename, forn, "aviso", "conflito", f"Documento com informações conflitantes: {doc['conflito']}"))
    if doc.get("aviso_leitura"):
        pend.append(_p(filename, forn, "aviso", "leitura", doc["aviso_leitura"]))
    linhas = doc.get("itens") or []
    soma = sum(i["total_linha"] for i in linhas)
    if doc.get("total_documento") and abs(soma - doc["total_documento"]) > 0.05:
        pend.append(_p(filename, forn, "erro", "total", f"Soma das linhas ({soma:,.2f}) ≠ total do documento ({doc['total_documento']:,.2f})"))
    for i in linhas:
        desc = i["descricao"]
        if abs(i["quantidade"] * i["preco_unitario"] - i["total_linha"]) > max(0.02, 0.005 * i["total_linha"]):
            pend.append(_p(filename, forn, "erro", "linha", f"Qtd × unitário ≠ total na linha: {desc}"))
        cod = i.get("cod") if i.get("cod") in lista else None  # IA só pode escolher da lista
        fator, base = conteudo_unidade(i.get("unidade"), desc, i.get("fator_base"), i.get("unidade_base"))
        icms = i.get("icms_pct")
        alertas = []
        if cod and i.get("duvida"):
            alertas.append(f"Conferir MP: {i['duvida']}")
            pend.append(_p(filename, forn, "aviso", "duvida", f"{cod} – {desc}: {i['duvida']}"))
        if cod and not fator:
            alertas.append("Conteúdo da unidade (g/mL) não identificado")
            pend.append(_p(filename, forn, "aviso", "fator", f"{cod} – {desc}: conteúdo da unidade não identificado; fica fora da planilha até preencher 'g/FR' na tabela"))
        if cod and dias is None:
            alertas.append("Prazo de pagamento não identificado")
        if cod and frete is None:
            alertas.append("Tipo de frete não identificado (assumido CIF)")
        if cod and cambio and cambio != 1.0:
            alertas.append(f"Convertido de US$ (câmbio {cambio:.4f})")
        items.append({"arquivo": filename, "fornecedor": forn, "cod": cod, "descricao_forn": desc, "marca": i.get("marca"),
                      "qtde_g": i["quantidade"] * fator if fator else None, "fr_g": fator, "um": base,
                      "preco_fr": i["preco_unitario"] * cambio if cambio else None,
                      "icms": icms / 100 if icms is not None else None, "ipi": (i.get("ipi_pct") or 0) / 100,
                      "frete": frete or "CIF", "prazo_dias": dias, "pgto": doc.get("condicao_pagamento") or "",
                      "entrega": i.get("prazo_entrega_dias"), "alertas": alertas})
    return items, pend


def process_all(docs: list, lista: dict):
    """docs = [(nome_arquivo, dict_extraido)]; lista = {COD: NOME}"""
    items, pend = [], []
    for fn, d in docs:
        i, p = process_doc(fn, d, lista)
        items += i
        pend += p
    faltam = [f"{c} {n}" for c, n in lista.items() if c not in {i["cod"] for i in items}]
    if faltam:
        pend.append(_p("", "", "aviso", "sem_cotacao", "Produtos da lista sem nenhuma cotação: " + "; ".join(faltam) +
                       ". Confira se não aparecem nas cotações com outro nome (use o seletor MP na tabela)."))
    items.sort(key=lambda x: x["cod"] is None)
    por_cod = {}
    for it in items:
        if it["cod"] and it["qtde_g"]:
            por_cod.setdefault(it["cod"], []).append(it)
    for cod, lst in por_cod.items():
        if len({x["um"] for x in lst}) > 1:
            pend.append(_p("", "", "aviso", "base", f"{cod}: cotações em unidades diferentes (g × mL); sem a densidade os preços não são comparáveis"))
        if len({round(x["qtde_g"]) for x in lst}) > 1:
            det = ", ".join(f"{x['fornecedor']} {x['qtde_g']:,.0f} g" for x in lst)
            pend.append(_p("", "", "aviso", "qtde", f"{cod}: quantidades diferentes entre fornecedores ({det})"))
            for x in lst:
                x["alertas"].append("QTDE diverge entre fornecedores")
    return items, pend
