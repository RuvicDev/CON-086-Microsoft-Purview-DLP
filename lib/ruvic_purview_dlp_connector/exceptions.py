"""Excepciones propias del conector Microsoft Purview DLP.

Separan los tres tipos de fallo que el usuario debe distinguir:
autenticación, red/servidor y datos. Nunca exponemos excepciones
crípticas del cliente HTTP subyacente.
"""


class PurviewDlpConnectorError(Exception):
    """Error base del conector."""


class PurviewDlpAuthError(PurviewDlpConnectorError):
    """Credenciales inválidas o permisos insuficientes."""


class PurviewDlpNetworkError(PurviewDlpConnectorError):
    """No se pudo alcanzar el servicio (red, timeout o error del servidor)."""


class PurviewDlpDataError(PurviewDlpConnectorError):
    """La operación es válida pero los datos o parámetros no lo son."""
