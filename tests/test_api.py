"""Pruebas de integración de la API sobre una BD sembrada."""


def test_search_companies_insensible_tildes(client):
    r = client.get("/api/companies", params={"search": "minera ejemplo"})
    assert r.status_code == 200
    assert r.json()["total"] >= 6


def test_search_por_ticker(client):
    r = client.get("/api/companies", params={"search": "MIN0"})
    names = [c["name"] for c in r.json()["companies"]]
    assert any("Minera Ejemplo 0" in n for n in names)


def test_filtro_profitable(client):
    r = client.get("/api/companies", params={"year": 2025, "semester": 2, "profitable": True})
    assert r.status_code == 200
    assert all(c.get("hasData") for c in r.json()["companies"])


def test_company_kpis_formato_consistente(client):
    cid = client.get("/api/companies").json()["companies"][0]["id"]
    r = client.get(f"/api/companies/{cid}/kpis", params={"year": 2025, "semester": 2})
    assert r.status_code == 200
    data = r.json()
    assert "company" in data and "period" in data and "kpis" in data
    assert "dataQuality" in data and "score" in data
    roic = data["kpis"]["roic"]
    assert "value" in roic and "displayValue" in roic and "isAvailable" in roic
    # No debe haber NaN/Infinity serializados
    for k in data["kpis"].values():
        assert k["value"] is None or isinstance(k["value"], (int, float))


def test_comparacion_sectorial_presente(client):
    # tomar una empresa del sector con >=5 miembros (Minería)
    companies = client.get("/api/companies", params={"sector": "Minería"}).json()["companies"]
    cid = companies[0]["id"]
    data = client.get(f"/api/companies/{cid}/kpis", params={"year": 2025, "semester": 2}).json()
    roic = data["kpis"]["roic"]
    if roic["isAvailable"]:
        assert "sectorMedian" in roic
        assert "percentile" in roic
        assert roic["sectorCompanies"] >= 5


def test_history_series(client):
    cid = client.get("/api/companies").json()["companies"][0]["id"]
    r = client.get(f"/api/companies/{cid}/history", params={"metric": "revenue"})
    assert r.status_code == 200
    assert len(r.json()["series"]) >= 2


def test_ranking_profitability_no_financieras_por_roic(client):
    r = client.get("/api/rankings/profitability", params={"year": 2025, "semester": 2})
    assert r.status_code == 200
    data = r.json()
    assert data["metric"] == "roic"
    assert len(data["ranking"]) >= 5
    # solo no financieras y ordenado descendente
    for row in data["ranking"]:
        assert row["isFinancial"] is False
    vals = [row["value"] for row in data["ranking"]]
    assert vals == sorted(vals, reverse=True)


def test_ranking_financieras_separado(client):
    r = client.get("/api/rankings/profitability",
                   params={"year": 2025, "semester": 2, "financial": True, "metric": "roe"})
    # Solo hay 2 financieras (< mínimo 5) -> ranking vacío por diseño
    assert r.status_code == 200
    assert r.json()["ranking"] == []


def test_ranking_growth(client):
    r = client.get("/api/rankings/growth", params={"year": 2025, "semester": 2})
    assert r.status_code == 200
    assert len(r.json()["ranking"]) >= 5


def test_sectors_endpoint(client):
    r = client.get("/api/sectors")
    names = [s["name"] for s in r.json()["sectors"]]
    assert "Minería" in names and "Bancos" in names


def test_periods_endpoint(client):
    r = client.get("/api/periods")
    assert any(p["year"] == 2025 for p in r.json()["periods"])


def test_summary_endpoint(client):
    r = client.get("/api/summary", params={"year": 2025, "semester": 2})
    s = r.json()
    assert s["totalCompanies"] == 8
    assert s["profitablePct"] is not None


def test_company_no_existente_404(client):
    r = client.get("/api/companies/99999/kpis")
    assert r.status_code == 404
