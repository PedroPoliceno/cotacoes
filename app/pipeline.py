"""Validação, normalização e cálculo. Nada aqui usa IA: tudo é determinístico e auditável."""
import re
import unicodedata
from difflib import SequenceMatcher

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


# Termos genéricos ou observações comerciais que não identificam o produto.
_STOP_PRODUTO = {"agar", "meio", "de", "da", "do", "das", "dos", "para", "com",
                 "marca", "conda", "fotossensivel", "fotossensibilidade", "verificar",
                 "concentracao", "exigida", "exigido", "frasco", "500", "g"}


def _termos_identidade(nome: str) -> set[str]:
    """Extrai os termos identificadores do nome cadastrado, ignorando observações após hífen/parênteses."""
    nome = unicodedata.normalize("NFKD", nome or "")
    nome = "".join(c for c in nome if not unicodedata.combining(c)).lower()
    # Em nomes como 'Agar Mueller Hinton - Conda', o trecho após o hífen é uma exigência, não identidade.
    nome = re.split(r"\s+-\s+|\(", nome, maxsplit=1)[0]
    tokens = re.findall(r"[a-z0-9]+", nome)
    if "mac" in tokens and "conkey" in tokens:
        tokens = [t for t in tokens if t not in {"mac", "conkey"}] + ["macconkey"]
    return {t for t in tokens if len(t) > 1 and t not in _STOP_PRODUTO}


def _descricao_compativel_com_mp(descricao: str, nome_mp: str) -> bool:
    """Barreira conservadora contra associações semanticamente incompatíveis sugeridas pela IA.

    Exige que os termos específicos do nome do cadastro apareçam na descrição do fornecedor.
    Se não aparecerem, não tenta adivinhar sinônimos: deixa o item para revisão manual.
    """
    exigidos = _termos_identidade(nome_mp)
    texto = unicodedata.normalize("NFKD", descricao or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    presentes = set(re.findall(r"[a-z0-9]+", texto))
    if "mac" in presentes and "conkey" in presentes:
        presentes.add("macconkey")
    # Variação ortográfica comum em Mueller/Muller e abreviação UTIC/UTI.
    if "mueller" in exigidos and "muller" in presentes:
        presentes.add("mueller")
    if "muller" in exigidos and "mueller" in presentes:
        presentes.add("muller")
    if "uti" in exigidos and "utic" in presentes:
        presentes.add("uti")
    if "utic" in exigidos and "uti" in presentes:
        presentes.add("utic")
    if "triptico" in exigidos and "triptona" in presentes:
        presentes.add("triptico")
    if "triptona" in exigidos and "triptico" in presentes:
        presentes.add("triptona")
    # Cadastros genéricos sem termos identificadores não permitem uma validação lexical útil.
    return not exigidos or exigidos.issubset(presentes)



def _normalizar_descricao(txt):
    """Normaliza descrição para comparar linhas dentro do mesmo arquivo."""
    txt = unicodedata.normalize("NFKD", txt or "")
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = txt.lower()
    txt = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:kg|g|gr|mg|ml|l|lt|lts|un|und|fr|frasco)\b", " ", txt)
    txt = re.sub(r"\b\d+(?:[.,]\d+)?\b", " ", txt)
    txt = re.sub(r"[^a-z]+", " ", txt)
    ignorar = {"de", "da", "do", "das", "dos", "com", "para", "em", "e", "un", "und", "frasco", "fr"}
    return {t for t in txt.split() if len(t) > 1 and t not in ignorar}


def _possivel_duplicidade(a, b):
    """Critério conservador: sinaliza sem excluir; não compara arquivos diferentes."""
    ta = _normalizar_descricao(a.get("descricao_forn"))
    tb = _normalizar_descricao(b.get("descricao_forn"))
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    uniao = ta | tb
    jaccard = len(ta & tb) / len(uniao) if uniao else 0
    texto_a, texto_b = " ".join(sorted(ta)), " ".join(sorted(tb))
    similaridade = SequenceMatcher(None, texto_a, texto_b).ratio()
    return jaccard >= 0.88 or similaridade >= 0.94


def _marcar_duplicidades_mesmo_documento(items, pend, filename, fornecedor):
    """Marca pares suspeitos dentro de uma cotação; preserva todas as linhas."""
    for idx, atual in enumerate(items):
        for j in range(idx):
            anterior = items[j]
            num_atual = str(atual.get("numero_item") or "").strip()
            num_anterior = str(anterior.get("numero_item") or "").strip()
            mesmo_numero = bool(num_atual and num_anterior and num_atual == num_anterior)
            if not (mesmo_numero or _possivel_duplicidade(atual, anterior)):
                continue
            detalhe = (
                f"Possível produto repetido na mesma cotação: "
                f"'{anterior['descricao_forn']}'"
                f"{f' (item {num_anterior})' if num_anterior else ''} / "
                f"'{atual['descricao_forn']}'"
                f"{f' (item {num_atual})' if num_atual else ''}. "
                "As duas linhas foram mantidas; conferir no documento original."
            )
            anterior["alertas"].append("Possível duplicidade na cotação; conferir")
            atual["alertas"].append("Possível duplicidade na cotação; conferir")
            pend.append(_p(filename, fornecedor, "aviso", "duplicidade", detalhe))


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
        cod_sugerido = i.get("cod")
        duvida = (i.get("duvida") or "").strip()
        conformidade = (i.get("alerta_conformidade") or "").strip()
        # A associação só passa se: código existe, não há dúvida de identidade e a descrição
        # contém os termos específicos do nome do MP. Marca/especificações continuam sendo
        # avaliadas separadamente como conformidade.
        cod = cod_sugerido if cod_sugerido in lista and not duvida else None
        if cod and not _descricao_compativel_com_mp(desc, lista[cod]):
            nome_mp = lista[cod]
            cod = None
            motivo = (f"A descrição '{desc}' não contém os termos identificadores de '{nome_mp}'. "
                      "A associação sugerida pela IA foi bloqueada para evitar confundir produtos diferentes.")
            alertas_bloqueio = True
            pend.append(_p(filename, forn, "aviso", "identidade_incompativel", motivo))
        else:
            alertas_bloqueio = False
        fator, base = conteudo_unidade(i.get("unidade"), desc, i.get("fator_base"), i.get("unidade_base"))
        icms = i.get("icms_pct")
        alertas = []
        if alertas_bloqueio:
            alertas.append("Associação MP bloqueada: descrição incompatível com o produto cadastrado")
        if duvida:
            alertas.append(f"Associação MP pendente: {duvida}")
            pend.append(_p(filename, forn, "aviso", "duvida",
                           f"{cod_sugerido or 'Sem código'} – {desc}: {duvida}. Associação automática bloqueada; conferir manualmente."))
        if conformidade:
            alertas.append(f"Conferir conformidade: {conformidade}")
            pend.append(_p(filename, forn, "aviso", "conformidade",
                           f"{cod or cod_sugerido or 'Sem código'} – {desc}: {conformidade}. Produto identificado; verificar se atende às exigências do comprador."))
        if not duvida and cod_sugerido and cod_sugerido not in lista:
            alertas.append("Código MP inválido; conferir associação")
            pend.append(_p(filename, forn, "aviso", "cod_invalido",
                           f"{desc}: a IA retornou o código {cod_sugerido}, que não existe na lista carregada."))
        if cod and not fator:
            alertas.append("Conteúdo da unidade (g/mL) não identificado")
            pend.append(_p(filename, forn, "aviso", "fator", f"{cod} – {desc}: conteúdo da unidade não identificado; fica fora da planilha até preencher 'g/FR' na tabela"))
        if cod and dias is None:
            alertas.append("Prazo de pagamento não identificado")
        if cod and frete is None:
            alertas.append("Tipo de frete não identificado (assumido CIF)")
        if cod and cambio and cambio != 1.0:
            alertas.append(f"Convertido de US$ (câmbio {cambio:.4f})")
        items.append({"arquivo": filename, "fornecedor": forn, "numero_item": i.get("numero_item"),
                      "codigo_fabricante": i.get("codigo_fabricante"), "cod": cod,
                      "descricao_forn": desc, "marca": i.get("marca"),
                      "qtde_g": i["quantidade"] * fator if fator else None, "fr_g": fator, "um": base,
                      "preco_fr": i["preco_unitario"] * cambio if cambio else None,
                      "icms": icms / 100 if icms is not None else None, "ipi": (i.get("ipi_pct") or 0) / 100,
                      "frete": frete or "CIF", "prazo_dias": dias, "pgto": doc.get("condicao_pagamento") or "",
                      "entrega": i.get("prazo_entrega_dias"), "alertas": alertas})
    _marcar_duplicidades_mesmo_documento(items, pend, filename, forn)
    return items, pend


def process_all(docs: list, lista: dict):
    """docs = [(nome_arquivo, dict_extraido)]; lista = {COD: NOME}.

    Cada arquivo é preservado como uma cotação independente. Não deduplicar entre
    arquivos: versões diferentes do mesmo orçamento devem continuar comparáveis.
    """
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
