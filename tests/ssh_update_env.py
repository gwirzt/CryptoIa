"""
tests/ssh_update_env.py — Actualiza el .env del servidor con los nuevos parametros v3
"""
import paramiko

HOST = "192.168.1.6"
USER = "gwirzt"
PASS = "1211Gustavo"
ENV_PATH = "/home/gwirzt/CryptoIa/.env"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)

def run(cmd, timeout=15):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    return out

# Leer el .env actual
sftp = client.open_sftp()
with sftp.open(ENV_PATH, "r") as f:
    contenido = f.read().decode("utf-8")

print("=== Actualizando .env ===")

# Cambios a aplicar: (clave, valor_nuevo)
# Si la clave existe → reemplazar valor; si no existe → agregar al final
cambios = {
    "TRAILING_STOP_ACTIVACION_PCT": "0.3",
    "TRAILING_STOP_PROTECCION_PCT": "0.2",
    "CICLOS_MIN_EN_POSICION":       "1",
    "PNL_MIN_PARA_VENDER_IA":       "0.1",
    "CONFIANZA_VENTA_FORZADA":      "75",
    "PNL_MAX_PERDIDA_IA":           "-0.5",
    "MACD_HIST_MIN_COMPRA":         "-15.0",
    "COOLDOWN_POST_STOPLOSS":       "2",
}

lineas = contenido.splitlines()
claves_encontradas = set()

# Reemplazar valores existentes
nuevas_lineas = []
for linea in lineas:
    reemplazada = False
    for clave, valor in cambios.items():
        if linea.startswith(f"{clave}="):
            valor_viejo = linea.split("=", 1)[1]
            nuevas_lineas.append(f"{clave}={valor}")
            claves_encontradas.add(clave)
            if valor_viejo != valor:
                print(f"  ✏️  {clave}: {valor_viejo} → {valor}")
            else:
                print(f"  ✅ {clave}={valor} (sin cambio)")
            reemplazada = True
            break
    if not reemplazada:
        nuevas_lineas.append(linea)

# Agregar claves que no existían
claves_nuevas = set(cambios.keys()) - claves_encontradas
if claves_nuevas:
    nuevas_lineas.append("")
    nuevas_lineas.append("# Parametros v3 — agregados automaticamente")
    for clave in sorted(claves_nuevas):
        nuevas_lineas.append(f"{clave}={cambios[clave]}")
        print(f"  ➕ {clave}={cambios[clave]} (nuevo)")

nuevo_contenido = "\n".join(nuevas_lineas) + "\n"

# Escribir el .env actualizado
with sftp.open(ENV_PATH, "w") as f:
    f.write(nuevo_contenido.encode("utf-8"))

sftp.close()
print("\n  ✅ .env actualizado correctamente")

# Reiniciar servicios para aplicar los nuevos valores
print("\n=== Reiniciando servicios ===")
for svc in ["cryptobot", "cryptoapi"]:
    out = run(f"echo '{PASS}' | sudo -S systemctl restart {svc} 2>&1")
    lineas_out = [l for l in out.splitlines() if "password" not in l.lower() and l.strip()]
    print(f"  {svc}: {'OK' if not lineas_out else chr(10).join(lineas_out)}")

import time
time.sleep(5)

# Verificar
print("\n=== Estado final ===")
for svc in ["cryptobot", "cryptoapi"]:
    out = run(f"systemctl is-active {svc}")
    estado = "✅ ACTIVO" if out.strip() == "active" else f"❌ {out}"
    print(f"  {svc:15} {estado}")

print("\n=== Logs del bot (últimas 12 líneas) ===")
out = run("journalctl -u cryptobot -n 12 --no-pager 2>/dev/null")
print(out)

client.close()
print("\nListo.")
