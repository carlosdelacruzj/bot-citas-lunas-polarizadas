# Runbook operativo

## Interpretacion de salud

- `GET /health` comprueba vida del proceso.
- `worker_running=true` con `reason=outside_hot_window` es una espera saludable,
  no una caida.
- Confirmar la fase real con `GET /api/v1/worker` mediante el dashboard.

## Recuperar el worker

1. Revisar `/health`, fase, `next_check_at` y el ultimo error.
2. Si esta `outside_hot_window`, no reiniciar.
3. Si el proceso no responde, cerrar solo el proceso worker y ejecutar
   `scripts/start-worker.ps1`.
4. Confirmar `/health` y luego la fase del worker.

## Recuperar admin API y dashboard

1. Verificar `http://127.0.0.1:8766/health`.
2. Detener solo el proceso admin-dashboard.
3. Ejecutar `scripts/start-admin-dashboard.ps1 -SkipBuild` si el build existe;
   sin `-SkipBuild` si debe reconstruirse.
4. Abrir `http://127.0.0.1:8766/` y comprobar ordenes y runs.
5. Rollback: ejecutar `appointment-bot-admin-api` y `npm start` desde
   `dashboard/` como procesos separados.

## Reporte semanal y alertas

```powershell
appointment-bot-client weekly-report --start 2026-07-06 --end 2026-07-12
```

Agregar `--notify` para enviar por Telegram los outliers CAPTCHA y aumentos
sostenidos de `slot_lost`. Comparar siempre rangos de igual duracion.

## Backup y restore PostgreSQL

```powershell
scripts/verify-postgres-backup.ps1
```

El script crea el dump dentro del contenedor, restaura en una base temporal,
compara conteos esenciales y elimina base y dump en `finally`. No deja backups
en el repositorio. Ejecutarlo en una ventana de baja actividad.
