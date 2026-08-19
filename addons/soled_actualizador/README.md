# Soled - Actualizador de Marketplaces

Módulo de Odoo, solo lectura, que refleja la tabla `marketplace_product_change_actions`
(el historial de cambios de precio/stock/estado propagados a Fravega y OnCity) para
poder verla dentro de Odoo. Consume el endpoint que ya existe en `internal-soled`:
`GET /internal/marketplace-change-actions`. No escribe nada en el catálogo real.

## Instalación

1. Copiar la carpeta `soled_actualizador/` al `addons_path` de tu instancia de Odoo
   (en el servidor de DigitalOcean).
2. Reiniciar el servicio de Odoo.
3. Activar el modo desarrollador, ir a **Apps**, quitar el filtro "Apps" (para
   ver módulos no listados como app), buscar "Soled - Actualizador de
   Marketplaces" e instalarlo.

## Configuración obligatoria (después de instalar)

Ir a **Ajustes → Técnico → Parámetros → Parámetros del sistema** y crear:

| Clave | Valor |
|---|---|
| `soled_actualizador.api_base_url` | URL base donde corre `internal-soled` (la misma que usa `products.api` en `INTERNAL_SOLED_API_BASE_URL`, sin la barra final) |
| `soled_actualizador.api_key` | La misma API key interna que valida `internal-soled` (`INTERNAL_API_KEY` en su `.env`, que es el mismo secreto que `products.api` manda como `INTERNAL_SOLED_API_KEY`) |
| `soled_actualizador.page_size` | Opcional, por defecto `200` — tamaño de página al paginar el endpoint |

Sin estos dos primeros parámetros el sync tira un error claro pidiéndolos.

## Uso

- El menú **"Actualizador Soled" → "Cambios a marketplaces"** muestra la
  lista, con badges de color por marketplace y estado, una columna "Cambio"
  con un resumen legible (ej. `Precio: $163.994 → $164.994`, sin JSON a la
  vista) y filtros/agrupados por estado, marketplace, tipo de cambio y
  origen (incluye un filtro para ver solo las pausas automáticas,
  `source = auto_pause_on_failure`).
- El botón **"Ver detalle"** de cada fila abre un modal (no navega a otra
  página) con el resumen del cambio arriba de todo, y el JSON crudo
  (valores viejo/nuevo, request/response) recién en la pestaña "Detalle
  técnico" al final, para quien lo necesite debuguear.
- Hay un cron (**Soled Actualizador: sincronizar cambios de marketplace**)
  que corre cada 5 minutos y trae todo lo nuevo. El intervalo se puede
  cambiar desde Ajustes → Técnico → Automatización → Acciones planificadas.
- Para no esperar al cron mientras probás: abrí la lista, ícono de engranaje
  (Acciones) → **"Sincronizar ahora"**.

## Cosas a tener en cuenta

- **Menú separado a propósito.** No tengo el ID técnico de tu menú
  "Retailer" existente, así que este módulo crea su propio menú de nivel
  superior ("Actualizador Soled") para no arriesgarme a duplicarlo mal. Para
  colgarlo de tu "Retailer" real: conseguime el ID externo de ese menú (modo
  desarrollador → clic derecho sobre el menú → "Editar Menú") y te ajusto el
  `parent` en `views/marketplace_change_action_menus.xml`, o movelo vos
  mismo por UI en Ajustes → Técnico → Interfaz de Usuario → Menús (no
  requiere tocar código).
- **Versión de Odoo.** Si tu instancia es Odoo 18+, puede que la vista lista
  necesite `<list>` en vez de `<tree>` — es un cambio de una sola etiqueta en
  `views/marketplace_change_action_views.xml` si al instalar tira error de
  vista.
- **Sync es un barrido completo, no incremental.** El endpoint de
  `internal-soled` no tiene un filtro tipo "traeme solo lo que cambió desde
  tal fecha", así que cada corrida del cron pagina TODA la tabla. Con el
  volumen actual no debería ser un problema, pero si en unos meses la tabla
  crece mucho y el sync empieza a tardar, conviene agregar un filtro
  incremental (por `updatedAt` o `id`) en el endpoint de `internal-soled` y
  ajustar `cron_sync_change_actions` para usarlo — es un cambio chico,
  avisame cuando llegue el momento.
- Es de **solo lectura** por diseño (no se puede crear/editar/borrar desde
  Odoo) — la fuente de verdad sigue siendo `internal-soled`.
