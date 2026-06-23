"""
tests/ssh_estado.py — Estado completo del sistema en el servidor
Uso: python tests/ssh_estado.py
"""
import paramiko

HOST = "192.168.1.6"
USER = "gwirzt"
PASS = "1211Gustavo"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    return out, err

print("=" * 70)
print("  ESTADO DEL SISTEMA — CryptoIA v2")
print("=" * 70)

# Servicios
print("\n[SERVICIOS]")
for svc in ["cryptobot", "cryptoapi", "ollama"]:
    out, _ = run(f"systemctl is-active {svc} 2>/dev/null")
    estado = "✅ ACTIVO" if out.strip() == "active" else f"❌ {out}"
    print(f"  {svc:15} {estado}")

# Últimos logs del bot (últimos 50 líneas)
print("\n[LOGS DEL BOT — últimas 40 líneas]")
out, _ = run("journalctl -u cryptobot -n 40 --no-pager 2>/dev/null")
print(out if out else "  (sin logs)")

# Últimos logs de la API
print("\n[LOGS DE LA API — últimas 10 líneas]")
out, _ = run("journalctl -u cryptoapi -n 10 --no-pager 2>/dev/null")
print(out if out else "  (sin logs)")

client.close()
print("\n" + "=" * 70)
