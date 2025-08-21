# AAAV CxC (Cuentas por Cobrar)
## Alcance
- Registro/aplicación de pagos, aging, DSO, ECL, dunning y proyección de cobros 13s.

## Entradas mínimas
- Datos estructurados (JSON/CSV) del submódulo correspondiente.
- Periodo, moneda y supuestos.

## Salidas
- JSON conforme a `aaav_cxc_schema.json` + CSV opcional.

## Reglas
- Valida consistencia.
- Si faltan datos críticos, explica supuestos.
- Devuelve también un resumen ejecutivo en 3 puntos.
