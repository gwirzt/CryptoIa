"""
tests/ssh_deploy_v3.py — Deploy directo al servidor sin git
Copia los archivos modificados y reinicia los servicios
"""
import paramiko
import os

HOST    = "192.168.1.6"
USER    = "gwirzt"
PASS    = "1211Gustavo"
PROYECTO = "/home/gwirzt/CryptoIa"

# Archivos a copiar: (ruta_local, ruta_remota)
ARCHIVOS = [
    ("config.py",                    f"{PROYECTO}/config.py"),
    ("src/bot/ciclo.py",             f"{PROYECTO}/src/bot/ciclo.py"),
    ("src/trading/posicion.py",      f"{PROYECTO}/src/trading/posicion.py"),
    ("src/api/main.py",              f"{PROYECTO}/src/api/main.py"),
    ("src/dashboard/index.html",     f"{PROYECTO}/src/dashboard/index.html"),
]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("  DEPLOY CryptoIA v3 — Sin git")
print("=" * 60)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

def run(cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    return out, err

# 1. Copiar archivos vía SFTP
print("\n[1/3] Copiando archivos...")
sftp = client.open_sftp()
for local_rel, remoto in ARCHIVOS:
    local_abs = os.path.join(BASE_DIR, local_rel)
    if not os.path.exists(local_abs):
        print(f"  ⚠️  No encontrado: {local_abs}")
        continue
    sftp.put(local_abs, remoto)
    print(f"  ✅ {local_rel} → {remoto}")
sftp.close()

# 2. Migración de DB (agregar columnas nuevas si no existen)
print("\n[2/3] Migrando base de datos...")
sql_migracion = """
PGPASSWORD=Crypto2026 psql -h localhost -U Crypto -d CryptoTrade -c "
ALTER TABLE posicion_v2 ADD COLUMN IF NOT EXISTS precio_maximo DECIMAL(18,8);
ALTER TABLE posicion_v2 ADD COLUMN IF NOT EXISTS ultimo_stoploss TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS ciclos_log (
    id                SERIAL PRIMARY KEY,
    timestamp         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    simbolo           VARCHAR(20) NOT NULL DEFAULT 'BTC/USDT',
    precio_btc        DECIMAL(18,2),
    accion            VARCHAR(30),
    precio_compra_pos DECIMAL(18,2),
    pnl_pct           DECIMAL(8,4),
    pnl_usdt          DECIMAL(18,2),
    razon             TEXT,
    rsi               DECIMAL(6,2),
    macd_hist         DECIMAL(12,4),
    total_comprado    DECIMAL(18,2) DEFAULT 0,
    total_vendido     DECIMAL(18,2) DEFAULT 0,
    diferencia        DECIMAL(18,2) DEFAULT 0
);
" 2>/dev/null
"""
out, err = run(sql_migracion, timeout=30)
if "ERROR" in (out + err).upper() and "already exists" not in (out + err).lower():
    print(f"  ⚠️  {err or out}")
else:
    print("  ✅ Tablas y columnas OK")

# Inicializar precio_maximo en posiciones existentes
out, err = run("""
PGPASSWORD=Crypto2026 psql -h localhost -U Crypto -d CryptoTrade -c "
UPDATE posicion_v2 SET precio_maximo = precio_compra WHERE precio_maximo IS NULL;
" 2>/dev/null
""")
print(f"  ✅ precio_maximo inicializado: {out.strip()}")

# 3. Reiniciar servicios
print("\n[3/3] Reiniciando servicios...")
for svc in ["cryptobot", "cryptoapi"]:
    out, err = run(f"sudo systemctl restart {svc} 2>&1")
    print(f"  {svc}: {out or 'OK'}")

import time
time.sleep(4)

# Verificar estado
print("\n[VERIFICACIÓN]")
for svc in ["cryptobot", "cryptoapi"]:
    out, _ = run(f"systemctl is-active {svc}")
    estado = "✅ ACTIVO" if out.strip() == "active" else f"❌ {out}"
    print(f"  {svc:15} {estado}")

# Últimas líneas de log del bot
print("\n[LOGS DEL BOT — últimas 15 líneas]")
out, _ = run("journalctl -u cryptobot -n 15 --no-pager 2>/dev/null")
print(out if out else "  (sin logs)")

client.close()
print("\n" + "=" * 60)
print("  Deploy completado")
print("=" * 60)
