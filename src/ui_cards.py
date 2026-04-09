"""UI helpers: tarjetas con encabezado coloreado."""

from __future__ import annotations

import streamlit as st


def ensure_card_styles() -> None:
    if st.session_state.get("_ui_card_styles_loaded"):
        return
    st.session_state["_ui_card_styles_loaded"] = True
    st.markdown(
        """
<style>
.tcard-title{
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
  color: #fff;
  font-weight: 700;
  font-size: 14px;
  letter-spacing: .2px;
}
.tcard-sub{
  margin: 6px 2px 0 2px;
  color: rgba(0,0,0,.65);
  font-size: 12px;
}
</style>
""",
        unsafe_allow_html=True,
    )


def card_header(title: str, color: str, subtitle: str | None = None) -> None:
    """Encabezado visual (barra de color) dentro de una tarjeta (st.container(border=True))."""
    ensure_card_styles()
    st.markdown(f"<div class='tcard-title' style='background:{color};'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)

