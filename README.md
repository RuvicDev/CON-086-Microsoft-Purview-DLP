# Conector Microsoft Purview DLP (CON-086)

Conector Ruvic de solo lectura para Microsoft Purview DLP: alertas, incidentes, eventos DLP y políticas activadas.

## Instalación

```bash
pip install git+https://github.com/RuvicDev/CON-086-Microsoft-Purview-DLP.git#subdirectory=lib
```

Python 3.10+. Dependencias: `requests>=2.31,<3.0`.

## Permisos requeridos

Autenticación OAuth2 **client_credentials** con una aplicación de Microsoft Entra ID.
Permisos de **aplicación** con consentimiento de administrador:

| API | Permiso | Uso |
|-----|---------|-----|
| Microsoft Graph | `SecurityAlert.Read.All` | `list_alerts` (security/alerts_v2) |
| Microsoft Graph | `SecurityIncident.Read.All` | `list_incidents` (security/incidents) |
| Office 365 Management APIs | `ActivityFeed.ReadDlp` | `list_events`, `list_triggered_policies` (DLP.All) |

La **auditoría unificada** de Microsoft 365 debe estar activada (Purview → Auditoría).

## Variables de entorno (`RUVIC_PURVIEW_DLP_*`)

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `RUVIC_PURVIEW_DLP_TENANT_ID` | Sí | Tenant ID (Directory ID) |
| `RUVIC_PURVIEW_DLP_CLIENT_ID` | Sí | Client ID (Application ID) |
| `RUVIC_PURVIEW_DLP_CLIENT_SECRET` | Sí | Client Secret |
| `RUVIC_PURVIEW_DLP_CONNECT_TIMEOUT` | No (default `30`) | Timeout de conexión (segundos) |

Los campos opcionales vacíos usan su valor por defecto (la plataforma envía
`""` cuando un campo queda en blanco).

## Pruebas locales

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ./lib

export RUVIC_PURVIEW_DLP_TENANT_ID=...
export RUVIC_PURVIEW_DLP_CLIENT_ID=...
export RUVIC_PURVIEW_DLP_CLIENT_SECRET=...

python test_connection.py
python validate_local.py
```

`validate_local.py` consulta alertas, incidentes, eventos y políticas activadas. Si es la primera vez, los eventos pueden salir vacíos hasta 12 horas.

## Notas de integración

- Las alertas se filtran con `serviceSource eq 'dataLossPrevention'` (el valor documentado; `microsoftDataLossPrevention` da error).
- Graph no filtra incidentes por origen de alerta: el conector revisa los `scan` incidentes más recientes y conserva los que tienen alertas DLP.
- `list_events` recorre la Management Activity API en tramos de 24 h y sigue `NextPageUri`.
- Se usan dos tokens (Graph y manage.office.com), cacheados hasta 60 s antes de vencer.

## Limitaciones conocidas

- El catálogo de políticas DLP solo existe en PowerShell de Security & Compliance (`Get-DlpCompliancePolicy`); el conector reporta las políticas activadas.
- No resuelve alertas ni cambia políticas.
- La Management Activity API conserva 7 días de eventos y puede tardar hasta 12 horas en publicarlos.
