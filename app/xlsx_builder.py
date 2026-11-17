"""Planilha única, um bloco por MP (menor custo final primeiro), fórmulas vivas."""
import io, re
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from .pipeline import custo_final

HEAD = ["COD", "DESCRIÇÃO", "FORNECEDOR", "QTDE", "FR", "UM", "PREÇO FR", "PREÇO UN", "ICMS", "IPI",
        "VALOR TOTAL", "TIPO FRETE", "VALOR FRETE", "PRAZO (em dias)", "CUSTO FINAL", "PRAZO DE PGTO"]
WIDTHS = [8, 40, 14, 10, 8, 6, 11, 11, 8, 8, 12, 11, 12, 15, 13, 16]
F = lambda **k: Font(name="Arial", size=10, **k)


def _ok(it, lista):
    return it.get("cod") in lista and it.get("fr_g") and it.get("preco_fr") is not None


def build_xlsx(items, lista, rend=0.0005, frete_fob=0.05, pendencias=None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Comparativo"
    ws["A1"], ws["B1"] = "rendimento diário", rend
    ws["A2"], ws["B2"] = "frete FOB (% do preço)", frete_fob
    ws["A3"] = "Linha verde = menor custo final do bloco. PREÇO UN e custos em R$ por g (ou mL). Frete FOB estimado pelo % acima."
    ws["B1"].number_format, ws["B2"].number_format = "0.00%", "0.0%"
    for c in ("B1", "B2"):
        ws[c].font = F(color="0000FF")
    ws["A3"].font = F(italic=True, color="595959")
    for c, h in enumerate(HEAD, 1):
        x = ws.cell(4, c, h)
        x.font, x.fill = F(bold=True, color="FFFFFF"), PatternFill("solid", start_color="1F3864", end_color="1F3864")
        x.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[x.column_letter].width = WIDTHS[c - 1]
    grupos = {}
    for it in items:
        if _ok(it, lista):
            grupos.setdefault(it["cod"], []).append(it)
    r = 5
    verde = PatternFill("solid", start_color="C6EFCE", end_color="C6EFCE")
    sep = Border(bottom=Side(style="thin", color="808080"))
    for cod in sorted(grupos, key=lambda c: int(re.sub(r"\D", "", c) or 0)):
        a = r
        desc = lista[cod]
        for it in sorted(grupos[cod], key=lambda x: custo_final(x, rend, frete_fob)):
            vals = [cod, desc, it["fornecedor"], it.get("qtde_g"), it["fr_g"], it.get("um") or "g", it["preco_fr"], f"=G{r}/E{r}",
                    it.get("icms"), it.get("ipi"), f"=H{r}", it.get("frete") or "CIF",
                    f'=IF(L{r}="FOB",H{r}*$B$2,0)', it.get("prazo_dias") or 0,
                    f"=K{r}+M{r}-(K{r}*$B$1*N{r})", it.get("pgto") or ""]
            for c, v in enumerate(vals, 1):
                x = ws.cell(r, c, v)
                x.font = F()
                x.number_format = {4: "#,##0", 5: "#,##0", 7: "#,##0.00", 8: "0.0000", 9: "0.0%", 10: "0.0%",
                                   11: "0.0000", 13: "0.0000", 14: "0", 15: "0.0000"}.get(c, "General")
            r += 1
        ws.conditional_formatting.add(f"A{a}:P{r-1}", FormulaRule(
            formula=[f"$O{a}=MIN($O${a}:$O${r-1})"], fill=verde, font=Font(name="Arial", size=10, bold=True)))
        for c in range(1, 17):
            ws.cell(r - 1, c).border = sep
        r += 1  # linha em branco entre blocos
    ws.freeze_panes = "A5"
    if pendencias:
        wp = wb.create_sheet("Pendências")
        for c, h in enumerate(["Nível", "Arquivo", "Fornecedor", "Mensagem"], 1):
            wp.cell(1, c, h).font = F(bold=True)
        for i, p in enumerate(pendencias, 2):
            for c, k in enumerate(["nivel", "arquivo", "fornecedor", "msg"], 1):
                wp.cell(i, c, p.get(k, "")).font = F()
        for col, w in zip("ABCD", (9, 30, 14, 110)):
            wp.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
