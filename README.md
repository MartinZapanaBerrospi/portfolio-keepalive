# portfolio-keepalive

Mantiene despiertas las apps de mi portafolio alojadas en planes gratuitos, para que
quien visite un proyecto no se encuentre con la pantalla de "app dormida".

| Plataforma | Cuándo se pausa | Cómo se evita |
|---|---|---|
| Streamlit Community Cloud | ~12 h sin visitas | Se abre la app con un navegador real (Playwright) y, si está dormida, se pulsa *"Yes, get this app back up!"*. Un `curl` no basta: la visita cuenta solo cuando se abre la sesión websocket. |
| Supabase Free | 7 días sin actividad | Se ejecuta una consulta real a la base de datos (REST con la anon key o Postgres directo). |

El workflow [`keepalive.yml`](.github/workflows/keepalive.yml) corre cada 6 horas en
GitHub Actions y deja el resultado en [`STATUS.md`](STATUS.md). Si una app no responde, el
workflow falla y GitHub envía un correo.

## Agregar o quitar apps

Edita [`targets.json`](targets.json):

- `streamlit`: nombre y URL pública.
- `supabase_rest`: nombre del secret con la URL del proyecto, el de la anon key y una tabla para consultar.
- `supabase_postgres`: nombre del secret con la cadena de conexión.

Las credenciales van como **GitHub Secrets**. Para copiarlas desde los `.env` locales:

```powershell
.\setup-secrets.ps1
```

Un objetivo sin secret configurado se omite sin romper el workflow.

## Probar en local

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python keepalive.py
```

## Notas

- GitHub desactiva los cron de repos sin actividad durante 60 días. El commit diario de
  `STATUS.md` mantiene el repo activo.
- Si un proyecto de Supabase ya está pausado, hay que restaurarlo a mano desde el panel;
  este workflow solo evita que vuelva a pausarse.
