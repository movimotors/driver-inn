import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.auth_api import AuthError, request_password_recovery, sign_in_with_password
from src.config import get_supabase_config, supabase_configured
from src.rbac import ROLE_LABELS, fetch_profile_for_user, init_session_state, is_logged_in, logout

st.set_page_config(
    page_title="Delivery Control",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()

st.title("Delivery Control")
st.caption("Asesoría y gestión de cuentas delivery (USA)")

if not supabase_configured():
    st.error(
        "**Faltan credenciales de Supabase.** Sin ellas no podés iniciar sesión. "
        "En Streamlit Cloud: **App settings → Secrets** y agregá `SUPABASE_URL` y `SUPABASE_KEY` (clave **anon**). "
        "Debajo igualmente podés ver el formulario de acceso; al intentar entrar verás el error hasta que guardes los Secrets."
    )

with st.sidebar:
    if is_logged_in():
        st.write(f"**{st.session_state.user_email or 'Usuario'}**")
        st.write(ROLE_LABELS.get(st.session_state.user_role, st.session_state.user_role))
        if st.button("Cerrar sesión", use_container_width=True):
            logout()
            st.rerun()
    else:
        st.info("Iniciá sesión para usar la app.")

if is_logged_in():
    st.success("Sesión activa. Usá el menú lateral para **Dashboard**, **Clientes**, **Cuentas**, etc.")
    st.markdown(
        """
- **Dashboard** — resumen y alertas de alquiler  
- **Clientes** — altas (vendedor / administración)  
- **Técnicos** — solo administración  
- **Cuentas** — semáforo y asignaciones  
- **Alquileres** — pagos y vencimientos  
- **Por pagar / Por cobrar / Gastos** — finanzas operativas  
- **Inventario telecom** — números web USA, datos, proxies (lectura según rol)  
- **Admin usuarios** — roles (admin / super usuario)  
"""
    )
    st.stop()

tab_login, tab_recover = st.tabs(["Iniciar sesión", "Olvidé mi contraseña"])

with tab_login:
    st.subheader("Iniciar sesión")
    if not supabase_configured():
        st.caption("Completá **Secrets** con `SUPABASE_URL` y `SUPABASE_KEY` y recargá la app (~1 min después de guardar).")
    with st.form("login_form"):
        email = st.text_input("Correo", key="login_email")
        password = st.text_input("Contraseña", type="password", key="login_pw")
        go = st.form_submit_button("Entrar", type="primary")
    if go:
        if not supabase_configured():
            st.error("Configurá primero SUPABASE_URL y SUPABASE_KEY en Secrets (o .env en local).")
        elif not email.strip() or not password:
            st.error("Completá correo y contraseña.")
        else:
            try:
                data = sign_in_with_password(email, password)
                token = data.get("access_token")
                user = data.get("user") or {}
                uid = user.get("id")
                if not token or not uid:
                    st.error("Respuesta de autenticación incompleta.")
                else:
                    prof = fetch_profile_for_user(token, uid)
                    if not prof:
                        st.error(
                            "No hay perfil para este usuario. Pedile a un administrador que verifique **profiles** en Supabase."
                        )
                    else:
                        st.session_state.access_token = token
                        st.session_state.refresh_token = data.get("refresh_token")
                        st.session_state.user_id = uid
                        st.session_state.user_email = user.get("email") or email.strip()
                        st.session_state.user_role = prof.get("role")
                        st.cache_data.clear()
                        st.success("Bienvenido.")
                        st.rerun()
            except AuthError as e:
                st.error(str(e))

with tab_recover:
    st.subheader("Recuperar contraseña")
    st.markdown(
        "Te enviamos un correo con un enlace para **restablecer la contraseña**. "
        "Revisá también spam. La URL de redirección debe estar permitida en Supabase (**Authentication → URL configuration**)."
    )
    url_base, _ = get_supabase_config()
    with st.form("recover_form"):
        remail = st.text_input("Correo de la cuenta", key="recover_email")
        send = st.form_submit_button("Enviar enlace")
    if send:
        if not supabase_configured():
            st.error("Configurá SUPABASE_URL y SUPABASE_KEY en Secrets antes de pedir el enlace.")
        elif not remail.strip():
            st.error("Ingresá tu correo.")
        else:
            try:
                redirect_to = None
                try:
                    if hasattr(st, "secrets") and "PASSWORD_RESET_REDIRECT_URL" in st.secrets:
                        redirect_to = str(st.secrets["PASSWORD_RESET_REDIRECT_URL"]).strip() or None
                except Exception:
                    redirect_to = None
                request_password_recovery(remail, redirect_to=redirect_to)
                st.success("Si el correo existe en el sistema, recibirás instrucciones en breve.")
            except AuthError as e:
                st.error(str(e))

st.divider()
st.caption("Roles: super usuario · administración · vendedor · técnico")
