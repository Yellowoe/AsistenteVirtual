# AAAV CxP (Cuentas por Pagar)
## Alcance
- Validación contra OC/recepción, aging y programación de pagos 13s.

## Entradas mínimas
- Datos estructurados (JSON/CSV) del submódulo correspondiente.
- Periodo, moneda y supuestos.

## Salidas
- JSON conforme a `aaav_cxp_schema.json` + CSV opcional.

## Reglas
- Valida consistencia.
- Si faltan datos críticos, explica supuestos.
- Devuelve también un resumen ejecutivo en 3 puntos.
