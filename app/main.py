"""API + tela. Rodar: uvicorn app.main:app --host 0.0.0.0 --port 8000"""
import io
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import extractor, pipeline
from .lista import ler_lista
from .xlsx_builder import build_xlsx

app = FastAPI(title="Comparativo de cotações")
MAX_MB = 20


@app.post("/api/process")
async def process(lista: UploadFile = File(...), files: list[UploadFile] = File(...)):
    try:
        itens_lista = ler_lista(await lista.read())
    except Exception as e:
        raise HTTPException(400, f"Lista de produtos: {e}")
    docs, pend = [], []
    for f in files:
        data = await f.read()
        try:
            if len(data) > MAX_MB * 1024 * 1024:
                raise ValueError(f"Arquivo maior que {MAX_MB} MB")
            docs.append((f.filename, await run_in_threadpool(extractor.extract, f.filename, data, itens_lista)))
        except Exception as e:  # um arquivo ruim nÃ£o derruba o lote
            pend.append({"arquivo": f.filename, "fornecedor": "", "nivel": "erro", "tipo": "leitura", "msg": str(e)})
    itens, p2 = pipeline.process_all(docs, itens_lista)
    return {"itens": itens, "pendencias": pend + p2,
            "lista": itens_lista}


class ExportIn(BaseModel):
    itens: list[dict]
    lista: dict
    pendencias: list[dict] = []
    rendimento: float = 0.0005
    frete_fob: float = 0.05
    incluir_pendencias: bool = False


@app.post("/api/export")
def export(e: ExportIn):
    xlsx = build_xlsx(e.itens, e.lista, e.rendimento, e.frete_fob, e.pendencias if e.incluir_pendencias else None)
    return StreamingResponse(io.BytesIO(xlsx), headers={"Content-Disposition": 'attachment; filename="comparativo_cotacoes.xlsx"'},
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="static")
