"""Pantalla exclusiva de acceso: login, registro y recuperación (sin menú de la app)."""

from pathlib import Path

import streamlit as st

from src.auth_api import AuthError, request_password_recovery, sign_in_with_password, sign_up
from src.config import get_auth_redirect_url, supabase_configured
from src.rbac import fetch_profile_for_user

_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo_driver_inn.png"


def _hide_app_chrome():
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stSidebarNav"] { display: none !important; }
        button[kind="header"] { display: none !important; }
        div[data-testid="stToolbar"] { display: none !important; }
        div[data-testid="stDecoration"] { display: none !important; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        .block-container {
            padding-top: clamp(1.5rem, 4vh, 3rem) !important;
            padding-bottom: clamp(2rem, 5vh, 4rem) !important;
            padding-left: clamp(1rem, 4vw, 2.5rem) !important;
            padding-right: clamp(1rem, 4vw, 2.5rem) !important;
            max-width: min(960px, 96vw) !important;
        }
        div[data-testid="stTabs"] button { border-radius: 8px 8px 0 0 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_auth_screen():
    _hide_app_chrome()

    c1, c2, c3 = st.columns([0.12, 0.76, 0.12])
    with c2:
        if _LOGO_PATH.is_file():
            st.image(str(_LOGO_PATH), use_container_width=True)
        else:
            st.markdown("### Driver Inn")
        st.markdown(
            '<p style="color:#5c6368;font-size:1rem;margin-top:0.2rem;">'
            "Gestión de cuentas delivery · Iniciá sesión o registrate"
            "</p>",
            unsafe_allow_html=True,
        )

        if not supabase_configured():
            st.error(
                "Faltan **SUPABASE_URL** y **SUPABASE_KEY** en **Secrets** (Streamlit Cloud) o en `.env` (local)."
            )

        tab_in, tab_reg, tab_rec = st.tabs(["Iniciar sesión", "Registrarme", "Olvidé mi contraseña"])

        with tab_in:
            st.subheader("Iniciar sesión")
            if not supabase_configured():
                st.caption("Guardá los Secrets y esperá ~1 minuto; luego recargá la app.")
            with st.form("login_form"):
                email = st.text_input("Correo", key="login_email")
                password = st.text_input("Contraseña", type="password", key="login_pw")
                go = st.form_submit_button("Entrar", type="primary", use_container_width=True)
            if go:
                if not supabase_configured():
                    st.error("Configurá Supabase antes de entrar.")
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
                                    "No hay perfil para este usuario. Un administrador debe revisar la tabla **profiles** en Supabase."
                                )
                            else:
                                st.session_state.access_token = token
                                st.session_state.refresh_token = data.get("refresh_token")
                                st.session_state.user_id = uid
                                st.session_state.user_email = user.get("email") or email.strip()
                                st.session_state.user_role = prof.get("role")
                                st.cache_data.clear()
                                st.rerun()
                    except AuthError as e:
                        st.error(str(e))

        with tab_reg:
            st.subheader("Crear cuenta")
            _redir = get_auth_redirect_url()
            st.caption(
                "Completá los datos. Si te piden confirmar el correo, revisá tu bandeja (y spam); "
                "después entrá con **Iniciar sesión**."
            )
            if supabase_configured() and not _redir:
                st.warning(
                    "Falta la URL pública de la app en **Secrets** (`AUTH_REDIRECT_URL`). "
                    "Sin eso, el enlace del correo puede fallar."
                )
            elif supabase_configured() and _redir:
                with st.expander("¿Problemas con el enlace del correo?", expanded=False):
                    st.markdown(
                        f"URL configurada para volver a la app: `{_redir}`. "
                        "Tiene que estar también en Supabase → **Authentication** → **URL configuration** → **Redirect URLs**. "
                        "Si confirmás el mail desde el celular, no puede quedar solo `localhost` en el panel de Supabase."
                    )
            if not supabase_configured():
                st.warning("Configurá Secrets primero.")
            with st.form("signup_form"):
                su_name = st.text_input("Nombre visible")
                su_email = st.text_input("Correo", key="su_email")
                su_pw = st.text_input("Contraseña (mín. 6 caracteres)", type="password", key="su_pw")
                su_pw2 = st.text_input("Repetir contraseña", type="password", key="su_pw2")
                su_go = st.form_submit_button("Registrarme", type="primary", use_container_width=True)
            if su_go:
                if not supabase_configured():
                    st.error("Configurá Supabase.")
                elif not su_email.strip() or not su_pw:
                    st.error("Completá correo y contraseña.")
                elif su_pw != su_pw2:
                    st.error("Las contraseñas no coinciden.")
                elif len(su_pw) < 6:
                    st.error("La contraseña debe tener al menos 6 caracteres.")
                else:
                    try:
                        sign_up(
                            su_email.strip(),
                            su_pw,
                            full_name=su_name.strip() or None,
                            redirect_to=_redir,
                        )
                        st.success(
                            "Cuenta creada. Si hay confirmación por correo, abrí el enlace y luego **iniciá sesión** "
                            "con el mismo correo y contraseña (Streamlit no inicia sesión solo desde el enlace). "
                            "Revisá también la carpeta de spam."
                        )
                    except AuthError as e:
                        st.error(str(e))

        with tab_rec:
            st.subheader("Recuperar contraseña")
            st.markdown(
                "Te enviamos un enlace al correo. Revisá spam. La URL de retorno debe estar en **Supabase → Authentication → URL configuration**."
            )
            with st.form("recover_form"):
                remail = st.text_input("Correo de la cuenta", key="recover_email")
                send = st.form_submit_button("Enviar enlace", use_container_width=True)
            if send:
                if not supabase_configured():
                    st.error("Configurá Supabase primero.")
                elif not remail.strip():
                    st.error("Ingresá tu correo.")
                else:
                    try:
                        request_password_recovery(remail, redirect_to=get_auth_redirect_url())
                        st.success("Si el correo existe, recibirás instrucciones en breve.")
                    except AuthError as e:
                        st.error(str(e))

        st.divider()
        st.caption("Acceso restringido · roles: super usuario · administración · vendedor · técnico")
