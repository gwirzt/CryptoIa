"""Test rápido de los endpoints de ciclos y exportación"""
import requests

BASE = "http://192.168.1.6:8000"

# Test 1: Ciclos de hoy
print("[1] GET /ciclos?fecha=2026-09-08")
r = requests.get(f"{BASE}/ciclos?fecha=2026-09-08", timeout=10)
d = r.json()
print(f"    Status: {r.status_code} | OK: {d.get('ok')} | Total: {d.get('total')} ciclos")

# Test 2: Ciclos del 8 de agosto (fecha del screenshot)
print("\n[2] GET /ciclos?fecha=2026-08-08")
r = requests.get(f"{BASE}/ciclos?fecha=2026-08-08", timeout=10)
d = r.json()
print(f"    Status: {r.status_code} | OK: {d.get('ok')} | Total: {d.get('total')} ciclos")
if d.get('total', 0) > 0:
    print(f"    Primer ciclo: {d['ciclos'][0]['timestamp']} - {d['ciclos'][0]['accion']}")

# Test 3: Exportar CSV rango amplio
print("\n[3] GET /ciclos/exportar?fecha_desde=2026-08-01&fecha_hasta=2026-09-08")
r = requests.get(f"{BASE}/ciclos/exportar?fecha_desde=2026-08-01&fecha_hasta=2026-09-08", timeout=15)
print(f"    Status: {r.status_code} | Content-Type: {r.headers.get('content-type')}")
if r.status_code == 200:
    lines = r.text.strip().split("\n")
    print(f"    Filas CSV: {len(lines)} (incluye encabezado)")
    if len(lines) > 1:
        print(f"    Encabezado: {lines[0][:100]}")
        print(f"    Primera fila: {lines[1][:100]}")

print("\n✅ Tests completados")
