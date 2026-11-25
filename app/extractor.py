"""Extração com APIs gratuitas: Groq (texto ou visão); Cloudflare só como reserva para documentos 100% texto.

Regra de ouro: o modelo só recebe o que realmente existe no documento.
 - PDF com texto  -> texto da página
 - PDF escaneado / sem texto -> página renderizada em imagem (endireitada se estiver deitada)
 - Imagem (png/jpg) -> a própria imagem (reencodada em JPEG, então a extensão não importa)
"""
import base64, io, json, os, re, time
from pathlib import Path

import pypdfium2 as pdfium
import requests
from PIL import Image, ImageOps

from .schema import COTACAO_TOOL

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")                   # só texto
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
CLOUDFLARE_MODEL = os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")  # só texto
ROTACAO_DEITADA = int(os.getenv("ROTACAO_PAGINA_DEITADA", "-90"))             # -90 = horário, 90 = anti-horário

MAX_SAIDA = int(os.getenv("MAX_SAIDA", "8000"))  # tokens de resposta (o padrão do provedor corta a lista de itens)
MIN_TEXTO = 80        # menos caracteres que isso: a página é imagem
MIN_TINTA = 0.006     # menos tinta que isso: página em branco / só logo
MAX_IMAGENS = 5       # limite do Groq por requisição
IMG = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

PROMPT_BASE = (
    "Extraia todos os itens desta cotação de fornecedor. Copie valores exatamente como aparecem. "
    "Não invente: se um campo não aparecer, use null. Preços e totais são números (ponto decimal).\n\n"
    "Lista de produtos do comprador (COD | NOME):\n{lista}\n\n"
    "Para cada item da cotação, identifique primeiro qual produto ele É e compare essa identidade com a lista do comprador. "
    "Preencha `cod` com o COD quando a identidade do produto for claramente a mesma, mesmo que exista divergência de marca, "
    "fornecedor, embalagem ou alguma especificação exigida pelo comprador. "
    "Nomes em outro idioma, abreviações e sinônimos químicos podem representar o mesmo produto "
    "(ex.: glicose anidra = dextrose, ácido fênico = fenol). "
    "Produto parecido mas diferente (outro tipo de meio de cultura, por exemplo) NÃO é o mesmo: use null.\\n"
    "IMPORTANTE: se o produto for claramente o mesmo, NÃO deixe `cod` null apenas por divergência de marca, "
    "fornecedor, concentração, fotossensibilidade, armazenamento ou outra exigência comercial/técnica. "
    "Nesses casos, preencha `cod` normalmente e descreva a divergência em `alerta_conformidade`. "
    "`duvida` deve ser usado SOMENTE quando não for possível afirmar com segurança que se trata do mesmo produto; "
    "nesse caso, use `cod` null e explique a dúvida. Nunca escolha o produto mais provável.\\n"
    "Não associe produtos apenas porque pertencem à mesma categoria ou compartilham palavras genéricas "
    "(por exemplo, a palavra 'agar'). A identidade deve considerar nome específico, composição e aplicação; "
    "uma exigência de marca não transforma um produto em outro produto.\\n"
    "Registre `numero_item` exatamente como aparece na linha da cotação, se existir; caso contrário use null. "
    "Registre `codigo_fabricante` somente se houver um código/referência explícito no documento; caso contrário use null.\n\n"
    "`quantidade` e `preco_unitario` seguem a unidade de venda da cotação (KG, LITRO, FR...). Preencha `fator_base` e "
    "`unidade_base` com o conteúdo dessa unidade em g ou mL (preço por KG -> 1000 g; por LITRO -> 1000 mL). "
    "Se o preço estiver em dólar, use moeda=USD e informe o total em R$ do documento, se houver.\n"
    "Se o documento se contradisser (ex.: cabeçalho diz 'à vista' e as observações dizem 'boleto 28 dias'), "
    "use a informação mais específica e descreva o conflito em `conflito`.\n\n"
    "Responda SOMENTE com um objeto JSON válido que siga o schema do sistema, sem texto antes ou depois. "
    "Escreva primeiro os campos do cabeçalho (inclusive `total_documento`) e por último `itens`, com TODOS os itens do documento.\n\n"
    "REGRA CRÍTICA SOBRE O FORNECEDOR: A NEWPROV é a empresa COMPRADORA.\n"
    "A NEWPROV nunca deve ser identificada como fornecedora.\n"
    "Não confunda o comprador, destinatário, cliente ou solicitante com o fornecedor.\n"
    "Procure identificar a empresa emissora pelo cabeçalho, logotipo, dados comerciais, CNPJ e informações de contato.\n"
    "Se não conseguir identificar o fornecedor com segurança, não invente um nome. Sinalize a incerteza."
)


# ---------------------------------------------------------------- leitura do arquivo
def _tinta(img: Image.Image) -> float:
    g = img.convert("L").point(lambda p: 255 if p < 160 else 0)
    return sum(g.histogram()[255:]) / (g.size[0] * g.size[1])


def _pixels(img: Image.Image):
    return list(getattr(img, "get_flattened_data", img.getdata)())  # getdata some em Pillow novo


def _deitada(img: Image.Image) -> bool:
    """Texto horizontal gera muita variação entre linhas; página deitada gera entre colunas."""
    d = ImageOps.invert(img.convert("L"))
    var = lambda v: sum((x - sum(v) / len(v)) ** 2 for x in v) / len(v)
    rows, cols = _pixels(d.resize((1, 400), Image.BILINEAR)), _pixels(d.resize((400, 1), Image.BILINEAR))
    vc = var(cols)
    return vc > 0 and var(rows) / vc < 0.5


def _jpeg_b64(img: Image.Image) -> str:
    img = img.convert("RGB")
    img.thumbnail((2000, 2000))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


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


def ler_documento(filename: str, data: bytes):
    """Retorna (texto, [imagens_jpeg_base64])."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        textos, imagens = [], []
        for n, page in enumerate(pdfium.PdfDocument(data), 1):
            t = page.get_textpage().get_text_range().strip()
            if len(t) >= MIN_TEXTO:
                textos.append(f"--- Página {n} ---\n{t.replace(chr(13), '')}")
                continue
            img = page.render(scale=1.6).to_pil()
            if _tinta(img) < MIN_TINTA:
                continue  # página em branco ou só logo
            if _deitada(img):
                img = img.rotate(ROTACAO_DEITADA, expand=True)
            imagens.append(_jpeg_b64(img))
        return "\n".join(textos), imagens
    if ext in IMG:
        return "", [_jpeg_b64(Image.open(io.BytesIO(data)))]
    if ext in (".xlsx", ".xlsm"):
        return _xlsx_text(data), []
    if ext in (".csv", ".txt", ".eml", ".md"):
        return data.decode("utf-8", errors="replace"), []
    raise ValueError(f"Formato não suportado: {ext}")


# ---------------------------------------------------------------- resposta do modelo
def _num(v):
    """'1.234,56' / 'R$ 94,50' / '1.000' -> float. Modelos menores às vezes devolvem número como texto."""
    if v is None or isinstance(v, (int, float)):
        return v
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _extrair_json(conteudo: str) -> dict:
    c = re.sub(r"<think>.*?</think>", "", conteudo or "", flags=re.S)
    a = c.find("{")
    if a < 0:
        raise ValueError("a resposta não contém JSON")
    c = c[a:]
    try:
        return json.loads(c[:c.rfind("}") + 1])
    except json.JSONDecodeError:
        pass
    # resposta cortada no meio: fica com os itens que vieram completos
    prof, em_str, esc, ultimo = 0, False, False, None
    for k, ch in enumerate(c):
        if em_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                em_str = False
        elif ch == '"':
            em_str = True
        elif ch in "{[":
            prof += 1
        elif ch in "}]":
            prof -= 1
            if ch == "}" and prof == 2:  # fechou um item da lista `itens`
                ultimo = k
    if ultimo is None:
        raise ValueError("JSON cortado antes do primeiro item")
    d = json.loads(c[:ultimo + 1] + "]}")
    d["aviso_leitura"] = "A resposta da IA veio cortada; só os itens completos foram aproveitados"
    return d


def _normalizar(d: dict) -> dict:
    if not isinstance(d, dict) or not isinstance(d.get("itens"), list):
        raise ValueError("JSON sem a lista 'itens'")
    for k in ("total_documento", "total_documento_brl", "pedido_minimo"):
        d[k] = _num(d.get(k))
    for it in d["itens"]:
        for k in ("quantidade", "preco_unitario", "total_linha", "icms_pct", "ipi_pct", "fator_base"):
            it[k] = _num(it.get(k))
        faltando = [k for k in ("descricao", "quantidade", "preco_unitario", "total_linha") if it.get(k) in (None, "")]
        if faltando:
            raise ValueError(f"item sem {', '.join(faltando)}: {it.get('descricao')}")
    return d


# ---------------------------------------------------------------- chamadas
def _espera(e) -> float:
    """Segundos pedidos pelo Groq num erro 429 (cabeçalho Retry-After ou 'try again in 1m2.5s')."""
    h = getattr(getattr(e, "response", None), "headers", None) or {}
    if h.get("retry-after"):
        try:
            return float(h["retry-after"])
        except ValueError:
            pass
    m = re.search(r"try again in\s+([0-9hms.]+)", str(e))
    if not m:
        return 20.0
    mult = {"h": 3600, "m": 60, "s": 1, "ms": 0.001}
    return sum(float(v) * mult[u] for v, u in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", m.group(1))) or 20.0


def _groq(modelo: str, messages: list, json_mode: bool) -> str:
    from openai import OpenAI  # import tardio: o sistema sobe mesmo sem a chave
    chave = os.getenv("GROQ_API_KEY")
    if not chave:
        raise RuntimeError("GROQ_API_KEY não configurada")
    kw = {"response_format": {"type": "json_object"}} if json_mode else {}
    cliente = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=chave, timeout=120, max_retries=0)
    for tentativa in range(4):
        try:
            r = cliente.chat.completions.create(model=modelo, messages=messages, temperature=0,
                                                max_completion_tokens=MAX_SAIDA, **kw)
            break
        except Exception as e:
            espera = _espera(e) + 1
            if getattr(e, "status_code", None) == 429 and tentativa < 3 and espera <= 90:
                print(f"[extractor] limite de uso do Groq; aguardando {espera:.0f}s ({tentativa + 1}/3)", flush=True)
                time.sleep(espera)
                continue
            raise
    print(f"[extractor] Groq {modelo}: finish_reason={r.choices[0].finish_reason}", flush=True)
    return r.choices[0].message.content


def _cloudflare(messages: list) -> str:
    conta = os.getenv("ACCOUNT_ID") or os.getenv("CLOUDFLARE_ACCOUNT_ID")
    r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{conta}/ai/v1/chat/completions",
                      headers={"Authorization": f"Bearer {os.getenv('CLOUDFLARE_API_KEY')}"}, timeout=120,
                      json={"model": CLOUDFLARE_MODEL, "messages": messages, "temperature": 0, "max_tokens": MAX_SAIDA,
                            "response_format": {"type": "json_object"}})
    print("[extractor] usou a reserva Cloudflare", flush=True)
    if r.status_code != 200:
        raise RuntimeError(f"Cloudflare {r.status_code}: {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"]


def _mensagens(texto: str, imagens: list, lista: dict) -> list:
    schema = json.dumps(COTACAO_TOOL["input_schema"], ensure_ascii=False, separators=(",", ":"))
    sistema = ("Você é especialista em extrair dados de cotações de fornecedores. Responda APENAS com um objeto JSON "
               f"válido que siga este JSON Schema:\n{schema}")
    prompt = PROMPT_BASE.format(lista="\n".join(f"{c} | {n}" for c, n in lista.items()))
    if texto:
        prompt += f"\n\n--- TEXTO DO DOCUMENTO ---\n{texto}"
    if not imagens:
        usuario = prompt
    else:
        prompt += "\n\nAs imagens a seguir são páginas do documento, já na orientação correta; leia todas."
        usuario = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}} for b in imagens]
    return [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]


def _chamar(fn, messages: list) -> dict:
    """Extrai uma vez; só repete a chamada se o JSON vier inválido.

    Não faz releitura automática para completar totais: essa segunda leitura podia
    devolver novamente itens já extraídos com pequenas diferenças de descrição.
    A divergência de total passa a ser um aviso para conferência humana.
    """
    resposta = fn(messages)
    try:
        d = _normalizar(_extrair_json(resposta))
    except (ValueError, json.JSONDecodeError) as e:
        retry = messages + [{"role": "assistant", "content": resposta or ""},
                            {"role": "user", "content": f"Resposta inválida ({e}). Responda novamente somente com o JSON completo, sem repetir instruções."}]
        d = _normalizar(_extrair_json(fn(retry)))

    total = d.get("total_documento")
    if total is not None:
        soma = sum(i["total_linha"] for i in d["itens"])
        falta = round(total - soma, 2)
        if abs(falta) > 0.05:
            aviso = (
                f"Conferência necessária: total das linhas ({soma:.2f}) difere do total "
                f"do documento ({total:.2f}); diferença de {falta:.2f}. "
                "O sistema não solicitou uma segunda extração automática para evitar duplicar itens."
            )
            anterior = d.get("aviso_leitura")
            d["aviso_leitura"] = f"{anterior} | {aviso}" if anterior else aviso
    return d


def extract(filename: str, data: bytes, lista: dict) -> dict:
    texto, imagens = ler_documento(filename, data)
    if not texto and not imagens:
        raise ValueError("Não consegui ler nenhum conteúdo deste arquivo (sem texto e sem imagem útil)")
    if len(imagens) > MAX_IMAGENS:
        raise ValueError(f"Documento escaneado com {len(imagens)} páginas; o limite é {MAX_IMAGENS}")
    messages = _mensagens(texto, imagens, lista)
    if imagens:  # visão: sem modo JSON (nem todo modelo de visão aceita) e sem reserva (a reserva não enxerga imagem)
        try:
            return _chamar(lambda m: _groq(GROQ_VISION_MODEL, m, json_mode=False), messages)
        except Exception as e:
            raise RuntimeError(f"Falha na leitura por imagem (modelo {GROQ_VISION_MODEL}; confira GROQ_VISION_MODEL): {e}")
    try:
        return _chamar(lambda m: _groq(GROQ_MODEL, m, json_mode=True), messages)
    except Exception as e_groq:
        print(f"[extractor] Groq falhou ({str(e_groq)[:200]}); tentando a reserva Cloudflare", flush=True)
        try:
            d = _chamar(_cloudflare, messages)
            d["aviso_leitura"] = (f"Lido pela reserva Cloudflare (Groq falhou: {str(e_groq)[:100]}). "
                                  "A reserva é mais fraca no casamento com a lista: confira os itens.")
            return d
        except Exception as e_cf:
            raise RuntimeError(f"Groq falhou ({e_groq}) e a reserva Cloudflare também ({e_cf})")
