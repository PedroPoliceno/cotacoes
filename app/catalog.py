"""Catálogo de MPs + tabela de equivalências (aliases) aprendidas com as correções."""
import json, re, unicodedata
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
ALIASES_FILE = DATA / "aliases.json"

# regras: lista de alternativas; cada alternativa = tokens que devem aparecer TODOS na descrição.
# "=agar" = descrição, sem tamanhos de embalagem, é exatamente "agar".
CATALOGO = {
    "MP32": {"descricao": "Agar MacConkey", "obs": "Verificar concentração",
             "regras": [["macconkey"], ["mac", "conkey"]]},
    "MP15": {"descricao": "Agar Bacteriológico", "obs": "Fotossensível, marca Conda",
             "regras": [["bacteriologico"], ["=agar"]]},
    "MP40": {"descricao": "Agar Triptico de Soja - TSA", "obs": "",
             "regras": [["triptona", "soja"], ["tryptic", "soy"], ["tsa"]]},
    "MP76": {"descricao": "Caldo GN", "obs": "", "regras": [["gn", "hajna"]]},
    "MP20": {"descricao": "Agar Cromogênico UTI", "obs": "Termolábil, exceto fornecedor Himedia",
             "regras": [["cromogenico", "utic"], ["cromogenico", "urinario"]]},
}


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _tokens_sem_embalagem(texto: str) -> list:
    return [t for t in norm(texto).split() if not re.fullmatch(r"\d+(g|kg)?", t) and t not in ("frasco", "fr")]


def load_aliases() -> dict:
    return json.loads(ALIASES_FILE.read_text()) if ALIASES_FILE.exists() else {}


def add_alias(descricao: str, cod: str):
    if cod not in CATALOGO:
        raise KeyError(cod)
    al = load_aliases()
    al[norm(descricao)] = cod
    DATA.mkdir(exist_ok=True)
    ALIASES_FILE.write_text(json.dumps(al, ensure_ascii=False, indent=1))


def match(descricao: str, aliases: dict | None = None):
    """Retorna o COD ou None. Alias (correção humana) tem prioridade sobre as regras."""
    aliases = load_aliases() if aliases is None else aliases
    n = norm(descricao)
    if n in aliases:
        return aliases[n]
    toks = set(n.split())
    for cod, c in CATALOGO.items():
        for regra in c["regras"]:
            if regra == ["=agar"]:
                if _tokens_sem_embalagem(descricao) == ["agar"]:
                    return cod
            elif all(t in toks for t in regra):
                return cod
    return None
