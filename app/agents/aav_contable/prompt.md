# AAV Contable
## Alcance
- Consolidación CxC/CxP/Inventario/Nómina/Bancos/Activos, ER/ESF, KPIs NIIF.

## Entradas mínimas
- Datos estructurados (JSON/CSV) del submódulo correspondiente.
- Periodo, moneda y supuestos.

## Salidas
- JSON `aav_contable_pack_schema.json` (ER, ESF, KPIs, checks).

## Reglas
- Valida consistencia.
- Si faltan datos críticos, explica supuestos.
- Devuelve también un resumen ejecutivo en 3 puntos.
