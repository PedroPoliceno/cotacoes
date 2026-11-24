import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import io, openpyxl
from app.lista import ler_lista
from app.pipeline import prazo_pgto_dias, tipo_frete, process_all, custo_final
from app.xlsx_builder import build_xlsx
from tests.fixtures import DOCS, LISTA


class Core(unittest.TestCase):
    def setUp(self):
        self.itens, self.pend = process_all(DOCS, LISTA)

    def test_parsers(self):
        self.assertEqual(prazo_pgto_dias("30/60/90"), 60)
        self.assertEqual(prazo_pgto_dias("28 DIAS"), 28)
        self.assertEqual(prazo_pgto_dias("Pagamento Antecipado"), 0)
        self.assertEqual(tipo_frete("FCIF-Emitente"), "CIF")

    def test_totais_fecham(self):  # os 3 PDFs reais: nenhuma divergência de total/linha
        self.assertEqual([p for p in self.pend if p["nivel"] == "erro"], [])

    def test_casamento_usa_so_a_lista(self):
        por = {}
        for i in self.itens:
            if i["cod"]:
                por.setdefault(i["cod"], []).append(i["fornecedor"])
        self.assertEqual(sorted(por["MP15"]), ["CRALPLAST", "KASVI"])  # 'AGAR -454g' não prova ser Agar Bacteriológico
        self.assertEqual(por["MP20"], ["CRALPLAST"])
        # COD inventado pela IA (fora da lista) é descartado
        from app.pipeline import process_doc
        doc = dict(fornecedor_curto="X", itens=[dict(descricao="Y", quantidade=1, preco_unitario=1, total_linha=1, cod="MP99")])
        self.assertIsNone(process_doc("x", doc, LISTA)[0][0]["cod"])

    def test_aviso_produto_sem_cotacao(self):
        _, pend = process_all(DOCS, {**LISTA, "MP99": "Naftol"})
        self.assertTrue(any(p["tipo"] == "sem_cotacao" and "MP99 Naftol" in p["msg"] for p in pend))
        self.assertFalse(any(p["tipo"] == "sem_cotacao" for p in self.pend))  # lista completa: sem aviso

    def test_aviso_restricao(self):
        from app.pipeline import process_doc
        doc = dict(fornecedor_curto="CRALPLAST", itens=[dict(descricao="AGAR CROMOGENICO UTIC", quantidade=1, preco_unitario=1,
                   total_linha=1, cod="MP20", alerta_conformidade="Lista exige outra marca; cotação é HiMedia")])
        itens, pend = process_doc("x", doc, LISTA)
        self.assertEqual(itens[0]["cod"], "MP20")  # identidade preservada; conformidade sinalizada
        self.assertTrue(any(p["tipo"] == "conformidade" and "HiMedia" in p["msg"] for p in pend))

    def test_barreira_identidade_nao_confunde_meios_de_cultura(self):
        from app.pipeline import process_doc
        lista = {"MP19": "Agar CLED (Verificar concentração e fotossensível Marca Conda)",
                 "MP339": "Agar Mueller Hinton - Conda"}
        doc = dict(fornecedor_curto="INTERLAB", itens=[
            dict(descricao="CHROMAGAR ORIENTATION -500g", quantidade=1, preco_unitario=10, total_linha=10, cod="MP339"),
            dict(descricao="CLED AGAR -500g", quantidade=1, preco_unitario=10, total_linha=10, cod="MP19",
                 alerta_conformidade="Marca BBL/USA; lista exige Conda"),
            dict(descricao="AGAR MUELLER HINTON FRASCO 500G", quantidade=1, preco_unitario=10, total_linha=10, cod="MP339",
                 alerta_conformidade="Marca KASVI; lista exige Conda"),
        ])
        itens, pend = process_doc("x", doc, lista)
        self.assertIsNone(itens[0]["cod"])
        self.assertEqual(itens[1]["cod"], "MP19")
        self.assertEqual(itens[2]["cod"], "MP339")
        self.assertTrue(any(p["tipo"] == "identidade_incompativel" and "CHROMAGAR" in p["msg"] for p in pend))
        self.assertFalse(any(p["tipo"] == "cod_invalido" and "CHROMAGAR" in p["msg"] for p in pend))

    def test_duvida_de_identidade_bloqueia_associacao(self):
        from app.pipeline import process_doc
        doc = dict(fornecedor_curto="X", itens=[dict(descricao="Produto parecido", quantidade=1,
                   preco_unitario=1, total_linha=1, cod="MP20", duvida="Não é possível confirmar a identidade")])
        itens, pend = process_doc("x", doc, LISTA)
        self.assertIsNone(itens[0]["cod"])
        self.assertTrue(any(p["tipo"] == "duvida" for p in pend))

    def test_preco_por_kg_nao_usa_embalagem_da_descricao(self):  # bug: glicerina 16,39/KG virou /30.000 g
        from app.pipeline import process_doc
        doc = dict(fornecedor_curto="QUIMIDROL", condicao_pagamento="28/35/42 DIAS", tipo_frete="Não informado", itens=[
            dict(descricao="GLICERINA BB 30KG", quantidade=390, unidade="KG", preco_unitario=16.39, total_linha=6392.10,
                 cod="MP133", fator_base=1000, unidade_base="g")])
        it = process_doc("q", doc, {"MP133": "Glicerina"})[0][0]
        self.assertEqual(it["qtde_g"], 390000)
        self.assertAlmostEqual(custo_final(it), 0.01639 * (1 - 0.0005 * 35), 6)

    def test_dolar_usa_cambio_do_documento(self):
        from app.pipeline import process_doc
        item = dict(descricao="ACETONA", quantidade=400, unidade="LT", preco_unitario=2.14, total_linha=856.0,
                    cod="MP1", fator_base=1000, unidade_base="mL")
        doc = dict(fornecedor_curto="VERQUIMICA", moeda="USD", total_documento=856.0, total_documento_brl=4566.42, itens=[item])
        it, pend = process_doc("v", doc, {"MP1": "Acetona"})
        self.assertAlmostEqual(it[0]["preco_fr"], 11.416, 2)
        self.assertEqual(it[0]["um"], "mL")
        sem_brl = dict(doc, total_documento_brl=None)
        it, pend = process_doc("v", sem_brl, {"MP1": "Acetona"})
        self.assertIsNone(it[0]["preco_fr"])
        self.assertTrue(any(p["tipo"] == "moeda" for p in pend))

    def test_sem_fator_gera_aviso(self):
        from app.pipeline import process_doc
        doc = dict(fornecedor_curto="X", itens=[dict(descricao="Y", quantidade=1, preco_unitario=1, total_linha=1, cod="MP1")])
        self.assertTrue(any(p["tipo"] == "fator" for p in process_doc("x", doc, {"MP1": "Y"})[1]))

    def test_lista(self):
        def xl(rows):
            wb = openpyxl.Workbook(); [wb.active.append(r) for r in rows]
            b = io.BytesIO(); wb.save(b); return b.getvalue()
        self.assertEqual(ler_lista(xl([["COD", "NOME"], ["MP1", "Naftol"], [None, None], ["MP2", "Dextrose"]])), {"MP1": "Naftol", "MP2": "Dextrose"})
        self.assertEqual(ler_lista(xl([["MP1", "Naftol"]])), {"MP1": "Naftol"})  # sem cabeçalho
        with self.assertRaises(ValueError): ler_lista(xl([["MP1", "A"], ["MP1", "B"]]))
        with self.assertRaises(ValueError): ler_lista(xl([["MP1", None]]))

    def test_ranking_mp32_inverte_com_antecipado(self):
        m = {i["fornecedor"]: custo_final(i) for i in self.itens if i["cod"] == "MP32"}
        self.assertAlmostEqual(m["KASVI"], 0.5445, 4)
        self.assertAlmostEqual(m["CRALPLAST"], 0.5535, 4)
        self.assertLess(m["KASVI"], m["CRALPLAST"])

    def test_agar_generico_nao_cria_divergencia_de_quantidade(self):
        # INTERLAB informa apenas 'AGAR -454g'; não é seguro inferir Agar Bacteriológico.
        self.assertFalse(any(p["tipo"] == "qtde" and "MP15" in p["msg"] for p in self.pend))

    def test_xlsx(self):
        Path("/tmp/comparativo_teste.xlsx").write_bytes(build_xlsx(self.itens, LISTA, pendencias=self.pend))


if __name__ == "__main__":
    unittest.main()
