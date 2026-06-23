"""git pull + reinicio de servicios en el servidor"""
import paramiko, time

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

def sudo(cmd, timeout=30):
    return run(f"echo '{PASS}' | sudo -S {cmd}", timeout=timeout)

# Git pull
out, _ = run(f"cd {PROYECTO} && git pull origin master 2>&1")
print(f"Git pull:\n  {out[:300]}")

# Reiniciar servicios
for svc in ["cryptobot", "cryptoapi"]:
    sudo(f"systemctl restart {svc}")
    time.sleep(3)
    out, _ = run(f"systemctl is-active {svc} 2>/dev/null")
    estado = "✅ ACTIVO" if out.strip() == "active" else f"❌ {out}"
    print(f"  {svc}: {estado}")

# Verificar que /operaciones ya no da error
time.sleep(2)
out, _ = run("curl -s http://localhost:8000/operaciones?limite=5 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); print('OK' if d.get('ok') else d.get('error','?'))\"")
print(f"\n/operaciones: {out if out else 'sin respuesta'}")

client.close()
print("Listo.")
