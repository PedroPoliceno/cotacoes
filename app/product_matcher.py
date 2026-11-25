import re, unicodedata
from rapidfuzz import fuzz, process

def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()

def pontuar(a, b):
    por_tokens = fuzz.token_set_ratio(a, b)
    sem_espaco = fuzz.ratio(a.replace(" ", ""), b.replace(" ", ""))
    return max(por_tokens, sem_espaco)

def buscar(consulta, nomes, limiar=80):
    q = normalizar(consulta)
    resultados = []
    for nome in nomes:
        score = pontuar(q, normalizar(nome))
        if score >= limiar:
            resultados.append((nome, score))
    return sorted(resultados, key=lambda x: -x[1])
