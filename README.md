# Delivery Control

Aplicación **Streamlit** + **Supabase** (API REST / PostgREST) para asesoría y gestión de cuentas delivery en EE. UU. (Instacart, Uber Eats, Lyft, Spark Driver, Amazon Flex, Veho, DoorDash).

El acceso a datos usa **httpx** contra el endpoint REST de Supabase (sin el paquete `supabase` de Python), para evitar dependencias que en Windows suelen requerir compiladores C++.

## Modelo de negocio

- **Clientes**: quienes contratan o adquieren la cuenta.
- **Técnicos**: quienes ejecutan el trabajo; las cuentas se les **asignan**.
- **Cuentas**: vinculadas a una plataforma; **venta** o **alquiler**; **semáforo de estado** (`solicitud` → `asignada` → `en_proceso` → `requisitos_ok` → `entregada`, más `suspendida` / `cancelada`).
- **Alquileres**: monto semanal, próximo vencimiento, historial de pagos y alertas en el dashboard.

## Autenticación y roles

- **Inicio de sesión** con correo y contraseña (Supabase Auth) en **Home**.
- **Olvidé mi contraseña**: envía correo de recuperación de Supabase (configurá plantillas y URL en **Authentication → URL configuration**).
- **Roles** (tabla `public.profiles`):
  - **superusuario**: todo; puede asignar cualquier rol.
  - **administración**: gestión operativa y usuarios, **no** puede crear ni editar **superusuario**.
  - **vendedor**: clientes, cuentas, alquileres, dashboard; no gestiona técnicos ni usuarios.
  - **técnico**: solo cuentas **asignadas** a su fila en `technicians` (campo `auth_user_id` = UUID del usuario en Auth).

**Primer super usuario:** creá el usuario en **Authentication → Users** (o por invitación). Al insertarse en `auth.users`, el trigger crea `profiles` con rol `tecnico`. Ejecutá en SQL:

```sql
update public.profiles set role = 'superusuario' where id = '<uuid del usuario>';
```

## Configuración de Supabase

1. **SQL Editor**: ejecutá [`supabase/schema.sql`](supabase/schema.sql).
2. **SQL Editor**: ejecutá [`supabase/migration_002_auth_profiles_rls.sql`](supabase/migration_002_auth_profiles_rls.sql) (sustituye las políticas abiertas de desarrollo por RLS con JWT).
3. **SQL Editor** (opcional): [`supabase/migration_003_finance_telecom.sql`](supabase/migration_003_finance_telecom.sql) — cuentas por pagar/cobrar, gastos operativos, inventario telecom (datos, números, proxies, líneas) + RLS + filas de ejemplo. Si la ejecutás de nuevo, los `INSERT` duplicarán datos: comentá o borrá la sección de ejemplo.
4. **SQL Editor**: [`supabase/migration_004_signup_role.sql`](supabase/migration_004_signup_role.sql) — al registrarse, el rol **vendedor** o **técnico** elegido en la app se guarda en `profiles` (metadata `signup_role`). Sin esta migración, todos los registros quedan como técnico.
5. **SQL Editor**: [`supabase/migration_005_datos_terceros.sql`](supabase/migration_005_datos_terceros.sql) — **Datos terceros** (licencias): tablas `third_party_identities` y `account_identity_links`, bucket Storage **license-photos** y políticas. La pantalla **Inventario telecom** fue reemplazada por **Datos terceros** en la app.
6. **Authentication → Providers**: habilitá **Email** (correo/contraseña).
7. **Authentication → URL configuration**:
   - **Site URL**: en producción, ponelá la URL pública de Streamlit (`https://TU-APP.streamlit.app`), no `localhost`, si los usuarios confirman correo desde el celular u otro equipo.
   - **Redirect URLs**: añadí esa misma URL (y `http://localhost:8501` si probás en local). Aplica a **recuperación de contraseña** y a **confirmar registro por correo**.
8. **Settings → API**: copiá la **URL** y la clave **anon** (la app usa el JWT del usuario en cada petición; la anon key va en cabecera `apikey`).

## Configuración local

```powershell
cd "C:\Proyectos IA\delivery"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edita .env con SUPABASE_URL y SUPABASE_KEY (anon)
streamlit run Home.py
```

Abre el navegador en la URL que muestre Streamlit (por defecto `http://localhost:8501`).

## Streamlit Cloud (Secrets)

1. En el deploy, **Main file path** debe ser **`Home.py`**. La app usa **`st.navigation`** (Streamlit **≥ 1.36**): primero solo ves **login/registro**; el menú lateral de la app aparece después de autenticarte. Las pantallas viven en **`views/`** (ya no se usa la carpeta `pages/` automática).
2. **App settings → Secrets**, pegá por ejemplo:

```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "eyJ..."  # clave anon de Supabase

# URL pública de la app (enlaces de correo: confirmar cuenta + recuperar contraseña):
AUTH_REDIRECT_URL = "https://TU-APP.streamlit.app"
# (Si ya tenías la otra clave, también sirve:)
# PASSWORD_RESET_REDIRECT_URL = "https://TU-APP.streamlit.app"
```

3. **`AUTH_REDIRECT_URL`** (o **`PASSWORD_RESET_REDIRECT_URL`**) es la base que Supabase usa en los enlaces del correo. Tiene que ser exactamente la URL que abre el usuario (con `https://` en Streamlit Cloud).
4. En **Supabase → Authentication → URL configuration** tenés que **permitir** esa URL en **Redirect URLs** (por ejemplo `https://TU-APP.streamlit.app` y/o `https://TU-APP.streamlit.app/**`). Si no está permitida, el enlace del correo muestra error o no redirige a tu app.
5. **Streamlit no lee el token del fragmento de la URL**: después de confirmar el correo, la cuenta queda activa; el usuario debe **iniciar sesión** manualmente en la pestaña “Iniciar sesión”.

## GitHub

```powershell
cd "C:\Proyectos IA\delivery"
git remote add origin https://github.com/TU_ORG/TU_REPO.git
git push -u origin main
```

**No subas** el archivo `.env` ni secretos; ya están en `.gitignore`.

**Retomar después de un corte:** actualizá y leé [`CONTINUA_DELIVERY.md`](CONTINUA_DELIVERY.md) antes de seguir; en Cursor podés pedir *“leé CONTINUA_DELIVERY”*.

## Estructura

| Ruta | Descripción |
|------|-------------|
| `Home.py` | Entrada: login exclusivo si no hay sesión; luego `st.navigation` |
| `views/login_screen.py` | Formularios de acceso (sesión, registro, recuperar contraseña) |
| `views/*.py` | Dashboard, clientes, finanzas, datos terceros (licencias), admin (solo con sesión) |
| `src/` | Config, cliente REST, auth HTTP, roles |
| `supabase/schema.sql` | Tablas iniciales |
| `supabase/migration_002_auth_profiles_rls.sql` | Perfiles, Auth trigger, RLS por rol |
| `supabase/migration_003_finance_telecom.sql` | Finanzas + telecom, RLS, inserts de ejemplo |
| `supabase/migration_004_signup_role.sql` | Rol al registrarse (vendedor/técnico) vía metadata |
| `supabase/migration_005_datos_terceros.sql` | Licencias / datos terceros + fotos (Storage) + vínculo a cuentas |

## Próximos pasos sugeridos

- Notificaciones cuando un alquiler esté vencido.
- Export CSV / PDF de reportes.
- UI para asignar `auth_user_id` al técnico sin usar SQL.
