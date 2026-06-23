"""
tests/ssh_deploy.py — Deploy completo del bot en el servidor
1. git pull en el servidor
2. Instala dependencias en el venv
3. Copia los servicios systemd
4. Activa e inicia los servicios
Uso: python tests/ssh_deploy.py
"""
import paramiko, time, sys

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

def sudo(cmd, timeout=60):
    return run(f"echo '{PASS}' | sudo -S {cmd}", timeout=timeout)

def ok(msg): print(f"  ✅ {msg}")
def err(msg): print(f"  ❌ {msg}")
def info(msg): print(f"  → {msg}")

print("=" * 60)
print("  DEPLOY CryptoIA v2")
print("=" * 60)

# ── 1. Git pull ────────────────────────────────────────────────────────────────
print("\n[1/5] Actualizando código (git pull)...")
# Detectar rama actual
rama_out, _ = run(f"cd {PROYECTO} && git rev-parse --abbrev-ref HEAD 2>/dev/null")
rama = rama_out.strip() or "master"
info(f"Rama: {rama}")
out, e = run(f"cd {PROYECTO} && git pull origin {rama} 2>&1")
print(f"  {out[:300]}")
if "fatal" in out.lower() or "error" in out.lower():
    if "Already up to date" not in out and "up to date" not in out.lower():
        err(f"Git pull falló: {out[:100]}")
        # Intentar fetch + reset
        run(f"cd {PROYECTO} && git fetch origin {rama} 2>&1")
        run(f"cd {PROYECTO} && git reset --hard origin/{rama} 2>&1")
ok("Código actualizado")

# ── 2. Crear/actualizar venv e instalar dependencias ──────────────────────────
print("\n[2/5] Instalando dependencias...")
out, e = run(f"test -d {PROYECTO}/venv && echo 'existe' || echo 'no existe'")
if "no existe" in out:
    info("Creando venv...")
    run(f"python3 -m venv {PROYECTO}/venv")

deps = "fastapi uvicorn[standard] ccxt pandas sqlalchemy psycopg2-binary requests python-dotenv rich"
out, e = run(f"{PROYECTO}/venv/bin/pip install {deps} --quiet 2>&1", timeout=180)
if "error" in out.lower() or "error" in e.lower():
    err(f"Error instalando deps: {e[:200]}")
else:
    ok("Dependencias instaladas")

# ── 3. Copiar .env si no existe ────────────────────────────────────────────────
print("\n[3/5] Verificando .env...")
out, e = run(f"test -f {PROYECTO}/.env && echo 'existe' || echo 'no existe'")
if "no existe" in out:
    info(".env no encontrado — copiando desde .env.example")
    run(f"cp {PROYECTO}/.env.example {PROYECTO}/.env")
    err("⚠️  Editá el .env en el servidor con tus credenciales reales")
else:
    ok(".env existe")

# ── 4. Instalar servicios systemd ─────────────────────────────────────────────
print("\n[4/5] Instalando servicios systemd...")

for servicio in ["cryptobot", "cryptoapi"]:
    src = f"{PROYECTO}/deploy/{servicio}.service"
    dst = f"/etc/systemd/system/{servicio}.service"
    out, e = run(f"test -f {src} && echo 'ok' || echo 'no'")
    if "ok" in out:
        sudo(f"cp {src} {dst}")
        ok(f"{servicio}.service copiado")
    else:
        err(f"{src} no encontrado")

sudo("systemctl daemon-reload")
ok("systemd recargado")

# ── 5. Habilitar e iniciar servicios ──────────────────────────────────────────
print("\n[5/5] Iniciando servicios...")

for servicio in ["cryptoapi", "cryptobot"]:
    sudo(f"systemctl enable {servicio}")
    sudo(f"systemctl restart {servicio}")
    time.sleep(3)
    out, _ = run(f"systemctl is-active {servicio} 2>/dev/null")
    if out.strip() == "active":
        ok(f"{servicio}: ACTIVO")
    else:
        err(f"{servicio}: {out}")
        # Ver logs del error
        log_out, _ = run(f"journalctl -u {servicio} -n 10 --no-pager 2>/dev/null")
        print(f"  Logs:\n{log_out[:500]}")

# ── Resumen ────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  RESUMEN")
print("=" * 60)
out, _ = run("systemctl is-active cryptobot 2>/dev/null")
print(f"  Bot trading:  {out}")
out, _ = run("systemctl is-active cryptoapi 2>/dev/null")
print(f"  API/Dashboard: {out}")
print(f"\n  Dashboard: http://{HOST}:8000")
print(f"  API docs:  http://{HOST}:8000/docs")
print(f"\n  Ver logs bot: journalctl -u cryptobot -f")
print(f"  Ver logs api: journalctl -u cryptoapi -f")
print("=" * 60)

client.close()
