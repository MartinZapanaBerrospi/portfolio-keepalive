# portfolio-keepalive

Mantiene despiertas las apps de mi portafolio alojadas en planes gratuitos, para que
quien visite un proyecto no se encuentre con la pantalla de "app dormida".

| Plataforma | Cuándo se pausa | Cómo se evita |
|---|---|---|
| Streamlit Community Cloud | ~12 h sin visitas | Se abre la app con un navegador real (Playwright) y, si está dormida, se pulsa *"Yes, get this app back up!"*. Un `curl` no basta: la visita cuenta solo cuando se abre la sesión websocket. |
| Supabase Free | 7 días con poca "actividad de usuario en la base de datos" | Conexión Postgres directa que **escribe** una fila de latido en `keepalive.ping` (esquema propio, no expuesto por la API REST; se crea solo). Respaldo si no hay DSN: lectura REST de una tabla real con datos. |

El workflow [`keepalive.yml`](.github/workflows/keepalive.yml) corre cada 6 horas en
GitHub Actions y deja el resultado en [`STATUS.md`](STATUS.md). Si una app no responde, el
workflow falla y GitHub envía un correo.

## Agregar o quitar apps

Edita [`targets.json`](targets.json):

- `streamlit`: nombre y URL pública.
- `supabase`: por proyecto, `dsn_env` (secret con la cadena de conexión, **método preferido**)
  y, opcional como respaldo, `url_env` + `key_env` + `table` (una **tabla real con datos**, nunca
  una vista que devuelva una constante).

Las credenciales van como **GitHub Secrets**. Para copiarlas desde los `.env` locales:

```powershell
.\setup-secrets.ps1
```

Un objetivo sin secret configurado se omite sin romper el workflow.

### Procedimiento obligatorio para cada proyecto nuevo en un plan gratuito que se pausa

Al desplegar un proyecto en Supabase, Streamlit Community Cloud, Neon, Render u otro
servicio gratuito que se duerma por inactividad, regístralo aquí **el mismo día**:

1. **Supabase**: en el panel, *Connect* → *Session pooler* (puerto 5432, IPv4) y copia la
   cadena `postgresql://postgres.<ref>:<password>@aws-X-<región>.pooler.supabase.com:5432/postgres`.
   Guárdala en el `.env` local del proyecto (gitignored) y añade la lectura en
   [`setup-secrets.ps1`](setup-secrets.ps1) como `<PROYECTO>_DATABASE_URL`.
   No uses la conexión directa `db.<ref>.supabase.co`: es solo IPv6 y los runners de GitHub no la alcanzan.
2. **Streamlit**: solo la URL pública `https://<app>.streamlit.app`.
3. **Neon / otro Postgres**: igual que Supabase (`dsn_env`); **Render**: añadir su URL como
   app web (pendiente de implementar un tipo `http` si llega a usarse).
4. Añade el objetivo a [`targets.json`](targets.json) y el secret al bloque `env:` de
   [`keepalive.yml`](.github/workflows/keepalive.yml).
5. Ejecuta `.\setup-secrets.ps1`, luego `gh workflow run keepalive.yml` y confirma que el
   nuevo objetivo sale `[OK]` con `gh run view --log`.

### Qué cuenta como actividad (lección de 2026-11)

`entrenador-admision` recibió el aviso de pausa aunque el workflow consultaba cada 6 h su
vista `keepalive` por REST y salía `[OK]`: esa vista era `select 1` y no tocaba ninguna
tabla, así que Supabase no la contó como actividad de usuario. Por eso ahora se escribe
una fila real por Postgres.

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
- Si un proyecto de Supabase ya está pausado, hay que restaurarlo a mano: panel de
  Supabase → organización → proyecto → **Resume project** (hasta 90 días después de la
  pausa). Este workflow solo evita que vuelva a pausarse.
- Si llega el correo de aviso, entrar al proyecto en el panel también cuenta como actividad.
- 2026-11-22: `riskpredictor-xai` (proyecto RiskPredictor-RPA) se pausó a propósito para dejar
  lugar a `tiza` (límite de 2 proyectos gratuitos activos) y salió de `targets.json`. Para volver a
  usarlo hay que pausar otro proyecto, reanudarlo en el panel y registrarlo aquí de nuevo.

## Límites de los planes gratuitos implicados

| Servicio | Límites relevantes del plan gratuito |
|---|---|
| Supabase Free | 2 proyectos activos por cuenta (los pausados no cuentan); 500 MB de base de datos por proyecto; 5 GB de egress; 1 GB de Storage; 50 000 MAU; pausa tras 7 días de baja actividad; restaurable hasta 90 días. |
| Streamlit Community Cloud | Apps públicas desde GitHub; ~1 GB de RAM por app; duerme tras ~12 h sin visitas. |
| GitHub Actions (repo público) | Minutos gratis e ilimitados en runners estándar; el cron puede retrasarse u omitirse en horas de carga; se desactiva tras 60 días sin actividad en el repo. |
