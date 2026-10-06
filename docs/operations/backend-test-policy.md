# Politica de pruebas backend por riesgo

Estado: vigente. Ultima verificacion: `2026-09-01`.

El objetivo no es maximizar un porcentaje global. CI mide statements y ramas de
todo `appointment_bot`, pero bloquea regresiones mediante umbrales iniciales por
modulo critico definidos en `scripts/check-critical-coverage.py`.

## Matriz inicial

| Riesgo | Escenarios propietarios |
|---|---|
| Multiples tramites y preflight | `test_program_selection.py`, `test_program_resolution.py` |
| Screenshot bloqueado y reobservacion | `test_slot_evidence.py` |
| Lease global y claim de orden | `test_worker.py`, `test_database.py` |
| Sesiones manuales concurrentes | `test_manual_session_exclusivity.py` |
| Ambiguedad WhatsApp tras interaccion | `test_whatsapp_delivery.py` |
| Migracion y contabilidad integral | `test_database.py`, `test_finance_receipt_quality.py` |
| Submit activo y confirmacion Programado | `test_order_transitions.py`, `test_reservation_captcha.py` |

## Regla de cambio

- Toda correccion o nueva excepcion en una invariante critica debe agregar o
  ajustar primero un escenario que falle sin el comportamiento esperado.
- No se reduce un umbral para hacer verde una rama. Si una refactorizacion mueve
  la autoridad, se traslada el umbral al nuevo modulo sin perder cobertura.
- Los umbrales son un piso inicial, no una meta. Se elevan cuando nuevos
  escenarios dejan un margen estable y nunca se bajan sin una decision
  documentada.
- Pruebas de navegador simulan el portal o WhatsApp y no envian, reservan ni
  consumen credenciales productivas.

## Ejecucion

```powershell
python -m pytest -q --cov=appointment_bot --cov-branch `
  --cov-report=json:reports/ci/coverage.json
python scripts/check-critical-coverage.py reports/ci/coverage.json
```

El artefacto de CI conserva `pytest.xml` y `coverage.json` para revisar una
regresion. El porcentaje total informa deuda general; solo los pisos criticos
son obligatorios durante esta etapa inicial.
