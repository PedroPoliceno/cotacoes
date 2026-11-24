"""Schema de extração (tool use). A IA só LÊ o documento; contas ficam em código."""
NUM = {"type": ["number", "null"]}
STR = {"type": ["string", "null"]}

COTACAO_TOOL = {
    "name": "registrar_cotacao",
    "description": "Registra os dados extraídos de uma cotação de fornecedor.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fornecedor": {"type": "string", "description": "Razão social do fornecedor (quem emitiu a cotação)"},
            "fornecedor_curto": {"type": "string", "description": "Nome da marca do fornecedor em UMA palavra, MAIÚSCULAS, sem LTDA/COMERCIAL/INDUSTRIA (ex.: KASVI, NEON, INTERLAB, QUIMIDROL)"},
            "numero_cotacao": STR,
            "data_cotacao": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            "validade_proposta": STR,
            "condicao_pagamento": {"type": ["string", "null"], "description": "Texto como no documento: '30/60/90', '28 DIAS', 'Pagamento Antecipado'"},
            "tipo_frete": {"type": ["string", "null"], "description": "CIF, FOB ou texto original"},
            "pedido_minimo": NUM,
            "moeda": {"type": "string", "description": "BRL ou USD: moeda em que os preços unitários estão escritos"},
            "total_documento_brl": {"type": ["number", "null"], "description": "Só para cotação em dólar: total do documento em R$, se o documento informar"},
            "total_documento": {"type": ["number", "null"], "description": "Total do documento na moeda dos preços unitários"},
            "itens": {"type": "array", "items": {"type": "object", "properties": {
                "cod": {"type": ["string", "null"], "description": "COD da lista do comprador somente quando a identidade do produto for a mesma; divergências de marca/especificação vão em alerta_conformidade e não impedem o COD. Se a identidade for incerta ou for outro produto, use null"},
                "duvida": {"type": ["string", "null"], "description": "Somente dúvida sobre a identidade do produto; se preenchido, cod deve ser null"},
                "alerta_conformidade": {"type": ["string", "null"], "description": "Divergência de marca, fornecedor, concentração, especificação ou outra exigência; não impede preencher cod quando a identidade do produto é a mesma"},
                "numero_item": STR,
                "codigo_fabricante": STR,
                "descricao": {"type": "string", "description": "Descrição completa do produto, sem resumir"},
                "marca": STR,
                "quantidade": {"type": "number", "description": "Quantidade em unidades de venda (ex.: nº de frascos)"},
                "unidade": STR,
                "unidade_base": {"type": ["string", "null"], "description": "'g' se a unidade de venda é de massa (KG, G, FR de pó...), 'mL' se é de volume (LITRO, LT, mL)"},
                "fator_base": {"type": ["number", "null"], "description": "Quanto vale UMA unidade em que o PREÇO é cobrado, em g ou mL: KG=1000, LITRO=1000, FR de 500 g=500, bombona vendida por bombona de 30 kg=30000. Não use tamanhos citados na descrição se o preço é por kg ou litro"},
                "preco_unitario": {"type": "number"},
                "icms_pct": NUM, "ipi_pct": NUM,
                "total_linha": {"type": "number"},
                "prazo_entrega_dias": STR,
            }, "required": ["descricao", "quantidade", "preco_unitario", "total_linha"]}},
            "conflito": {"type": ["string", "null"], "description": "Se o documento se contradisser (pagamento, frete, preços), descreva em uma frase; senão null"},
            "observacoes": STR,
        },
        "required": ["fornecedor", "fornecedor_curto", "itens"],
    },
}
