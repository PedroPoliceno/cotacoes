# Comparativo de cotações

1. Anexar a lista de produtos (xlsx: coluna A = código, coluna B = nome).
2. Anexar as cotações (PDF, imagem, xlsx, csv, txt). Uma chamada ao Claude por cotação extrai os dados e já indica o código da lista.
3. Conferir na tela (itens com dúvida vêm sinalizados) e baixar a planilha única, um bloco por produto.

## Rodar
1. Copie `.env.example` para `.env` e preencha `ANTHROPIC_API_KEY=` com a sua chave.
2. Suba:

       docker build -t cotacoes . && docker run -p 8000:8000 --env-file .env cotacoes
   ou, sem Docker: `pip install -r requirements.txt && uvicorn app.main:app --port 8000 --env-file .env`

Abrir http://localhost:8000 (o `.env` fica fora do Git e da imagem Docker).

## Testes (sem API, sem internet)
    python3 -m unittest tests.test_core -v

## Onde mexer
- `app/lista.py`: leitura da planilha de produtos
- `app/pipeline.py`: parsers de prazo/frete/embalagem, validações, custo final
- `app/schema.py`: campos extraídos pela IA
- `app/xlsx_builder.py`: layout da planilha
