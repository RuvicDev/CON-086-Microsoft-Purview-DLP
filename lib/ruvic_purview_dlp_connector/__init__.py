"""Prevención de pérdida de datos con Microsoft Purview: consultar alertas e incidentes DLP, consultar eventos DLP y las políticas que se activaron"""

from .client import PurviewDlpClient
from .config import ENV_PREFIX, PurviewDlpConfig
from .exceptions import (
    PurviewDlpAuthError,
    PurviewDlpConnectorError,
    PurviewDlpDataError,
    PurviewDlpNetworkError,
)
from .logging_utils import setup_logging

__all__ = [
    "ENV_PREFIX",
    "PurviewDlpAuthError",
    "PurviewDlpClient",
    "PurviewDlpConfig",
    "PurviewDlpConnectorError",
    "PurviewDlpDataError",
    "PurviewDlpNetworkError",
    "setup_logging",
]

__version__ = "1.0.0"
