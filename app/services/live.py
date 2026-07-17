"""Scrape bajo demanda + caché.

Estrategia de la app desplegada:
- Al arrancar se sincroniza el catálogo de empresas de la SMV (buscable al
  instante), sin descargar estados financieros.
- Cuando se abre una empresa sin datos cacheados, se scrapean sus estados de la
  SMV en vivo, se calculan sus KPIs y se guardan. La siguiente visita es
  instantánea.

Un lock por empresa evita que dos peticiones simultáneas scrapeen lo mismo.
El catálogo se sincroniza como máximo una vez por intervalo (CATALOG_TTL).
"""
import threading
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CalculatedKPI, Company
from app.services.ingestion import ingest_company_year, recalc_company, sync_companies
from app.smv.scraper import SMVScraper

# Años que se scrapean bajo demanda (los más recientes con datos)
LIVE_YEARS = [2023, 2024, 2025]
CATALOG_TTL = 6 * 3600  # resincronizar catálogo como máximo cada 6 horas

_company_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()
_catalog_state = {"last_sync": 0.0, "lock": threading.Lock()}


def _lock_for(company_id: int) -> threading.Lock:
    with _locks_guard:
        return _company_locks.setdefault(company_id, threading.Lock())


def company_has_data(db: Session, company_id: int) -> bool:
    return db.scalar(
        select(func.count(CalculatedKPI.id)).where(CalculatedKPI.company_id == company_id)
    ) > 0


def ensure_catalog(db: Session, force: bool = False) -> int:
    """Sincroniza el catálogo de empresas si está vencido. Devuelve nº de empresas."""
    now = time.time()
    total = db.scalar(select(func.count(Company.id))) or 0
    if not force and total > 0 and (now - _catalog_state["last_sync"]) < CATALOG_TTL:
        return total
    if not _catalog_state["lock"].acquire(blocking=False):
        return total  # otra petición ya está sincronizando
    try:
        scraper = SMVScraper()
        try:
            sync_companies(db, scraper)
        finally:
            scraper.close()
        _catalog_state["last_sync"] = time.time()
    except Exception:  # noqa: BLE001 — si la SMV falla, se usa lo que haya
        pass
    finally:
        _catalog_state["lock"].release()
    return db.scalar(select(func.count(Company.id))) or 0


def ensure_company_data(db: Session, company: Company,
                        years: list[int] | None = None, force: bool = False) -> dict:
    """Garantiza que la empresa tenga datos: si no, la scrapea de la SMV en vivo.

    Devuelve {'status': 'cached'|'scraped'|'empty', 'periods': int}.
    """
    years = years or LIVE_YEARS
    if not force and company_has_data(db, company.id):
        return {"status": "cached", "periods": 0}

    lock = _lock_for(company.id)
    with lock:
        # Reverificar dentro del lock (otra petición pudo haber terminado)
        if not force and company_has_data(db, company.id):
            return {"status": "cached", "periods": 0}
        scraper = SMVScraper()
        periods = 0
        try:
            for year in years:
                try:
                    periods += ingest_company_year(db, scraper, company, year)
                except Exception:  # noqa: BLE001 — un año que falla no aborta el resto
                    continue
            recalc_company(db, company)
        finally:
            scraper.close()
        if periods == 0 and not company_has_data(db, company.id):
            return {"status": "empty", "periods": 0}
        return {"status": "scraped", "periods": periods}
