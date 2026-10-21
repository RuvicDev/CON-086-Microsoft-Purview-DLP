"""Validación local del conector purview_dlp (solo lectura).

Uso:
    python validate_local.py

Requiere RUVIC_PURVIEW_DLP_TENANT_ID, RUVIC_PURVIEW_DLP_CLIENT_ID y
RUVIC_PURVIEW_DLP_CLIENT_SECRET exportadas.
"""

from ruvic_purview_dlp_connector import PurviewDlpClient, setup_logging

setup_logging("INFO")
client = PurviewDlpClient()

print("== 0. Ping ==")
client.ping()

print("== 1. Alertas DLP ==")
for a in client.list_alerts(limit=5):
    print(f"  {a['created']} {a['severity']} {a['title']}")

print("== 2. Incidentes con alertas DLP ==")
for i in client.list_incidents(limit=5):
    print(f"  {i['id']} {i['name']} ({i['dlp_alerts']} DLP)")

print("== 3. Eventos DLP últimas 24 h ==")
for e in client.list_events(hours=24, limit=5):
    print(f"  {e['time']} {e['workload']} {e['policies']}")

print("== 4. Políticas activadas última semana ==")
for p in client.list_triggered_policies(hours=168):
    print(f"  {p['policy']}: {p['matches']}")

print("\nTodo OK.")
