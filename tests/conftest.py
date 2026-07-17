"""Fixtures de integración: BD SQLite temporal sembrada con datos sintéticos.

Se sustituye el engine/SessionLocal del módulo de BD (sin recargar módulos,
para no redefinir las tablas del MetaData) y se sobreescribe la dependencia
get_db de FastAPI.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as database
from app import models
from app.database import get_db, Base
from app.main import app


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    # Reapuntar el engine global (para servicios que usan SessionLocal directo)
    prev_engine, prev_session = database.engine, database.SessionLocal
    database.engine = engine
    database.SessionLocal = TestingSession
    Base.metadata.create_all(bind=engine)

    _seed(TestingSession)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        database.engine, database.SessionLocal = prev_engine, prev_session
        engine.dispose()
        try:
            os.remove(path)
        except OSError:
            pass


def _seed(SessionLocal):
    """Siembra 6 empresas industriales y 2 financieras con KPIs precalculados."""
    from sqlalchemy import select

    from app.services.ingestion import recalc_company
    from app.smv.account_mapping import normalize_text

    db = SessionLocal()
    ind = models.Sector(name="Minería", is_financial=False)
    fin = models.Sector(name="Bancos", is_financial=True)
    db.add_all([ind, fin])
    db.flush()

    def base(scale, ni=127, ocf=250):
        return dict(revenue=1000 * scale, cost_of_sales=-600 * scale, gross_profit=400 * scale,
                    operating_income=200 * scale, ebit=200 * scale, financial_expenses=-20 * scale,
                    income_before_tax=180 * scale, income_tax=53 * scale, net_income=ni * scale,
                    net_income_attributable=ni * scale, depreciation_and_amortization=50 * scale,
                    cash_and_equivalents=300 * scale, current_assets=800 * scale,
                    total_assets=3000 * scale, accounts_receivable=200 * scale,
                    inventory=150 * scale, current_liabilities=500 * scale,
                    total_liabilities=1000 * scale, short_term_debt=100 * scale,
                    long_term_debt=400 * scale, total_debt=500 * scale,
                    total_equity=2000 * scale, equity_attributable=2000 * scale,
                    operating_cash_flow=ocf * scale, capex=80 * scale, dividends_paid=40 * scale)

    companies = []
    for i in range(6):
        c = models.Company(smv_id=f"IND{i}", legal_name=f"Minera Ejemplo {i} S.A.A.",
                           normalized_name=normalize_text(f"Minera Ejemplo {i} S.A.A."),
                           ticker=f"MIN{i}", sector_id=ind.id,
                           source_url="https://smv.gob.pe/ejemplo")
        # variar márgenes reales cambiando la utilidad, no solo la escala
        companies.append((c, base(1 + i * 0.1, ni=80 + i * 25, ocf=180 + i * 30)))
    for i in range(2):
        c = models.Company(smv_id=f"FIN{i}", legal_name=f"Banco Ejemplo {i} S.A.",
                           normalized_name=normalize_text(f"Banco Ejemplo {i} S.A."),
                           ticker=f"BAN{i}", sector_id=fin.id)
        companies.append((c, base(2 + i, ni=300 + i * 50)))

    db.add_all([c for c, _ in companies])
    db.flush()

    for c, fields in companies:
        for year in (2024, 2025):
            stmt = models.FinancialStatement(
                company_id=c.id, year=year, semester=2, period_type="semester",
                is_consolidated=True, currency="PEN", source_url=c.source_url,
                is_derived=False, flow_basis="discrete")
            fyear = fields if year == 2025 else {k: v * 0.9 for k, v in fields.items()}
            for k, v in fyear.items():
                setattr(stmt, k, v)
            db.add(stmt)
    db.flush()

    for c in db.scalars(select(models.Company)).all():
        recalc_company(db, c)
    db.commit()
    db.close()
