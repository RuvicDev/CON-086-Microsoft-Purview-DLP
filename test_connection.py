"""Prueba de conexión estándar del conector purview_dlp.

Firma estándar Ruvic: def test_connection() -> tuple[bool, str]
- Lee la configuración EXCLUSIVAMENTE de las env vars RUVIC_PURVIEW_DLP_*.
- Nunca lanza excepciones; retorna (ok, mensaje).

Ejecutable también como script para pruebas locales:
    python test_connection.py
"""

from __future__ import annotations


def test_connection() -> tuple[bool, str]:
    """Obtiene un token de Microsoft Graph y consulta una alerta DLP con las env vars RUVIC_PURVIEW_DLP_*."""
    try:
        from ruvic_purview_dlp_connector import (
            PurviewDlpAuthError,
            PurviewDlpClient,
            PurviewDlpDataError,
            PurviewDlpNetworkError,
        )
    except ImportError:
        return (
            False,
            (
                "La librería ruvic-purview-dlp-connector no está instalada. "
                "Instala con: pip install git+https://github.com/RuvicDev/"
                "CON-086-Microsoft-Purview-DLP.git#subdirectory=lib"
            ),
        )

    try:
        client = PurviewDlpClient()  # valida que existan las env vars
    except ValueError as exc:
        return False, str(exc)

    try:
        client.ping()
    except PurviewDlpAuthError as exc:
        return False, f"Autenticación fallida: {exc}"
    except PurviewDlpNetworkError as exc:
        return False, f"Error de red: {exc}"
    except PurviewDlpDataError as exc:
        return False, f"Error de datos: {exc}"
    except Exception as exc:  # noqa: BLE001 - red de seguridad: jamás propagar
        return False, f"Error inesperado: {exc}"

    return True, "Conexión exitosa a Microsoft Purview (Graph y Management Activity API)"


if __name__ == "__main__":
    ok, message = test_connection()
    print(f"{'OK' if ok else 'FALLO'}: {message}")
    raise SystemExit(0 if ok else 1)
