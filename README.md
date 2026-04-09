# Delivery Control

Aplicación **Streamlit** + **Supabase** (API REST / PostgREST) para asesoría y gestión de cuentas delivery en EE. UU. (Instacart, Uber Eats, Lyft, Spark Driver, Amazon Flex, Veho, DoorDash).

El acceso a datos usa **httpx** contra el endpoint REST de Supabase (sin el paquete `supabase` de Python), para evitar dependencias que en Windows suelen requerir compiladores C++.

## Modelo de negocio

- **Clientes**: quienes contratan o adquieren la cuenta.
- **Técnicos**: quienes ejecutan el trabajo; las cuentas se les **asignan**.
- **Cuentas**: vinculadas a una plataforma; **venta** o **alquiler**; **semáforo de estado** (`solicitud` → `asignada` → `en_proceso` → `requisitos_ok` → `entregada`, más `suspendida` / `cancelada`).
- **Alquileres**: monto semanal, próximo vencimiento, historial de pagos y alertas en el dashboard.

## Requisitos

- Python 3.10+
- Proyecto en [Supabase](https://supabase.com) (gratis para empezar)

## Configuración de Supabase

1. Crea un proyecto en Supabase.
2. En **SQL Editor**, pega y ejecuta el contenido de [`supabase/schema.sql`](supabase/schema.sql).
3. En **Settings → API**, copia la **URL** y la clave **anon** (o service role solo en entornos privados).

Las políticas RLS incluidas son **abiertas para desarrollo**. Antes de producción, sustitúyelas por políticas basadas en `auth.uid()` y roles.

## Configuración local

```powershell
cd "C:\Proyectos IA\delivery"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edita .env con SUPABASE_URL y SUPABASE_KEY
streamlit run Home.py
```

Abre el navegador en la URL que muestre Streamlit (por defecto `http://localhost:8501`).

## GitHub

```powershell
cd "C:\Proyectos IA\delivery"
git init
git add .
git commit -m "Initial Delivery Control app"
```

Crea un repositorio vacío en GitHub y sigue las instrucciones para `git remote add` y `git push`.

**No subas** el archivo `.env` ni secretos; ya están en `.gitignore`.

## Próximos pasos sugeridos

- Autenticación Supabase (login) y RLS por rol (gerencia / operaciones).
- Notificaciones (email o webhook) cuando un alquiler esté vencido.
- Export CSV / PDF de reportes gerenciales.
- Checklist de requisitos editable por plataforma (`requirements_checklist` JSON ya está en el esquema).

## Estructura

| Ruta | Descripción |
|------|-------------|
| `Home.py` | Entrada y comprobación de configuración |
| `pages/` | Dashboard, clientes, técnicos, cuentas, alquileres |
| `src/` | Configuración y cliente Supabase |
| `supabase/schema.sql` | Tablas, enums, triggers, RLS de desarrollo |
