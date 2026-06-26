"""
tests/ssh_restart_servicios.py — Reinicia los servicios del bot vía SSH
Usa sudo con contraseña por stdin para evitar el problema de terminal
"""
import paramiko
import time

HOST = "192.168.1.6"
USER = "gwirzt"
PASS = "1211Gustavo"
SUDO_PASS = "1211Gustavo"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

def run_sudo(cmd, timeout=20):
    """Ejecuta un comando con sudo pasando la contraseña por stdin."""
    stdin, stdout, stderr = client.exec_command(
        f"echo '{SUDO_PASS}' | sudo -S {cmd} 2>&1",
        timeout=timeout
    )
    out = stdout.read().decode("utf-8", errors="replace").strip()
    return out

def run(cmd, timeout=20):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    return out

print("=" * 60)
print("  REINICIO DE SERVICIOS — CryptoIA v3")
print("=" * 60)

for svc in ["cryptobot", "cryptoapi"]:
    print(f"\n  Reiniciando {svc}...")
    out = run_sudo(f"systemctl restart {svc}")
    # Filtrar línea de sudo password prompt
    lineas = [l for l in out.splitlines() if "password" not in l.lower() and l.strip()]
    print(f"  {chr(10).join(lineas) if lineas else 'OK'}")

print("\n  Esperando 5 segundos...")
time.sleep(5)

print("\n[ESTADO DE SERVICIOS]")
for svc in ["cryptobot", "cryptoapi"]:
    out = run(f"systemctl is-active {svc}")
    estado = "✅ ACTIVO" if out.strip() == "active" else f"❌ {out}"
    print(f"  {svc:15} {estado}")

print("\n[LOGS DEL BOT — últimas 20 líneas]")
out = run("journalctl -u cryptobot -n 20 --no-pager 2>/dev/null")
print(out if out else "  (sin logs)")

client.close()
print("\n" + "=" * 60)
