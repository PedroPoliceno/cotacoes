"""As 3 cotações reais (transcritas dos PDFs) no formato que a IA devolve."""
def I(desc, q, p, t, marca=None, pack=None, un="FR", icms=None):
    return dict(descricao=desc, quantidade=q, preco_unitario=p, total_linha=t, marca=marca, unidade=un,
                tamanho_embalagem_g=pack, icms_pct=icms)

CRAL = dict(fornecedor="CRAL ARTIGOS PARA LABORATÓRIO LTDA", cnpj_fornecedor="48.740.849/0007-13",
    condicao_pagamento="Pagamento Antecipado", tipo_frete="CIF", total_documento=198371.24, itens=[
    I("PEPTONA DE CASEINA FRASCO 500G", 6, 412.76, 2476.56, "HIMEDIA", icms=12),
    I("AGAR CROMOGENICO INFECCOES DO TRATO URINARIO (UTIC) 500G", 140, 864.97, 121095.80, "HIMEDIA", icms=12),
    I("AGAR TRIPTONA DE SOJA (TSA) FRASCO 500G", 60, 312.30, 18738.00, "HIMEDIA", icms=12),
    I("AGAR FUNGOBIOTICO (MYCOBIO) 500G", 10, 3125.00, 31250.00, "HIMEDIA", icms=12),
    I("GN CALDO HAJNA FRASCO 500G", 1, 330.00, 330.00, "HIMEDIA", icms=12),
    I("AGAR BASE BACILLUS CEREUS (MYP) FRASCO 500G", 1, 479.94, 479.94, "HIMEDIA", icms=12),
    I("AGAR GRAU BACTERIOLOGICO FRASCO 500G", 8, 286.28, 2290.24, "HIMEDIA", icms=12),
    I("AGAR SABOURAUD DEXTROSE GRANULADO FRASCO 500G", 18, 283.65, 5105.70, "HIMEDIA", icms=12),
    I("AGAR MAC CONKEY COM CRISTAL VIOLETA FRASCO 500G", 60, 276.75, 16605.00, "HIMEDIA", icms=12)])

KASVI = dict(fornecedor="KASVI IMPORTACAO E DISTRIBUICAO DE PRODUTOS PARA LABORATÓRIO LTDA",
    cnpj_fornecedor="13.324.282/0003-96", condicao_pagamento="30/60/90", tipo_frete="FCIF-Emitente",
    total_documento=92688.60, itens=[
    I("AGAR MUELLER HINTON. FRASCO 500 G", 10, 319.50, 3195.00, "KASVI", icms=19.5),
    I("AGAR BACTERIOLÓGICO. FRASCO 500 G", 8, 436.65, 3493.20, "KASVI", icms=19.5),
    I("AGAR CLED. 500 G", 70, 322.50, 22575.00, "KASVI", icms=19.5),
    I("AGAR MACCONKEY. FRASCO 500 G", 60, 280.69, 16841.40, "KASVI", icms=19.5),
    I("AGAR TRIPTONA DE SOJA (TSA). FRASCO 500 G", 60, 456.40, 27384.00, "KASVI", icms=19.5),
    I("AGAR SABOURAUD DEXTROSE. FRASCO 500 G", 60, 320.00, 19200.00, "KASVI", icms=19.5)])

INTERLAB = dict(fornecedor="INTERLAB DISTR. PROD. CIENTÍFICOS LTDA.", cnpj_fornecedor="46.849.303/0001-84",
    condicao_pagamento="28 DIAS", tipo_frete="FOB", total_documento=117159.60, itens=[
    I("LACTOSE PA -25Kg", 1, 698, 698, un="BAR"), I("FUCSINA BASICA (BASIC FUCHSIN) -1000g", 5, 348, 1740),
    I("ENTEROCOCCOSEL AGAR (BILE ESCULIN AZIDE AGAR) -500g", 30, 650, 19500),
    I("AZURE II -1000g", 4, 2200, 8800), I("SABOURAUD DEXTROSE AGAR -500g", 60, 253, 15180),
    I("TRYPTIC SOY AGAR -500g", 60, 326.01, 19560.60), I("XLD AGAR -500g", 6, 427, 2562),
    I("PEPTONA DE CASEINA (TRIPTONA)-1000g", 3, 590, 1770), I("TRIPTOFANO(L-TRIPTOFANO)PUREX -20Kg", 4, 2100, 8400),
    I("MYCOSEL AGAR -500g", 10, 974.84, 9748.40), I("GN BROTH HAJNA -500g", 1, 1663, 1663),
    I("EDTA SAL DISSODICO DIHIDRATADO PA - 1000g", 3, 123.20, 369.60), I("DEXTROSE -1000g", 2, 28, 56),
    I("AGAR -454g", 8, 501.50, 4012), I("CLED AGAR -500g", 70, 330, 23100)])

DOCS = [("CRAL.pdf", CRAL), ("KASVI.pdf", KASVI), ("INTERLAB.pdf", INTERLAB)]

# --- Simula o que o Claude devolve (cod/fornecedor_curto); o casamento real é feito pela IA ---
LISTA = {"MP32": "Agar MacConkey", "MP15": "Agar Bacteriológico", "MP40": "Agar Triptico de Soja - TSA",
         "MP76": "Caldo GN", "MP20": "Agar Cromogênico UTI"}
_REGRAS = [("mac conkey", "MP32"), ("macconkey", "MP32"), ("bacteriologico", "MP15"), ("bacteriológico", "MP15"),
           ("-454g", "MP15"), ("triptona de soja", "MP40"), ("tryptic soy", "MP40"), ("hajna", "MP76"), ("urinario", "MP20")]
for (_, d), curto in zip(DOCS, ("CRALPLAST", "KASVI", "INTERLAB")):
    d["fornecedor_curto"] = curto
    for it in d["itens"]:
        it["cod"] = next((c for k, c in _REGRAS if k in it["descricao"].lower()), None)

import re as _re
for _, _d in DOCS:  # simula fator_base/unidade_base que a IA devolve (conteúdo da unidade de venda)
    for _it in _d["itens"]:
        _m = _re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|g)\b", _it["descricao"].lower())
        if _m and _it.get("unidade") == "FR":
            _it["fator_base"] = float(_m.group(1).replace(",", ".")) * (1000 if _m.group(2) == "kg" else 1)
            _it["unidade_base"] = "g"
