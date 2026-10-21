"""Cliente de Microsoft Purview DLP (Microsoft Graph + Office 365 Management Activity API).

Capacidades:
- list_alerts():             alertas DLP (Graph security/alerts_v2, serviceSource=dataLossPrevention).
- list_incidents():          incidentes de Microsoft Defender XDR que contienen alertas DLP.
- list_events():             eventos DLP de la auditoría (Management Activity API, DLP.All).
- list_triggered_policies(): políticas DLP que se activaron en un periodo, con su conteo.

Limitación: el catálogo completo de políticas DLP no está expuesto por
REST (solo por PowerShell de Security & Compliance, Get-DlpCompliancePolicy);
list_triggered_policies() reporta las políticas que aparecen en los eventos.

Las credenciales SIEMPRE provienen de variables de entorno RUVIC_PURVIEW_DLP_*
(ver config.PurviewDlpConfig.from_env). Prohibido hardcodearlas.
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .config import PurviewDlpConfig
from .exceptions import PurviewDlpAuthError, PurviewDlpDataError, PurviewDlpNetworkError
from .logging_utils import get_logger

_GRAPH = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_MANAGE = "https://manage.office.com/api/v1.0"
_MANAGE_SCOPE = "https://manage.office.com/.default"
_DLP_SOURCE = "dataLossPrevention"
_SEVERITIES = {"informational", "low", "medium", "high"}
_STATUSES = {"new", "inProgress", "resolved"}


def _limit(value: Any, maximum: int = 500) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise PurviewDlpDataError(f"limit debe ser un entero entre 1 y {maximum}.")
    return value


def _hours(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 168:
        raise PurviewDlpDataError("hours debe ser un entero entre 1 y 168 (la API guarda 7 días).")
    return value


def _choice(value: str | None, allowed: set[str], field: str) -> str | None:
    if value is None:
        return None
    lookup = {a.lower(): a for a in allowed}
    found = lookup.get(str(value).strip().lower())
    if not found:
        raise PurviewDlpDataError(f"{field} {value!r} inválido. Valores permitidos: {sorted(allowed)}")
    return found


class PurviewDlpClient:
    """Cliente de Microsoft Purview DLP.

    Args:
        config: configuración. Si se omite, se lee de RUVIC_PURVIEW_DLP_*.

    Ejemplo:
        >>> client = PurviewDlpClient()
        >>> client.list_alerts(severity="high", limit=10)
        [{'id': 'dl...', 'title': 'DLP policy match for document ...', 'severity': 'high', ...}]
    """

    def __init__(self, config: PurviewDlpConfig | None = None) -> None:
        self.config = config or PurviewDlpConfig.from_env()
        self._logger = get_logger()
        self._session = requests.Session()
        self._tokens: dict[str, tuple[str, float]] = {}

    # ------------------------------------------------------------------ #
    # Conexión
    # ------------------------------------------------------------------ #

    def _token(self, scope: str) -> str:
        cached = self._tokens.get(scope)
        if cached and time.time() < cached[1] - 60:
            return cached[0]
        url = f"https://login.microsoftonline.com/{self.config.tenant_id}/oauth2/v2.0/token"
        try:
            resp = self._session.post(url, data={
                "grant_type": "client_credentials",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "scope": scope,
            }, timeout=self.config.connect_timeout)
        except requests.exceptions.RequestException as exc:
            raise PurviewDlpNetworkError(f"No se pudo alcanzar Microsoft Entra ID: {exc}") from exc
        if resp.status_code != 200:
            try:
                desc = resp.json().get("error_description", "")
            except ValueError:
                desc = resp.text
            raise PurviewDlpAuthError(
                "No se pudo obtener el token de Microsoft Entra ID: revisa Tenant ID, Client ID y "
                f"Client Secret. Detalle: {desc.splitlines()[0][:200] if desc else resp.status_code}"
            )
        body = resp.json()
        self._tokens[scope] = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
        return body["access_token"]

    def _request(self, method: str, url: str, scope: str, **kwargs: Any) -> Any:
        headers = {"Authorization": f"Bearer {self._token(scope)}", "Accept": "application/json"}
        try:
            resp = self._session.request(method, url, headers=headers,
                                         timeout=self.config.connect_timeout, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise PurviewDlpNetworkError(f"No se pudo alcanzar Microsoft ({url.split('/')[2]}): {exc}") from exc
        api = "Office 365 Management APIs (ActivityFeed.ReadDlp)" if scope == _MANAGE_SCOPE else \
            "Microsoft Graph (SecurityAlert.Read.All / SecurityIncident.Read.All)"
        if resp.status_code in (401, 403):
            detail = ""
            try:
                detail = str(resp.json().get("error", {}).get("message", ""))[:200]
            except ValueError:
                pass
            raise PurviewDlpAuthError(
                f"Permiso insuficiente: la aplicación necesita permisos de {api} con consentimiento "
                f"de administrador. {detail}".strip()
            )
        if resp.status_code == 404:
            raise PurviewDlpDataError("El recurso solicitado no existe.")
        if resp.status_code == 429:
            raise PurviewDlpNetworkError("Límite de peticiones de Microsoft alcanzado; reintenta en un minuto.")
        if resp.status_code >= 500:
            raise PurviewDlpNetworkError(f"Microsoft respondió {resp.status_code}; reintenta en unos segundos.")
        if resp.status_code >= 400:
            raise PurviewDlpDataError(f"Microsoft rechazó la petición ({resp.status_code}): {resp.text[:300]}")
        return resp.json() if resp.content else None

    def ping(self) -> bool:
        """Verifica credenciales y permisos de Graph consultando una alerta DLP.

        Raises:
            PurviewDlpAuthError / PurviewDlpNetworkError / PurviewDlpDataError.
        """
        self._request("GET", f"{_GRAPH}/security/alerts_v2", _GRAPH_SCOPE,
                      params={"$top": 1, "$filter": f"serviceSource eq '{_DLP_SOURCE}'"})
        self._logger.info("Ping exitoso a Microsoft Graph (alertas DLP)")
        return True

    # ------------------------------------------------------------------ #
    # Capacidad 1: alertas DLP
    # ------------------------------------------------------------------ #

    def list_alerts(self, severity: str | None = None, status: str | None = None,
                    limit: int = 50) -> list[dict[str, Any]]:
        """Consulta alertas DLP, de la más reciente a la más antigua.

        Args:
            severity: "informational", "low", "medium" o "high" (opcional).
            status: "new", "inProgress" o "resolved" (opcional).
            limit: máximo de alertas (1-500).

        Returns:
            Lista de dicts: id, title, severity, status, created, incident_id,
            category, description.

        Ejemplo:
            >>> client.list_alerts(status="new")
            [{'id': 'dl...', 'title': 'DLP policy match ...', 'status': 'new', ...}]
        """
        limit = _limit(limit)
        filters = [f"serviceSource eq '{_DLP_SOURCE}'"]
        if severity:
            filters.append(f"severity eq '{_choice(severity, _SEVERITIES, 'severity')}'")
        if status:
            filters.append(f"status eq '{_choice(status, _STATUSES, 'status')}'")
        data = self._request("GET", f"{_GRAPH}/security/alerts_v2", _GRAPH_SCOPE, params={
            "$filter": " and ".join(filters), "$top": limit,
        }) or {}
        alerts = sorted(data.get("value", []), key=lambda a: a.get("createdDateTime") or "", reverse=True)
        self._logger.info("Alertas DLP: %d", len(alerts))
        return [{
            "id": a.get("id"),
            "title": a.get("title"),
            "severity": a.get("severity"),
            "status": a.get("status"),
            "created": a.get("createdDateTime"),
            "incident_id": a.get("incidentId"),
            "category": a.get("category"),
            "description": (a.get("description") or "")[:500],
        } for a in alerts]

    # ------------------------------------------------------------------ #
    # Capacidad 2: incidentes DLP
    # ------------------------------------------------------------------ #

    def list_incidents(self, limit: int = 25, scan: int = 100) -> list[dict[str, Any]]:
        """Consulta incidentes que contienen al menos una alerta DLP.

        Graph no permite filtrar incidentes por origen de alerta, así que
        el conector revisa los `scan` incidentes más recientes y conserva
        los que tienen alertas DLP.

        Args:
            limit: máximo de incidentes DLP a devolver (1-500).
            scan: incidentes recientes a revisar (1-500, default 100).

        Returns:
            Lista de dicts: id, name, severity, status, created, dlp_alerts,
            total_alerts, url.

        Ejemplo:
            >>> client.list_incidents(limit=5)
            [{'id': '1234', 'name': 'DLP incident on ...', 'dlp_alerts': 2, ...}]
        """
        limit, scan = _limit(limit), _limit(scan)
        data = self._request("GET", f"{_GRAPH}/security/incidents", _GRAPH_SCOPE, params={
            "$top": scan, "$expand": "alerts",
        }) or {}
        out = []
        incidents = sorted(data.get("value", []), key=lambda i: i.get("createdDateTime") or "", reverse=True)
        for inc in incidents:
            alerts = inc.get("alerts") or []
            dlp = [a for a in alerts if str(a.get("serviceSource", "")).lower() == _DLP_SOURCE.lower()]
            if not dlp:
                continue
            out.append({
                "id": inc.get("id"),
                "name": inc.get("displayName"),
                "severity": inc.get("severity"),
                "status": inc.get("status"),
                "created": inc.get("createdDateTime"),
                "dlp_alerts": len(dlp),
                "total_alerts": len(alerts),
                "url": inc.get("incidentWebUrl"),
            })
            if len(out) >= limit:
                break
        self._logger.info("Incidentes con alertas DLP: %d (revisados %d)", len(out), scan)
        return out

    # ------------------------------------------------------------------ #
    # Capacidad 3: eventos DLP (Management Activity API)
    # ------------------------------------------------------------------ #

    def _ensure_subscription(self) -> None:
        base = f"{_MANAGE}/{self.config.tenant_id}/activity/feed/subscriptions"
        subs = self._request("GET", f"{base}/list", _MANAGE_SCOPE) or []
        if any(s.get("contentType") == "DLP.All" and s.get("status") == "enabled" for s in subs):
            return
        self._request("POST", f"{base}/start", _MANAGE_SCOPE, params={"contentType": "DLP.All"})
        self._logger.info("Suscripción DLP.All iniciada (los eventos pueden tardar hasta 12 h en aparecer)")

    def list_events(self, hours: int = 24, limit: int = 100) -> list[dict[str, Any]]:
        """Consulta eventos DLP de la auditoría unificada de Microsoft 365.

        La primera vez inicia la suscripción DLP.All; desde ahí, los eventos
        nuevos tardan normalmente entre minutos y 12 horas en estar disponibles.

        Args:
            hours: ventana hacia atrás (1-168; la API conserva 7 días).
            limit: máximo de eventos (1-500).

        Returns:
            Lista de dicts: time, workload, operation, user, object, policies
            (nombres), severity, sensitive_info_types.

        Ejemplo:
            >>> client.list_events(hours=24, limit=20)
            [{'time': '2026-10-20T15:02:11', 'workload': 'Exchange', 'policies': ['Tarjetas de crédito'], ...}]
        """
        hours, limit = _hours(hours), _limit(limit)
        self._ensure_subscription()
        end = datetime.now(timezone.utc)
        out: list[dict[str, Any]] = []
        # La API acepta ventanas de máximo 24 h: se recorre en tramos.
        cursor = end - timedelta(hours=hours)
        while cursor < end and len(out) < limit:
            chunk_end = min(cursor + timedelta(hours=24), end)
            for item in self._list_content(cursor, chunk_end):
                for record in self._request("GET", item["contentUri"], _MANAGE_SCOPE) or []:
                    out.append(self._event(record))
                    if len(out) >= limit:
                        break
                if len(out) >= limit:
                    break
            cursor = chunk_end
        out.sort(key=lambda e: e.get("time") or "", reverse=True)
        self._logger.info("Eventos DLP: %d (últimas %dh)", len(out), hours)
        return out[:limit]

    def _list_content(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        url = f"{_MANAGE}/{self.config.tenant_id}/activity/feed/subscriptions/content"
        params: dict[str, Any] | None = {
            "contentType": "DLP.All",
            "startTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "endTime": end.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        items: list[dict[str, Any]] = []
        token = self._token(_MANAGE_SCOPE)
        while url:
            try:
                resp = self._session.get(url, params=params, timeout=self.config.connect_timeout,
                                         headers={"Authorization": f"Bearer {token}"})
            except requests.exceptions.RequestException as exc:
                raise PurviewDlpNetworkError(f"No se pudo alcanzar la Management Activity API: {exc}") from exc
            if resp.status_code in (401, 403):
                raise PurviewDlpAuthError(
                    "Permiso insuficiente: la aplicación necesita Office 365 Management APIs → "
                    "ActivityFeed.ReadDlp con consentimiento de administrador."
                )
            if resp.status_code >= 400:
                raise PurviewDlpDataError(f"Management Activity API respondió {resp.status_code}: {resp.text[:300]}")
            items.extend(resp.json() or [])
            url = resp.headers.get("NextPageUri") or ""
            params = None
        return items

    @staticmethod
    def _event(r: dict[str, Any]) -> dict[str, Any]:
        policies = r.get("PolicyDetails") or []
        sits: list[str] = []
        severities: list[str] = []
        for p in policies:
            for rule in p.get("Rules") or []:
                if rule.get("Severity"):
                    severities.append(rule["Severity"])
                for sd in (rule.get("ConditionsMatched") or {}).get("SensitiveInformation") or []:
                    if sd.get("SensitiveInformationTypeName"):
                        sits.append(sd["SensitiveInformationTypeName"])
        shared = r.get("SharePointMetaData") or {}
        exch = r.get("ExchangeMetaData") or {}
        return {
            "time": r.get("CreationTime"),
            "workload": r.get("Workload"),
            "operation": r.get("Operation"),
            "user": r.get("UserId"),
            "object": shared.get("FileName") or exch.get("Subject") or r.get("ObjectId"),
            "policies": sorted({p.get("PolicyName") for p in policies if p.get("PolicyName")}),
            "severity": severities[0] if severities else None,
            "sensitive_info_types": sorted(set(sits)),
        }

    # ------------------------------------------------------------------ #
    # Capacidad 4: políticas activadas
    # ------------------------------------------------------------------ #

    def list_triggered_policies(self, hours: int = 168, max_events: int = 500) -> list[dict[str, Any]]:
        """Resume qué políticas DLP se activaron en el periodo y cuántas veces.

        Args:
            hours: ventana hacia atrás (1-168).
            max_events: eventos a analizar como máximo (1-500).

        Returns:
            Lista de dicts: policy, matches, workloads, last_match; ordenada
            de la política más activada a la menos.

        Ejemplo:
            >>> client.list_triggered_policies(hours=72)
            [{'policy': 'Tarjetas de crédito', 'matches': 14, 'workloads': ['Exchange', 'OneDrive'], ...}]
        """
        events = self.list_events(hours=hours, limit=_limit(max_events))
        counts: Counter[str] = Counter()
        workloads: dict[str, set[str]] = {}
        last: dict[str, str] = {}
        for e in events:
            for p in e["policies"]:
                counts[p] += 1
                workloads.setdefault(p, set()).add(e.get("workload") or "")
                if (e.get("time") or "") > last.get(p, ""):
                    last[p] = e.get("time") or ""
        return [{
            "policy": p,
            "matches": n,
            "workloads": sorted(w for w in workloads[p] if w),
            "last_match": last.get(p),
        } for p, n in counts.most_common()]
