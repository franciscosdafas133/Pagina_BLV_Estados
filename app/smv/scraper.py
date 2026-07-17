"""Scraper de la SMV (Superintendencia del Mercado de Valores del Perú).

Flujo verificado contra el portal (julio 2026):

1. GET  Frm_InformacionFinanciera  -> formulario ASP.NET WebForms con el
   catálogo de empresas (cboDenominacionSocial), años y trimestres.
2. POST del formulario (con __VIEWSTATE/__EVENTVALIDATION) filtrando por
   empresa y año -> grilla MainContent_grdInfoFinanciera con los filings.
   Las filas "Estados Financieros" enlazan a Frm_DetalleInfoFinanciera.aspx
   con un token ligado a la sesión (se requieren las cookies).
3. GET del detalle -> página con los estados; cada estado se selecciona vía
   postback y se renderiza como tabla (Cuenta | Nota | Periodo actual | Anterior).

El scraper es tolerante a fallos: cualquier estado que no pueda parsearse se
registra y se omite (nunca se inventan cifras).
"""
import re
import time
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

from app.smv.account_mapping import classify_statement, map_accounts, normalize_text

BASE = "https://www.smv.gob.pe/SIMV/"
SEARCH_URL = BASE + "Frm_InformacionFinanciera?data=A70181B60967D74090DCD93C4920AA1D769614EC12"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) proyecto-educativo-analisis"}
THROTTLE_SECONDS = 1.0  # cortesía con el servidor público


@dataclass
class Filing:
    quarter: str          # 'I'..'IV' o 'Anual'
    company_name: str
    doc_type: str
    filing_number: str
    presented_at: str
    detail_url: str | None
    xbrl_url: str | None = None   # archivo estructurado XBRL (fuente preferida)


@dataclass
class ParsedStatement:
    kind: str                      # income | balance | cash_flow
    rows: list = field(default_factory=list)   # [(descripcion, valor_actual)]
    currency: str | None = None
    is_consolidated: bool | None = None


ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}


class SMVScraper:
    def __init__(self, throttle: float = THROTTLE_SECONDS):
        self.client = httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True)
        self.throttle = throttle
        self._form_html: str | None = None

    def close(self):
        self.client.close()

    # ------------------------------------------------------------------ utils
    def _sleep(self):
        time.sleep(self.throttle)

    def _get_form(self) -> str:
        if self._form_html is None:
            self._form_html = self.client.get(SEARCH_URL).text
        return self._form_html

    @staticmethod
    def _hidden_fields(html: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        out = {}
        for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION", "__PREVIOUSPAGE"):
            el = soup.find("input", {"name": name})
            if el:
                out[name] = el.get("value", "")
        return out

    # ------------------------------------------------------------ público
    def list_companies(self) -> list[dict]:
        """Catálogo de empresas del combo de la SMV: [{'smv_id', 'name'}]."""
        soup = BeautifulSoup(self._get_form(), "lxml")
        select = soup.find("select", {"name": "ctl00$MainContent$cboDenominacionSocial"})
        companies = []
        if not select:
            return companies
        for opt in select.find_all("option"):
            val = (opt.get("value") or "").strip()
            name = opt.get_text(strip=True)
            if val and val != "-1" and name:
                companies.append({"smv_id": val, "name": name})
        return companies

    def search_filings(self, smv_id: str, company_name: str, year: int) -> list[Filing]:
        """Filings de una empresa en un año (todos los trimestres)."""
        html = self._get_form()
        data = self._hidden_fields(html)
        data.update({
            "__EVENTTARGET": "", "__EVENTARGUMENT": "", "__LASTFOCUS": "",
            "ctl00$MainContent$TextBox1": company_name,
            "ctl00$MainContent$cboDenominacionSocial": smv_id,
            "ctl00$MainContent$cboAnio": str(year),
            "ctl00$MainContent$cboTrimestre": "-1",
            "ctl00$MainContent$cbBuscar": "Buscar",
        })
        self._sleep()
        resp = self.client.post(SEARCH_URL, data=data)
        return self._parse_grid(resp.text)

    @staticmethod
    def _parse_grid(html: str) -> list[Filing]:
        """Extrae los filings 'Estados Financieros' y les asocia el XBRL del
        mismo trimestre (que aparece en una fila 'Archivo Estructurado XBRL')."""
        soup = BeautifulSoup(html, "lxml")
        grid = soup.find("table", id="MainContent_grdInfoFinanciera")
        if not grid:
            return []

        xbrl_by_quarter: dict[str, str] = {}
        rows = []
        for tr in grid.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue
            quarter = tds[0].get_text(strip=True)
            doc = tds[2].get_text(strip=True)
            xbrl = tr.find("a", href=re.compile(r"documento\.aspx\?vidDoc", re.I))
            if "XBRL" in doc and xbrl:
                # el XBRL más reciente del trimestre (primera fila) gana
                xbrl_by_quarter.setdefault(quarter, xbrl["href"].strip())
            detail = tr.find("a", href=re.compile(r"Frm_DetalleInfoFinanciera", re.I))
            rows.append((quarter, doc, tds, detail))

        filings = []
        for quarter, doc, tds, detail in rows:
            if not doc.startswith("Estados Financieros"):
                continue
            filings.append(Filing(
                quarter=quarter,
                company_name=tds[1].get_text(strip=True),
                doc_type=doc,
                filing_number=tds[3].get_text(strip=True),
                presented_at=tds[4].get_text(strip=True),
                detail_url=(BASE + detail["href"]) if detail else None,
                xbrl_url=xbrl_by_quarter.get(quarter),
            ))
        return filings

    def fetch_xbrl(self, xbrl_url: str):
        """Descarga y parsea el XBRL estructurado de un filing."""
        from app.smv.xbrl import parse_xbrl, prev_year_balance
        self._sleep()
        xml = self.client.get(xbrl_url).text
        return parse_xbrl(xml), prev_year_balance(xml)

    def fetch_statements(self, detail_url: str) -> tuple[list[ParsedStatement], str]:
        """Descarga y parsea los estados financieros de un filing.

        Devuelve (estados, url_fuente). La página de detalle renderiza cada
        estado como tabla; si trae un combo de estados, se recorren por postback.
        """
        self._sleep()
        resp = self.client.get(detail_url)
        html = resp.text
        statements = self._parse_statement_tables(html)

        # Si hay un combo para elegir estado, recorrer las opciones restantes
        soup = BeautifulSoup(html, "lxml")
        combo = None
        for sel in soup.find_all("select"):
            opts_text = " ".join(o.get_text() for o in sel.find_all("option"))
            if classify_statement(opts_text) or "estado" in normalize_text(opts_text):
                combo = sel
                break
        if combo is not None:
            name = combo.get("name")
            seen_kinds = {s.kind for s in statements}
            for opt in combo.find_all("option"):
                kind = classify_statement(opt.get_text())
                if not kind or kind in seen_kinds:
                    continue
                data = self._hidden_fields(html)
                data.update({"__EVENTTARGET": name, "__EVENTARGUMENT": "", "__LASTFOCUS": "",
                             name: opt.get("value", "")})
                self._sleep()
                page = self.client.post(detail_url, data=data).text
                for st in self._parse_statement_tables(page):
                    if st.kind not in seen_kinds:
                        statements.append(st)
                        seen_kinds.add(st.kind)
        return statements, detail_url

    @staticmethod
    def _parse_statement_tables(html: str) -> list[ParsedStatement]:
        """Encuentra tablas de estados financieros y extrae (cuenta, valor actual).

        Heurística: una tabla de estado tiene >= 8 filas con una celda textual
        (descripción de la cuenta) seguida de celdas numéricas; el título del
        estado aparece en la propia tabla, en un heading previo o en un caption.
        """
        soup = BeautifulSoup(html, "lxml")
        text_all = normalize_text(soup.get_text(" ")[:20000])
        currency = "PEN" if ("soles" in text_all or "s/" in text_all) else (
            "USD" if "dolares" in text_all else None)
        consolidated = None
        if "consolidad" in text_all:
            consolidated = True
        elif "individual" in text_all:
            consolidated = False

        results = []
        for table in soup.find_all("table"):
            rows = []
            title_context = ""
            # título: caption, primera fila o heading anterior
            cap = table.find("caption")
            if cap:
                title_context += cap.get_text(" ")
            prev = table.find_previous(["h1", "h2", "h3", "h4", "span", "b", "td"])
            if prev:
                title_context += " " + prev.get_text(" ")
            title_context += " " + table.get_text(" ")[:300]
            kind = classify_statement(title_context)

            for tr in table.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                desc = cells[0].get_text(" ", strip=True)
                if not desc or len(desc) > 160:
                    continue
                value = None
                for c in cells[1:]:
                    v = _parse_number(c.get_text(strip=True))
                    if v is not None:
                        value = v
                        break
                if value is not None:
                    rows.append((desc, value))
            if kind and len(rows) >= 8:
                results.append(ParsedStatement(kind=kind, rows=rows,
                                               currency=currency, is_consolidated=consolidated))
        return results


def _parse_number(text: str) -> float | None:
    """Convierte '1,234' / '(1,234)' / '-1,234' a float. Vacíos y '0' válidos."""
    t = (text or "").strip()
    if not t or t in {"-", "--"}:
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace(",", "").replace("\xa0", "")
    if not re.fullmatch(r"-?\d+(\.\d+)?", t):
        return None
    v = float(t)
    return -v if neg else v


def parse_filing_statements(statements: list[ParsedStatement]) -> dict:
    """Mapea los estados parseados a campos internos normalizados."""
    fields: dict = {}
    for st in statements:
        fields.update(map_accounts(st.kind, st.rows))
    return fields
