"""Punto de entrada de conveniencia.

El proyecto se ejecuta con uvicorn (ver README). Este script arranca el servidor
de desarrollo directamente:  python hola.py
"""
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
