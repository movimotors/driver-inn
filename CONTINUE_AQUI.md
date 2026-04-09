# Retomar el trabajo (Driver Inn)

Usá este archivo cuando cortes la sesión (descanso, corte de luz, reinicio). **Antes de cerrar**, actualizá las secciones de abajo en 1 minuto. **Al volver**, abrí el proyecto en Cursor y pedí: *“Leé CONTINUE_AQUI.md y seguí”*.

## Estado rápido (editá esto al irte)

| Campo | Valor |
|--------|--------|
| **Fecha / hora** | |
| **En qué estábamos** | |
| **Próximo paso concreto** | |
| **Último commit** | `git log -1 --oneline` |

## Recordatorios del proyecto

- **Repo:** `movimotors/driver-inn` · entrada Streamlit: **`Home.py`**
- **Supabase:** si falta algo de auth/finanzas, revisá `README.md` y migraciones en `supabase/`
- **Migración rol registro:** ejecutar en SQL Editor si aún no: `migration_004_signup_role.sql`

## Al retomar (orden sugerido)

1. `git pull origin main`
2. Leer este archivo y el último mensaje de commit
3. Continuar el **Próximo paso** anotado arriba

## Si Cursor / el agente hizo cambios

La regla del proyecto pide **commit + push** al terminar cambios reales (ver `.cursor/rules/git-commit-push.mdc`).
