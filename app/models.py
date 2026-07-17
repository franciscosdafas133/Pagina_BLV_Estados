"""Modelos de datos.

Se mantienen separados los datos originales (financial_statements) de los
indicadores calculados (calculated_kpis): nunca se mezclan ni se duplican.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Campos financieros normalizados que puede contener un estado financiero.
# Un valor NULL significa "no reportado"; nunca se convierte en cero.
STATEMENT_FIELDS = [
    # Estado de resultados
    "revenue", "cost_of_sales", "gross_profit", "operating_income", "ebit",
    "financial_expenses", "income_before_tax", "income_tax", "net_income",
    "net_income_attributable", "depreciation_and_amortization",
    # Balance general
    "cash_and_equivalents", "current_assets", "total_assets",
    "accounts_receivable", "inventory", "current_liabilities",
    "total_liabilities", "short_term_debt", "long_term_debt", "total_debt",
    "total_equity", "equity_attributable",
    # Flujo de efectivo
    "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
    "capex", "dividends_paid", "interest_paid",
    # Datos accionarios
    "shares_outstanding", "weighted_average_shares", "diluted_shares",
    "market_price", "market_cap",
]


class Sector(Base):
    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    is_financial: Mapped[bool] = mapped_column(Boolean, default=False)

    companies: Mapped[list["Company"]] = relationship(back_populates="sector_rel")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    smv_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # id del combo de la SMV
    legal_name: Mapped[str] = mapped_column(String(250), index=True)
    commercial_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    normalized_name: Mapped[str] = mapped_column(String(250), index=True)  # sin tildes, minúsculas
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    ruc: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sector_rel: Mapped[Sector | None] = relationship(back_populates="companies")
    statements: Mapped[list["FinancialStatement"]] = relationship(back_populates="company")


class FinancialStatement(Base):
    """Un estado financiero normalizado para un periodo concreto.

    period_type:
      - 'quarter_ytd' : cifras acumuladas desde enero hasta fin del trimestre
                        (formato en que la SMV entrega resultados intermedios)
      - 'semester'    : flujo del semestre (derivado, S2 = acumulado Q4 - acumulado Q2)
      - 'annual'      : año completo
    flow_basis indica cómo llegaron las cifras de flujos ('ytd' o 'discrete').
    El balance general siempre es una foto al cierre del periodo.
    """
    __tablename__ = "financial_statements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..4 (filing de origen)
    semester: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # 1 o 2
    period_type: Mapped[str] = mapped_column(String(20), index=True)
    period_start: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO yyyy-mm-dd
    period_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    unit_multiplier: Mapped[int] = mapped_column(Integer, default=1000)  # SMV reporta en miles
    is_consolidated: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_derived: Mapped[bool] = mapped_column(Boolean, default=False)  # calculado a partir de otros filings
    flow_basis: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    filing_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company: Mapped[Company] = relationship(back_populates="statements")

    __table_args__ = (
        UniqueConstraint("company_id", "year", "quarter", "semester", "period_type",
                         "is_consolidated", name="uq_statement_period"),
        Index("ix_stmt_lookup", "company_id", "year", "period_type", "is_consolidated"),
    )


# Columnas numéricas (todas anulables: NULL = no reportado)
for _f in STATEMENT_FIELDS:
    setattr(FinancialStatement, _f, mapped_column(_f, Float, nullable=True))


class CalculatedKPI(Base):
    """KPIs precalculados para (empresa, año, semestre/anual)."""
    __tablename__ = "calculated_kpis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    semester: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # NULL = anual
    period_type: Mapped[str] = mapped_column(String(20), index=True)
    is_consolidated: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    kpi: Mapped[str] = mapped_column(String(50), index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_value: Mapped[float | None] = mapped_column(Float, nullable=True)  # mismo semestre año anterior
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)  # p.ej. EBITDA aproximado
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "year", "semester", "period_type",
                         "is_consolidated", "kpi", name="uq_kpi_period"),
        Index("ix_kpi_rankings", "kpi", "year", "semester", "period_type", "value"),
    )


class FinancialAlert(Base):
    __tablename__ = "financial_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    semester: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(10))  # alta | media | baja
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    kpi: Mapped[str | None] = mapped_column(String(50), nullable=True)
    observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[str | None] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "year", "semester", "code", name="uq_alert"),
    )


class IngestionLog(Base):
    __tablename__ = "ingestion_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scope: Mapped[str] = mapped_column(String(200))  # p.ej. "AENZA 2023-2025"
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|ok|error|partial
    statements_ingested: Mapped[int] = mapped_column(Integer, default=0)
    kpis_calculated: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
