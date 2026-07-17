# Guía de despliegue en internet (Render.com)

Esta app scrapea la SMV **en tiempo real** con caché: al arrancar sincroniza el
catálogo de ~200 empresas (buscables al instante) y, al abrir una empresa sin
datos, descarga sus estados de la SMV en vivo (~30-40s la primera vez) y los
guarda para las siguientes visitas.

El código ya está commiteado en git. Solo faltan 3 pasos, todos en tu navegador.

---

## Paso 1 — Subir el código a GitHub

1. Crea una cuenta en https://github.com (si no tienes) e inicia sesión.
2. Crea un repositorio nuevo: botón **+** arriba a la derecha → **New repository**.
   - Nombre: `analisis-fundamental-smv` (o el que quieras).
   - Déjalo **público** o privado, da igual.
   - **No** marques "Add a README" (ya tienes uno).
   - Clic en **Create repository**.
3. GitHub te mostrará una URL como `https://github.com/TU_USUARIO/analisis-fundamental-smv.git`.
   Cópiala y ejecuta en la terminal, dentro de la carpeta del proyecto:

   ```bash
   git remote add origin https://github.com/TU_USUARIO/analisis-fundamental-smv.git
   git branch -M main
   git push -u origin main
   ```

   Te pedirá tu usuario y una contraseña: la "contraseña" es un **token**. Si no
   tienes, créalo en https://github.com/settings/tokens → *Generate new token
   (classic)* → marca el permiso **repo** → genéralo y pégalo como contraseña.

---

## Paso 2 — Desplegar en Render

1. Crea una cuenta en https://render.com (puedes entrar con tu cuenta de GitHub).
2. En el panel: **New +** → **Blueprint**.
3. Conecta tu cuenta de GitHub y selecciona el repositorio que subiste.
4. Render detectará el archivo `render.yaml` automáticamente y mostrará el
   servicio `analisis-fundamental-smv`. Clic en **Apply**.
5. Espera 3-5 minutos mientras construye e inicia. Cuando termine, Render te dará
   una URL pública tipo **https://analisis-fundamental-smv.onrender.com**.

Esa es la URL que le pasas a tu profesor.

> **Nota del plan gratuito:** tras ~15 min sin visitas, Render "duerme" el
> servicio; la siguiente visita tarda ~30s extra en despertar. Para una demo,
> abre la URL un minuto antes de mostrarla.

---

## Paso 3 — Probar

1. Abre tu URL de Render.
2. En el buscador escribe una empresa (ej. "alicorp", "gloria", "backus").
3. Entra a su ficha: la primera vez verás "Obteniendo datos de la SMV…" mientras
   scrapea en vivo (~30s); después queda cacheada.
4. El botón **↻ Actualizar desde SMV** en la ficha vuelve a scrapear en vivo
   cuando quieras — útil para demostrarle a tu profesor que es en tiempo real.

---

## Alternativas

- **Railway** (https://railway.app) o **Fly.io** — mismo repo, usan el `Procfile`.
- **Túnel temporal** para una demo desde tu PC sin hosting: instala
  `cloudflared` y corre `cloudflared tunnel --url http://localhost:8000` con el
  servidor local encendido; te da una URL pública mientras tu PC esté prendida.

---

## Variables de entorno (ya configuradas en render.yaml)

| Variable | Valor | Para qué |
|----------|-------|----------|
| `LIVE_SCRAPE` | `1` | Activa el scrape en vivo + sincronización del catálogo |
| `SMV_DB_PATH` | `/var/data/smv_analisis.db` | Caché en disco persistente |
| `PYTHON_VERSION` | `3.11.9` | Runtime |

Si pusieras `LIVE_SCRAPE=0`, la app serviría solo lo que haya en la BD sin
scrapear (modo offline).
