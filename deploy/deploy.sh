#!/usr/bin/env bash
#
# Despliega el panel en el droplet: trae main, actualiza SOLO los addons que
# cambiaron y reinicia Odoo. Sirve tanto para el workflow como a mano.
#
# Variables opcionales:
#   ODOO_DB      base de datos            (default: soled)
#   COMPOSE_FILE archivo de compose       (default: docker-compose.yml)
#   SKIP_BACKUP  1 para saltar el pg_dump (default: hace backup)
#   DRY_RUN      1 para solo mostrar que haria
set -euo pipefail

cd "$(dirname "$0")/.."

ODOO_DB="${ODOO_DB:-soled}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
COMPOSE="docker compose -f ${COMPOSE_FILE}"

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

log "Trayendo cambios"
BEFORE="$(git rev-parse HEAD)"
git fetch origin main
git reset --hard origin/main
AFTER="$(git rev-parse HEAD)"

if [ "$BEFORE" = "$AFTER" ]; then
    echo "Ya estaba en $(git log --oneline -1). Nada que desplegar."
    exit 0
fi

echo "De $(git log --oneline -1 "$BEFORE" | cut -c1-60)"
echo "a  $(git log --oneline -1 "$AFTER"  | cut -c1-60)"

# Que addons toco el rango. Es lo que antes habia que recordar a mano.
CHANGED="$(git diff --name-only "$BEFORE" "$AFTER" -- addons/ \
    | awk -F/ 'NF>2 {print $2}' | sort -u)"

if [ -z "$CHANGED" ]; then
    echo "Ningun addon cambio (solo archivos fuera de addons/). No hace falta actualizar."
    exit 0
fi

log "Addons con cambios"
echo "$CHANGED" | sed 's/^/  /'

# Instalados segun la base: los nuevos van con -i y el resto con -u.
INSTALLED="$($COMPOSE exec -T db psql -U odoo -d "$ODOO_DB" -tAc \
    "SELECT name FROM ir_module_module WHERE state = 'installed';" | tr -d ' ')"

TO_UPDATE=""
TO_INSTALL=""
for addon in $CHANGED; do
    [ -f "addons/$addon/__manifest__.py" ] || continue
    if echo "$INSTALLED" | grep -qx "$addon"; then
        TO_UPDATE="${TO_UPDATE:+$TO_UPDATE,}$addon"
    else
        TO_INSTALL="${TO_INSTALL:+$TO_INSTALL,}$addon"
    fi
done

if [ -z "$TO_UPDATE" ] && [ -z "$TO_INSTALL" ]; then
    echo "Los cambios no tocan ningun modulo Odoo valido."
    exit 0
fi

ARGS=""
[ -n "$TO_INSTALL" ] && { echo "  instalar: $TO_INSTALL"; ARGS="$ARGS -i $TO_INSTALL"; }
[ -n "$TO_UPDATE" ]  && { echo "  actualizar: $TO_UPDATE"; ARGS="$ARGS -u $TO_UPDATE"; }

if [ "${DRY_RUN:-0}" = "1" ]; then
    log "DRY_RUN: se detiene aca"
    echo "odoo -d $ODOO_DB$ARGS --without-demo=all --stop-after-init"
    exit 0
fi

if [ "${SKIP_BACKUP:-0}" != "1" ]; then
    log "Backup de la base"
    mkdir -p backups
    BACKUP="backups/${ODOO_DB}-$(date +%Y%m%d-%H%M%S).sql"
    $COMPOSE exec -T db pg_dump -U odoo "$ODOO_DB" > "$BACKUP"
    echo "  $BACKUP ($(du -h "$BACKUP" | cut -f1))"
    # Dejamos solo los ultimos 10 para no llenar el disco.
    ls -1t backups/*.sql 2>/dev/null | tail -n +11 | xargs -r rm --
fi

# El upgrade corre en un contenedor descartable: si falla, el que atiende
# requests sigue con el codigo viejo en memoria y no se reinicia.
log "Actualizando modulos"
$COMPOSE run --rm odoo odoo -d "$ODOO_DB" $ARGS --without-demo=all --stop-after-init

# Los bundles de assets viven como adjuntos en la base. Odoo los regenera
# solo cuando detecta el cambio, y cuando no lo detecta el navegador sigue
# sirviendo el CSS/JS viejo y parece que el deploy no hizo nada. Borrarlos
# es barato: se rearman en el primer request.
log "Invalidando los assets compilados"
$COMPOSE exec -T db psql -U odoo -d "$ODOO_DB" -qc \
    "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%';"

log "Reiniciando Odoo"
$COMPOSE restart odoo

log "Listo: $(git log --oneline -1)"
echo "Acordate del hard refresh en el navegador (Ctrl+Shift+R)."
