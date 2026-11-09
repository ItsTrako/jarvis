"""Prepara texto en español para la síntesis de voz.

Las voces multilingües (p. ej. en-US-AndrewMultilingualNeural) deciden el idioma por fragmentos: cifras,
símbolos y unidades sueltas ("11.6°C", "13.6 km/h", "09/11/2026") no tienen idioma propio y acaban leídos en
inglés. Aquí se convierten en palabras españolas para que toda la frase suene en español.
"""

from __future__ import annotations

import re

_UNI = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
        "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno",
        "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho",
        "veintinueve"]
_DEC = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
_CEN = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos",
        "ochocientos", "novecientos"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]


def _menor_mil(n: int) -> str:
    if n == 100:
        return "cien"
    c, r = divmod(n, 100)
    partes = [_CEN[c]] if c else []
    if r:
        if r < 30:
            partes.append(_UNI[r])
        else:
            d, u = divmod(r, 10)
            partes.append(_DEC[d] + (f" y {_UNI[u]}" if u else ""))
    return " ".join(partes)


def numero(n: int) -> str:
    """Entero a palabras en español (hasta billones)."""
    if n < 0:
        return "menos " + numero(-n)
    if n < 1000:
        return _menor_mil(n) if n else "cero"
    for div, sing, plur in ((10**12, "un billón", "billones"), (10**6, "un millón", "millones")):
        if n >= div:
            q, r = divmod(n, div)
            cab = sing if q == 1 else f"{numero(q)} {plur}"
            return cab + (f" {numero(r)}" if r else "")
    q, r = divmod(n, 1000)
    cab = "mil" if q == 1 else f"{numero(q)} mil"
    return cab + (f" {_menor_mil(r)}" if r else "")


def _apocope(s: str) -> str:
    # "veintiuno grados" -> "veintiún grados", "uno por ciento" -> "un por ciento"
    return re.sub(r"\b(veinti)?uno$", lambda m: (m.group(1) or "") + ("ún" if m.group(1) else "un"), s)


def decimal(txt: str) -> str:
    """'11.6' / '11,6' / '1.861,6' -> palabras ('once coma seis')."""
    t = txt.strip()
    neg = t.startswith("-")
    t = t.lstrip("-")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", t):  # miles con punto al estilo español
        t = t.replace(".", "")
    t = t.replace(",", ".")
    if "." in t:
        ent, dec = t.split(".", 1)
        dec = dec.rstrip("0")
        base = numero(int(ent or 0))
        if dec:
            # "0,05" -> "cero coma cero cinco"; "11,6" -> "once coma seis"; "3,25" -> "tres coma veinticinco"
            ceros = len(dec) - len(dec.lstrip("0"))
            resto = dec.lstrip("0")
            base += " coma " + " ".join(["cero"] * ceros + ([numero(int(resto))] if resto else []))
    else:
        base = numero(int(t))
    return ("menos " if neg else "") + base


_NUM = r"-?\d+(?:[.,]\d+)*"


def _fecha(m: re.Match) -> str:
    d, mes, a = int(m.group(1)), int(m.group(2)), m.group(3)
    if not (1 <= d <= 31 and 1 <= mes <= 12):
        return m.group(0)
    s = f"{'uno' if d == 1 else numero(d)} de {_MESES[mes - 1]}"
    if a:
        a = int(a) + (2000 if len(a) == 2 else 0)
        s += f" de {numero(a)}"
    return s


def _hora(m: re.Match) -> str:
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 24 or mi > 59:
        return m.group(0)
    hs = re.sub(r"uno$", "una", numero(h))  # la una, las veintiuna
    if mi == 0:
        return f"{hs} en punto"
    return f"{hs} y {numero(mi)}"


def _iso(m: re.Match) -> str:
    a, mes, d = m.group(1), int(m.group(2)), int(m.group(3))
    if not (1 <= mes <= 12 and 1 <= d <= 31):
        return m.group(0)
    return f"{'uno' if d == 1 else numero(d)} de {_MESES[mes - 1]} de {numero(int(a))}"


UNIDADES = [
    (r"°\s*C\b|ºC\b|° ?centígrados", "grados"),
    (r"°\s*F\b", "grados Fahrenheit"),
    (r"[°º]", "grados"),
    (r"km/h\b|kmh\b", "kilómetros por hora"),
    (r"m/s\b", "metros por segundo"),
    (r"km\b", "kilómetros"),
    (r"kg\b", "kilos"),
    (r"cm\b", "centímetros"),
    (r"mm\b", "milímetros"),
    (r"GB\b", "gigas"),
    (r"MB\b", "megas"),
    (r"TB\b", "teras"),
    (r"KB/s\b", "kilobytes por segundo"),
    (r"MHz\b", "megahercios"),
    (r"GHz\b", "gigahercios"),
    (r"W\b", "vatios"),
    (r"%", "por ciento"),
    (r"€", "euros"),
    (r"\$", "dólares"),
    (r"h\b", "horas"),
    (r"min\b", "minutos"),
    (r"s\b", "segundos"),
]
_UNIDAD_RE = [(re.compile(rf"({_NUM})\s*(?:{pat})"), rep) for pat, rep in UNIDADES]

ABREVIATURAS = [(r"\bmáx\.", "máxima"), (r"\bmín\.", "mínima"), (r"\baprox\.", "aproximadamente"),
                (r"\bp\. ?ej\.", "por ejemplo"), (r"\betc\.", "etcétera"), (r"\bn\.?º", "número"),
                (r"\bvs\.?(?=\s)", "contra"), (r"\bSr\.", "señor"), (r"\bSra\.", "señora")]


def _unidad(m: re.Match, rep: str) -> str:
    val = decimal(m.group(1))
    if val in ("uno", "menos uno") and not rep.startswith("por"):
        partes = rep.split(" ", 1)  # singular: "un grado", "un kilómetro por hora"
        rep = " ".join([re.sub(r"s$", "", partes[0])] + partes[1:])
    return f"{_apocope(val)} {rep}"


_NO_APOCOPE = {"de", "del", "y", "o", "coma", "por", "a", "en", "punto", "más", "menos"}


def _suelto(m: re.Match, texto: str) -> str:
    val = decimal(m.group(0))
    sig = re.match(r"\s+([^\W\d_]+)", texto[m.end():])
    if sig and sig.group(1).lower() not in _NO_APOCOPE and " coma " not in val:
        val = _apocope(val)  # "treinta y un días", "veintiún años"
    return val


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF️‍←-⇿⬀-⯿]")


def normalizar(texto: str) -> str:
    t = _EMOJI.sub("", texto)
    t = re.sub(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", _iso, t)
    t = re.sub(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?\b", _fecha, t)
    t = re.sub(r"\b(\d{1,2}):(\d{2})(?::\d{2})?\b", _hora, t)
    for pat, rep in ABREVIATURAS:
        t = re.sub(pat, rep, t, flags=re.I)
    t = re.sub(r"\b(entre\s+-?\d+(?:[.,]\d+)?)\s*[-–]\s*(\d)", r"\1 y \2", t, flags=re.I)
    t = re.sub(r"(\d)\s*[-–]\s*(\d)", r"\1 a \2", t)  # rangos "9-14" -> "9 a 14"
    for rx, rep in _UNIDAD_RE:
        t = rx.sub(lambda m, rep=rep: _unidad(m, rep), t)
    src = t
    t = re.sub(r"(?<![\w.,])" + _NUM + r"(?![\w])", lambda m: _suelto(m, src), t)
    t = re.sub(r"\s*&\s*", " y ", t)
    t = re.sub(r"\s*\+\s*", " más ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()
