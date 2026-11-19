"""Testes offline do extractor: leitura do arquivo e roteamento (a chamada de rede é simulada)."""
import io, json, sys, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw
from app import extractor as ex

LISTA = {"MP1": "Fucsina"}
OK = json.dumps({"fornecedor": "X", "fornecedor_curto": "X", "itens": [
    {"descricao": "Fucsina", "quantidade": "5,0000", "preco_unitario": "R$ 1.153,10", "total_linha": 5765.5, "cod": "MP1"}]})


def linhas(deitada=False, vazia=False):
    img = Image.new("RGB", (800, 1000), "white")
    if not vazia:
        d = ImageDraw.Draw(img)
        for y in range(100, 900, 14):
            d.rectangle([50, y, 750, y + 5], fill="black")
    return img.rotate(90, expand=True) if deitada else img


def pdf_de(img) -> bytes:
    b = io.BytesIO(); img.save(b, "PDF"); return b.getvalue()


class Leitura(unittest.TestCase):
    def test_numeros_em_texto(self):
        self.assertEqual(ex._num("R$ 1.153,10"), 1153.10)
        self.assertEqual(ex._num("5,0000"), 5.0)
        self.assertEqual(ex._num("1.000"), 1000)
        self.assertEqual(ex._num(3), 3)
        self.assertIsNone(ex._num(None))

    def test_json_com_cerca_e_think(self):
        self.assertEqual(ex._extrair_json('<think>hmm</think>```json\n{"a": 1}\n```'), {"a": 1})

    def test_pagina_deitada(self):
        self.assertFalse(ex._deitada(linhas()))
        self.assertTrue(ex._deitada(linhas(deitada=True)))

    def test_png_que_e_jpeg(self):
        b = io.BytesIO(); linhas().save(b, "JPEG")
        texto, imgs = ex.ler_documento("print.png", b.getvalue())
        self.assertEqual((texto, len(imgs)), ("", 1))

    def test_pdf_escaneado_vira_imagem_e_pagina_em_branco_some(self):
        self.assertEqual(len(ex.ler_documento("a.pdf", pdf_de(linhas(deitada=True)))[1]), 1)
        self.assertEqual(ex.ler_documento("a.pdf", pdf_de(linhas(vazia=True))), ("", []))


class Roteamento(unittest.TestCase):
    def test_escaneado_usa_visao_sem_json_mode(self):
        with mock.patch.object(ex, "_groq", return_value=OK) as g:
            d = ex.extract("a.pdf", pdf_de(linhas()), LISTA)
        modelo, msgs, json_mode = g.call_args.args[0], g.call_args.args[1], g.call_args.kwargs["json_mode"]
        self.assertEqual(modelo, ex.GROQ_VISION_MODEL)
        self.assertFalse(json_mode)
        self.assertEqual(msgs[1]["content"][1]["type"], "image_url")  # a imagem realmente é enviada
        self.assertEqual(d["itens"][0]["preco_unitario"], 1153.10)    # número em texto foi convertido

    def test_texto_usa_modelo_de_texto(self):
        with mock.patch.object(ex, "_groq", return_value=OK) as g:
            ex.extract("a.txt", b"Fucsina 5 x 1153,10", LISTA)
        self.assertEqual((g.call_args.args[0], g.call_args.kwargs["json_mode"]), (ex.GROQ_MODEL, True))

    def test_resposta_invalida_tenta_de_novo(self):
        with mock.patch.object(ex, "_groq", side_effect=["isto nao e json", OK]) as g:
            ex.extract("a.txt", b"x", LISTA)
        self.assertEqual(g.call_count, 2)

    def test_arquivo_sem_conteudo_nao_chama_ia(self):
        with mock.patch.object(ex, "_groq") as g, self.assertRaises(ValueError):
            ex.extract("a.pdf", pdf_de(linhas(vazia=True)), LISTA)
        g.assert_not_called()

    def test_reserva_so_para_texto(self):
        with mock.patch.object(ex, "_groq", side_effect=RuntimeError("limite")), \
             mock.patch.object(ex, "_cloudflare", return_value=OK) as cf:
            ex.extract("a.txt", b"x", LISTA)
            cf.assert_called_once()
            cf.reset_mock()
            with self.assertRaises(RuntimeError):  # imagem: reserva (sem visão) não pode ser usada
                ex.extract("a.pdf", pdf_de(linhas()), LISTA)
            cf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
