"""Libera el puerto 8000 y reinicia la API"""
import paramiko, time

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

def sudo(cmd, timeout=30):
    return run(f"echo '{PASS}' | sudo -S {cmd}", timeout=timeout)

# Ver qué usa el puerto 8000
out, _ = run("ss -tlnp 2>/dev/null | grep 8000 || echo 'libre'")
print(f"Puerto 8000: {out}")

# Matar proceso en puerto 8000
out, _ = run("fuser 8000/tcp 2>/dev/null || echo 'ninguno'")
print(f"PID en 8000: {out}")
if out and out != "ninguno":
    sudo(f"fuser -k 8000/tcp 2>/dev/null")
    time.sleep(2)
    print("  Proceso matado")

# Detener servicios viejos que puedan usar el puerto
sudo("systemctl stop cryptoapi 2>/dev/null")
sudo("systemctl stop cryptobot_api 2>/dev/null")  # nombre viejo si existe

# Verificar si hay algún servicio viejo de API
out, _ = run("systemctl list-units --type=service --state=active 2>/dev/null | grep -i crypto")
print(f"Servicios crypto activos: {out}")

time.sleep(2)

# Reiniciar la API nueva
sudo("systemctl restart cryptoapi")
time.sleep(4)

out, _ = run("systemctl is-active cryptoapi 2>/dev/null")
print(f"cryptoapi: {out}")

if out.strip() == "active":
    print("✅ API activa en http://192.168.1.6:8000")
else:
    log, _ = run("journalctl -u cryptoapi -n 15 --no-pager 2>/dev/null")
    print(f"Logs:\n{log}")

client.close()
