"""CLI de administración.

Uso:
  python -m app.cli sync-companies            # solo catálogo de empresas
  python -m app.cli ingest --years 2023 2024 2025 --limit 10
  python -m app.cli ingest --smv-ids 30481 --years 2024 2025
  python -m app.cli recalc                    # recalcula KPIs y alertas
"""
import argparse

from app.database import SessionLocal, init_db


def main():
    parser = argparse.ArgumentParser(description="Administración del MVP SMV")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync-companies")

    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("--years", nargs="+", type=int, required=True)
    p_ing.add_argument("--smv-ids", nargs="*", default=None,
                       help="IDs SMV de empresas (vacío = todas)")
    p_ing.add_argument("--limit", type=int, default=None,
                       help="máx. empresas a procesar")

    sub.add_parser("recalc")

    args = parser.parse_args()
    init_db()
    db = SessionLocal()
    try:
        if args.cmd == "sync-companies":
            from app.services.ingestion import sync_companies
            from app.smv.scraper import SMVScraper
            scraper = SMVScraper()
            try:
                n = sync_companies(db, scraper)
            finally:
                scraper.close()
            print(f"Empresas nuevas: {n}")
        elif args.cmd == "ingest":
            from app.services.ingestion import run_ingestion
            log = run_ingestion(db, args.smv_ids or None, args.years, args.limit)
            print(f"Estado: {log.status} | periodos: {log.statements_ingested} "
                  f"| KPIs: {log.kpis_calculated}")
            if log.detail:
                print("Incidencias:\n" + log.detail)
        elif args.cmd == "recalc":
            from sqlalchemy import select

            from app.models import Company
            from app.services.ingestion import recalc_company
            total = 0
            for c in db.scalars(select(Company)).all():
                total += recalc_company(db, c)
            print(f"KPIs recalculados: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
