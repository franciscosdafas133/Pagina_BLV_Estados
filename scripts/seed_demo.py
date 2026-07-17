"""Siembra la BD con datos DEMO sintéticos para probar la interfaz sin depender
de la red de la SMV. NO son datos reales: las empresas llevan el prefijo 'DEMO'.

Uso:  python -m scripts.seed_demo
Para datos reales usa el scraper:  python -m app.cli ingest --years 2024 2025 --limit 10
"""
import random

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Company, FinancialStatement, Sector
from app.services.ingestion import recalc_company
from app.smv.account_mapping import normalize_text

DEMO = [
    ("Minera Andina", "Minería", False, "MINAND"),
    ("Cementos del Sur", "Industriales", False, "CEMSUR"),
    ("Agroexport Perú", "Agroindustria", False, "AGROPE"),
    ("Energía del Pacífico", "Energía", False, "ENEPAC"),
    ("Retail Lima", "Comercio", False, "RETLIM"),
    ("Consumo Nacional", "Consumo", False, "CONNAC"),
    ("Pesquera del Norte", "Pesca", False, "PESNOR"),
    ("Constructora Central", "Construcción e ingeniería", False, "CONCEN"),
    ("Banco Demo", "Bancos", True, "BANDEM"),
    ("Seguros Demo", "Seguros", True, "SEGDEM"),
]


def _statement(scale, quality):
    """quality en [0,1] modula márgenes, flujo y deuda."""
    rev = 1000 * scale
    op = rev * (0.08 + 0.18 * quality)
    ni = op * (0.55 + 0.25 * quality)
    ocf = ni * (0.7 + 0.8 * quality)
    debt = rev * (0.9 - 0.5 * quality)
    return dict(
        revenue=rev, cost_of_sales=-rev * 0.6, gross_profit=rev * 0.4,
        operating_income=op, ebit=op, financial_expenses=-debt * 0.06,
        income_before_tax=op * 0.9, income_tax=op * 0.9 * 0.295,
        net_income=ni, net_income_attributable=ni,
        depreciation_and_amortization=rev * 0.05,
        cash_and_equivalents=rev * 0.15, current_assets=rev * 0.6,
        total_assets=rev * 2.5, accounts_receivable=rev * 0.2,
        inventory=rev * 0.15, current_liabilities=rev * 0.4,
        total_liabilities=rev * 1.1, short_term_debt=debt * 0.3,
        long_term_debt=debt * 0.7, total_debt=debt,
        total_equity=rev * 1.4, equity_attributable=rev * 1.4,
        operating_cash_flow=ocf, capex=rev * 0.08, dividends_paid=ni * 0.3,
        investing_cash_flow=-rev * 0.09, financing_cash_flow=-rev * 0.03,
        interest_paid=-debt * 0.06,
    )


def main():
    init_db()
    db = SessionLocal()
    random.seed(42)
    sectors = {}
    for name, sector, is_fin, ticker in DEMO:
        s = db.scalar(select(Sector).where(Sector.name == sector))
        if not s:
            s = Sector(name=sector, is_financial=is_fin)
            db.add(s)
            db.flush()
        sectors[sector] = s

    for name, sector, is_fin, ticker in DEMO:
        legal = f"DEMO {name} S.A.A."
        c = db.scalar(select(Company).where(Company.smv_id == f"DEMO-{ticker}"))
        if not c:
            c = Company(smv_id=f"DEMO-{ticker}", legal_name=legal,
                        normalized_name=normalize_text(legal), ticker=ticker,
                        sector_id=sectors[sector].id,
                        source_url="https://www.smv.gob.pe/")
            db.add(c)
            db.flush()
        scale = random.uniform(0.8, 4.0)
        quality = random.uniform(0.15, 0.95)
        for year in (2023, 2024, 2025):
            for sem in (1, 2):
                q = quality * random.uniform(0.9, 1.1)
                fields = _statement(scale * (1 + 0.05 * (year - 2023)), q)
                stmt = db.scalar(select(FinancialStatement).where(
                    FinancialStatement.company_id == c.id, FinancialStatement.year == year,
                    FinancialStatement.semester == sem, FinancialStatement.period_type == "semester"))
                if not stmt:
                    stmt = FinancialStatement(company_id=c.id, year=year, semester=sem,
                                              period_type="semester", is_consolidated=True,
                                              currency="PEN", source_url=c.source_url,
                                              is_derived=False, flow_basis="discrete")
                    db.add(stmt)
                for k, v in fields.items():
                    setattr(stmt, k, v)
    db.flush()
    total = 0
    for c in db.scalars(select(Company)).all():
        total += recalc_company(db, c)
    db.commit()
    print(f"Sembradas {len(DEMO)} empresas DEMO, KPIs calculados: {total}")
    db.close()


if __name__ == "__main__":
    main()
