---
name: purview-dlp
description: >
  Usa la librería ruvic_purview_dlp_connector para consultar la prevención
  de pérdida de datos de Microsoft Purview - alertas DLP (list_alerts),
  incidentes con alertas DLP (list_incidents), eventos DLP de la auditoría
  de Microsoft 365 (list_events) y las políticas DLP que se activaron
  (list_triggered_policies). Úsala cuando el usuario pregunte por fugas de
  datos, coincidencias de políticas DLP, alertas o incidentes de Purview.
triggers:
- purview
- dlp
- fuga de datos
- data loss prevention
- politica dlp
- informacion sensible
- cumplimiento
---

# Conector Microsoft Purview DLP (ruvic_purview_dlp_connector)

Librería Python para Microsoft Purview DLP (Microsoft Graph y Office 365 Management Activity API). Está **preinstalada en el runtime** cuando el
conector está configurado (si no, instálala con
`pip install git+https://github.com/RuvicDev/CON-086-Microsoft-Purview-DLP.git#subdirectory=lib`).

## Regla crítica de credenciales

El código generado **NUNCA hardcodea credenciales**. Siempre se leen de
variables de entorno, disponibles cuando el conector `purview_dlp` está
configurado:

| Variable | Contenido |
|----------|-----------|
| `RUVIC_PURVIEW_DLP_TENANT_ID` | Tenant ID (Directory ID) |
| `RUVIC_PURVIEW_DLP_CLIENT_ID` | Client ID (Application ID) |
| `RUVIC_PURVIEW_DLP_CLIENT_SECRET` | Client Secret |
| `RUVIC_PURVIEW_DLP_CONNECT_TIMEOUT` | (opcional) Timeout de conexión (segundos), default 30 |

Si estas variables NO existen, el conector no está configurado: no
generes código que lo use; indica al usuario que lo configure en
**Settings → Conectores**. El código generado **NUNCA** usa nombres con
segmento de alias (`_DEFAULT_INSTANCIA_`, `_PRODUCCION_`, etc.) salvo que
aparezcan en una sección autogenerada `## Variables en tu entorno` al final
de este skill.

## Este conector es de solo lectura

Todas las operaciones son de lectura: no cambian alertas, incidentes ni
políticas. La única escritura indirecta es que `list_events` inicia una
vez la suscripción `DLP.All` de la Management Activity API si no existe
(no afecta a los usuarios). Los eventos pueden tardar hasta 12 horas en
aparecer después de ocurrir.

## Conexión (siempre igual)

```python
from ruvic_purview_dlp_connector import PurviewDlpClient

client = PurviewDlpClient()  # lee RUVIC_PURVIEW_DLP_* del entorno automáticamente
```

## Capacidad 1 — Consultar alertas DLP

```python
alertas = client.list_alerts(severity="high", status="new", limit=20)
for a in alertas:
    print(a["created"], a["severity"], a["title"])
```

Severidades: `informational`, `low`, `medium`, `high`. Estados: `new`, `inProgress`, `resolved`.

## Capacidad 2 — Consultar incidentes con alertas DLP

```python
incidentes = client.list_incidents(limit=10)
for i in incidentes:
    print(i["id"], i["name"], f"{i['dlp_alerts']} alertas DLP", i["url"])
```

## Capacidad 3 — Consultar eventos DLP

```python
eventos = client.list_events(hours=24, limit=50)
for e in eventos:
    print(e["time"], e["workload"], e["user"], e["object"], e["policies"], e["sensitive_info_types"])
```

`hours` admite hasta 168 (la API conserva 7 días).

## Capacidad 4 — Políticas que se activaron

```python
for p in client.list_triggered_policies(hours=168):
    print(p["policy"], p["matches"], p["workloads"], p["last_match"])
```

El catálogo completo de políticas no está disponible por REST; esto reporta las que tuvieron coincidencias.

## Manejo de errores

```python
from ruvic_purview_dlp_connector import (
    PurviewDlpAuthError, PurviewDlpDataError, PurviewDlpNetworkError,
)

try:
    client.list_alerts(status="new")
except PurviewDlpAuthError as e:
    print(f"Credenciales o permisos: {e}")
except PurviewDlpNetworkError as e:
    print(f"No se pudo alcanzar el servicio: {e}")
except PurviewDlpDataError as e:
    print(f"Error de datos: {e}")
```

Muestra el mensaje de la excepción tal cual al usuario: indica qué corregir.

## Buenas prácticas al generar código

1. Lee credenciales SOLO de las variables `RUVIC_PURVIEW_DLP_*` (el constructor de `PurviewDlpClient` ya lo hace).
2. Nunca imprimas `RUVIC_PURVIEW_DLP_CLIENT_SECRET` en logs ni en la salida.
3. Los eventos contienen nombres de usuarios y archivos: muéstralos solo a quien los pidió y no los copies a otros sistemas.
4. Si `list_events` devuelve vacío justo después de configurar, explica que la suscripción tarda hasta 12 horas.
5. No prometas el catálogo completo de políticas: el conector solo ve las que se activaron.
