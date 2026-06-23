"""Ver el error exacto de /operaciones"""
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

# Ver logs completos de la API con errores
out, _ = run("journalctl -u cryptoapi -n 50 --no-pager 2>/dev/null | grep -A5 -i 'error\\|exception\\|traceback'")
print(out if out else "(sin errores en logs)")

# Ver tablas existentes en la DB
out, _ = run("PGPASSWORD=Crypto2026 psql -h localhost -U Crypto -d CryptoTrade -c '\\dt' 2>/dev/null")
print(f"\nTablas en DB:\n{out}")

# Ver estructura de la tabla operaciones si existe
out, _ = run("PGPASSWORD=Crypto2026 psql -h localhost -U Crypto -d CryptoTrade -c '\\d operaciones' 2>/dev/null")
print(f"\nEstructura operaciones:\n{out}")

client.close()
