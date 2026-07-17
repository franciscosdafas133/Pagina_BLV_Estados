"""Clasificación sectorial curada de emisores conocidos de la BVL/SMV.

La SMV no expone el sector en el catálogo de Información Financiera, por lo
que se usa: (1) este mapeo curado por palabra clave en la razón social y
(2) la detección de entidades financieras por nombre (config.FINANCIAL_NAME_KEYWORDS).
Las empresas no clasificadas quedan en "Sin clasificar" (nunca se inventa el dato).
"""
from app.config import FINANCIAL_NAME_KEYWORDS
from app.smv.account_mapping import normalize_text

# patrón (subcadena en el nombre normalizado) -> (sector, es_financiero)
SECTOR_KEYWORDS = [
    # Financieras
    ("banco", ("Bancos", True)),
    ("interbank", ("Bancos", True)),
    ("scotiabank", ("Bancos", True)),
    ("bbva", ("Bancos", True)),
    ("mibanco", ("Bancos", True)),
    ("credicorp", ("Bancos", True)),
    ("intercorp financial", ("Bancos", True)),
    ("financiera", ("Financieras", True)),
    ("caja municipal", ("Cajas", True)),
    ("caja rural", ("Cajas", True)),
    ("afp", ("AFP", True)),
    ("seguros", ("Seguros", True)),
    ("reaseguro", ("Seguros", True)),
    ("rimac", ("Seguros", True)),
    ("pacifico compania de seguros", ("Seguros", True)),
    ("leasing", ("Financieras", True)),
    ("edpyme", ("Financieras", True)),
    ("hipotecaria", ("Financieras", True)),
    ("fondo", ("Fondos", True)),
    # Mineras
    ("minera", ("Minería", False)),
    ("minas", ("Minería", False)),
    ("minsur", ("Minería", False)),
    ("buenaventura", ("Minería", False)),
    ("volcan", ("Minería", False)),
    ("nexa resources", ("Minería", False)),
    ("cerro verde", ("Minería", False)),
    ("southern", ("Minería", False)),
    ("shougang", ("Minería", False)),
    ("poderosa", ("Minería", False)),
    ("brocal", ("Minería", False)),
    ("atacocha", ("Minería", False)),
    ("corona", ("Minería", False)),
    # Energía y saneamiento
    ("electric", ("Energía", False)),
    ("electro", ("Energía", False)),
    ("edegel", ("Energía", False)),
    ("enel", ("Energía", False)),
    ("engie", ("Energía", False)),
    ("luz del sur", ("Energía", False)),
    ("hidrandina", ("Energía", False)),
    ("egasa", ("Energía", False)),
    ("egesur", ("Energía", False)),
    ("san gaban", ("Energía", False)),
    ("kallpa", ("Energía", False)),
    ("termochilca", ("Energía", False)),
    ("gas natural", ("Energía", False)),
    ("calidda", ("Energía", False)),
    ("petroleo", ("Energía", False)),
    ("petroperu", ("Energía", False)),
    ("refineria", ("Energía", False)),
    ("sedapal", ("Servicios públicos", False)),
    # Industria y construcción
    ("cemento", ("Industriales", False)),
    ("pacasmayo", ("Industriales", False)),
    ("unacem", ("Industriales", False)),
    ("yura", ("Industriales", False)),
    ("siderurg", ("Industriales", False)),
    ("aceros arequipa", ("Industriales", False)),
    ("fabrica", ("Industriales", False)),
    ("industria", ("Industriales", False)),
    ("quimpac", ("Industriales", False)),
    ("explosivos", ("Industriales", False)),
    ("famesa", ("Industriales", False)),
    ("aenza", ("Construcción e ingeniería", False)),
    ("grana y montero", ("Construcción e ingeniería", False)),
    ("cosapi", ("Construcción e ingeniería", False)),
    ("inmobiliari", ("Inmobiliario", False)),
    ("los portales", ("Inmobiliario", False)),
    ("jockey plaza", ("Inmobiliario", False)),
    ("centenario", ("Inmobiliario", False)),
    # Consumo y comercio
    ("alicorp", ("Consumo", False)),
    ("gloria", ("Consumo", False)),
    ("leche", ("Consumo", False)),
    ("backus", ("Consumo", False)),
    ("cerveceria", ("Consumo", False)),
    ("lindley", ("Consumo", False)),
    ("laive", ("Consumo", False)),
    ("san fernando", ("Consumo", False)),
    ("molitalia", ("Consumo", False)),
    ("intradevco", ("Consumo", False)),
    ("falabella", ("Comercio", False)),
    ("ripley", ("Comercio", False)),
    ("cencosud", ("Comercio", False)),
    ("supermercados", ("Comercio", False)),
    ("inretail", ("Comercio", False)),
    ("tiendas", ("Comercio", False)),
    # Agro y pesca
    ("agro", ("Agroindustria", False)),
    ("azucarera", ("Agroindustria", False)),
    ("casa grande", ("Agroindustria", False)),
    ("cartavio", ("Agroindustria", False)),
    ("laredo", ("Agroindustria", False)),
    ("paramonga", ("Agroindustria", False)),
    ("pomalca", ("Agroindustria", False)),
    ("tuman", ("Agroindustria", False)),
    ("san jacinto", ("Agroindustria", False)),
    ("camposol", ("Agroindustria", False)),
    ("pesquera", ("Pesca", False)),
    ("austral group", ("Pesca", False)),
    ("exalmar", ("Pesca", False)),
    # Telecom, transporte y servicios
    ("telefonica", ("Telecomunicaciones", False)),
    ("entel", ("Telecomunicaciones", False)),
    ("america movil", ("Telecomunicaciones", False)),
    ("transporte", ("Transporte", False)),
    ("ferrocarril", ("Transporte", False)),
    ("aeropuertos", ("Transporte", False)),
    ("corporacion aceros", ("Industriales", False)),
    ("holding", ("Holdings", False)),
    ("inversiones", ("Holdings", False)),
]


def classify_company(name: str) -> tuple[str, bool]:
    """Devuelve (sector, es_financiera) a partir de la razón social."""
    n = " " + normalize_text(name) + " "
    for kw, (sector, fin) in SECTOR_KEYWORDS:
        if kw in n:
            return sector, fin
    for kw in FINANCIAL_NAME_KEYWORDS:
        if kw in n:
            return "Servicios financieros", True
    return "Sin clasificar", False
