"""Análisis completo de operaciones y logs del bot"""
import paramiko

HOST = "192.168.1.6"
USER = "gwirzt"
PASS = "1211Gustavo"
PROYECTO = "/home/gwirzt/CryptoIa"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)

def run(cmd, timeout=60):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    return out, err

print("=" * 70)
print("  ANÁLISIS DE OPERACIONES — CryptoIA v2")
print("=" * 70)

# Todas las operaciones en la DB
print("\n[OPERACIONES EN DB]")
out, _ = run("""PGPASSWORD=Crypto2026 psql -h localhost -U Crypto -d CryptoTrade -c "
SELECT tipo, precio, cantidad, capital, pnl_pct, pnl_usdt, razon_ia, timestamp
FROM operaciones_v2
ORDER BY timestamp DESC
LIMIT 30
" 2>/dev/null""")
print(out if out else "  (sin operaciones)")

# Posición actual
print("\n[POSICIÓN ACTUAL]")
out, _ = run("""PGPASSWORD=Crypto2026 psql -h localhost -U Crypto -d CryptoTrade -c "
SELECT simbolo, precio_compra, cantidad, capital_usado, ciclos, timestamp_compra
FROM posicion_v2
" 2>/dev/null""")
print(out if out else "  (sin posición abierta)")

# Logs completos del bot (últimas 100 líneas)
print("\n[LOGS COMPLETOS DEL BOT — últimas 80 líneas]")
out, _ = run("journalctl -u cryptobot -n 80 --no-pager 2>/dev/null")
print(out if out else "  (sin logs)")

client.close()
print("\n" + "=" * 70)
