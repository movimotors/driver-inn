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
4. **Authentication → Providers**: habilitá **Email** (correo/contraseña).
5. **Authentication → URL configuration**: añadí la URL de tu app Streamlit (local y/o `*.streamlit.app`) para recuperación de contraseña.
6. **Settings → API**: copiá la **URL** y la clave **anon** (la app usa el JWT del usuario en cada petición; la anon key va en cabecera `apikey`).

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

En **App settings → Secrets**, por ejemplo:

```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "eyJ..."  # anon

# Opcional: URL a la que Supabase redirige tras el enlace del correo de recuperación
# PASSWORD_RESET_REDIRECT_URL = "https://tu-app.streamlit.app"
```

## GitHub

```powershell
cd "C:\Proyectos IA\delivery"
git remote add origin https://github.com/TU_ORG/TU_REPO.git
git push -u origin main
```

**No subas** el archivo `.env` ni secretos; ya están en `.gitignore`.

## Estructura

| Ruta | Descripción |
|------|-------------|
| `Home.py` | Login, recuperación de contraseña, bienvenida |
| `pages/` | Dashboard, clientes, técnicos, cuentas, alquileres, admin usuarios |
| `src/` | Config, cliente REST, auth HTTP, roles |
| `supabase/schema.sql` | Tablas iniciales |
| `supabase/migration_002_auth_profiles_rls.sql` | Perfiles, Auth trigger, RLS por rol |
| `supabase/migration_003_finance_telecom.sql` | Finanzas + telecom, RLS, inserts de ejemplo |

## Próximos pasos sugeridos

- Notificaciones cuando un alquiler esté vencido.
- Export CSV / PDF de reportes.
- UI para asignar `auth_user_id` al técnico sin usar SQL.
