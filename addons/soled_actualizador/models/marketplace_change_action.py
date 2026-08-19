import json
import logging
from datetime import datetime, timezone

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 200
REQUEST_TIMEOUT_SECONDS = 15


class MarketplaceChangeAction(models.Model):
    _name = 'soled.marketplace.change.action'
    _description = 'Cambio propagado a un marketplace (Fravega/OnCity)'
    _order = 'remote_created_at desc, id desc'
    _rec_name = 'action_id'

    action_id = fields.Char(string='Action ID', required=True, index=True, readonly=True)
    dedupe_key = fields.Char(string='Dedupe Key', readonly=True)
    source = fields.Char(string='Origen', readonly=True, index=True)
    sku = fields.Char(string='SKU', readonly=True, index=True)
    meli_item_id = fields.Char(string='Item MLA', readonly=True)
    marketplace = fields.Char(string='Marketplace', readonly=True, index=True)
    change_type = fields.Char(string='Tipo de cambio', readonly=True, index=True)
    status = fields.Char(string='Estado', readonly=True, index=True)

    old_value_json = fields.Text(string='Valor anterior', readonly=True)
    new_value_json = fields.Text(string='Valor nuevo', readonly=True)
    request_snapshot_json = fields.Text(string='Request enviado', readonly=True)
    response_snapshot_json = fields.Text(string='Response recibido', readonly=True)

    publication_id_ext = fields.Integer(string='Publication ID (Soled)', readonly=True)
    external_product_id = fields.Char(string='ID producto externo', readonly=True)
    external_sku = fields.Char(string='SKU externo', readonly=True)

    attempts = fields.Integer(string='Intentos', readonly=True)
    max_attempts = fields.Integer(string='Intentos máximos', readonly=True)
    bullmq_job_id = fields.Char(string='Job ID', readonly=True)

    error_code = fields.Char(string='Código de error', readonly=True)
    error_message = fields.Text(string='Mensaje de error', readonly=True)

    remote_queued_at = fields.Datetime(string='Encolado', readonly=True)
    remote_started_at = fields.Datetime(string='Iniciado', readonly=True)
    remote_finished_at = fields.Datetime(string='Finalizado', readonly=True)
    remote_created_at = fields.Datetime(string='Creado (origen)', readonly=True)
    remote_updated_at = fields.Datetime(string='Actualizado (origen)', readonly=True)

    last_synced_at = fields.Datetime(string='Última sincronización', readonly=True)

    change_summary = fields.Char(
        string='Cambio',
        compute='_compute_change_summary',
        store=True,
    )

    _sql_constraints = [
        (
            'action_id_uniq',
            'unique(action_id)',
            'Ya existe un registro sincronizado con ese Action ID.',
        ),
    ]

    # ------------------------------------------------------------------
    # Resumen legible (reemplaza mostrar el JSON crudo en la UI)
    # ------------------------------------------------------------------

    @api.depends('change_type', 'old_value_json', 'new_value_json')
    def _compute_change_summary(self):
        for record in self:
            record.change_summary = record._build_change_summary()

    def _build_change_summary(self):
        self.ensure_one()
        old = self._safe_json_loads(self.old_value_json) or {}
        new = self._safe_json_loads(self.new_value_json) or {}

        if self.change_type == 'price':
            return 'Precio: {} → {}'.format(
                self._format_money(old.get('price')),
                self._format_money(new.get('price')),
            )

        if self.change_type == 'stock':
            return 'Stock: {} → {}'.format(
                self._format_or_dash(old.get('stock')),
                self._format_or_dash(new.get('stock')),
            )

        if self.change_type == 'status':
            return 'Estado: {} → {}'.format(
                self._format_or_dash(old.get('status')),
                self._format_or_dash(new.get('status')),
            )

        return '—'

    @staticmethod
    def _safe_json_loads(value):
        if not value:
            return None

        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_or_dash(value):
        if value is None or value == '':
            return '—'

        return str(value)

    @classmethod
    def _format_money(cls, value):
        if value is None or value == '':
            return '—'

        try:
            amount = float(value)
        except (TypeError, ValueError):
            return cls._format_or_dash(value)

        return '${:,.0f}'.format(amount).replace(',', '.')

    # ------------------------------------------------------------------
    # Sync desde internal-soled
    # ------------------------------------------------------------------

    @api.model
    def _get_api_config(self):
        params = self.env['ir.config_parameter'].sudo()
        base_url = params.get_param('soled_actualizador.api_base_url')
        api_key = params.get_param('soled_actualizador.api_key')

        if not base_url or not api_key:
            raise UserError(
                'Falta configurar soled_actualizador.api_base_url y '
                'soled_actualizador.api_key en Ajustes > Técnico > '
                'Parámetros del sistema. Son la URL base de internal-soled '
                'y la misma API key interna que usa products.api.'
            )

        page_size = params.get_param('soled_actualizador.page_size', DEFAULT_PAGE_SIZE)

        try:
            page_size = int(page_size)
        except (TypeError, ValueError):
            page_size = DEFAULT_PAGE_SIZE

        return base_url.rstrip('/'), api_key, page_size

    @api.model
    def _fetch_page(self, base_url, api_key, limit, offset):
        response = requests.get(
            f'{base_url}/internal/marketplace-change-actions',
            headers={'x-internal-api-key': api_key},
            params={'limit': limit, 'offset': offset},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()

    @api.model
    def cron_sync_change_actions(self):
        """Recorre todo /internal/marketplace-change-actions y hace upsert local.

        Nota: el endpoint no ofrece un filtro tipo "updatedSince", asi que
        esto es un barrido completo en cada corrida (paginado). Funciona bien
        mientras la tabla tenga un volumen moderado; si en el futuro crece
        mucho, conviene agregar un filtro incremental (por updated_at o id)
        del lado de internal-soled y ajustar este metodo para usarlo.
        """
        base_url, api_key, limit = self._get_api_config()
        offset = 0
        total_synced = 0

        while True:
            try:
                page = self._fetch_page(base_url, api_key, limit, offset)
            except requests.RequestException as error:
                _logger.error(
                    '[SOLED-ACTUALIZADOR] Fallo consultando internal-soled: %s',
                    error,
                )
                break

            items = page.get('items') or []

            if not items:
                break

            self._upsert_items(items)
            total_synced += len(items)
            offset += limit

            total = (page.get('pagination') or {}).get('total')

            if total is not None and offset >= total:
                break

        _logger.info('[SOLED-ACTUALIZADOR] Sync completo | filas=%s', total_synced)
        return total_synced

    @api.model
    def _upsert_items(self, items):
        for item in items:
            action_id = item.get('actionId')

            if not action_id:
                continue

            values = self._map_item(item)
            existing = self.search([('action_id', '=', action_id)], limit=1)

            if existing:
                existing.write(values)
            else:
                self.create(values)

    @api.model
    def _map_item(self, item):
        return {
            'action_id': item.get('actionId'),
            'dedupe_key': item.get('dedupeKey'),
            'source': item.get('source'),
            'sku': item.get('sku'),
            'meli_item_id': item.get('meliItemId'),
            'marketplace': item.get('marketplace'),
            'change_type': item.get('changeType'),
            'status': item.get('status'),
            'old_value_json': self._to_json_text(item.get('oldValue')),
            'new_value_json': self._to_json_text(item.get('newValue')),
            'request_snapshot_json': self._to_json_text(item.get('requestSnapshot')),
            'response_snapshot_json': self._to_json_text(item.get('responseSnapshot')),
            'publication_id_ext': item.get('publicationId') or 0,
            'external_product_id': item.get('externalProductId'),
            'external_sku': item.get('externalSku'),
            'attempts': item.get('attempts') or 0,
            'max_attempts': item.get('maxAttempts') or 0,
            'bullmq_job_id': item.get('bullmqJobId'),
            'error_code': item.get('errorCode'),
            'error_message': item.get('errorMessage'),
            'remote_queued_at': self._parse_datetime(item.get('queuedAt')),
            'remote_started_at': self._parse_datetime(item.get('startedAt')),
            'remote_finished_at': self._parse_datetime(item.get('finishedAt')),
            'remote_created_at': self._parse_datetime(item.get('createdAt')),
            'remote_updated_at': self._parse_datetime(item.get('updatedAt')),
            'last_synced_at': fields.Datetime.now(),
        }

    @staticmethod
    def _to_json_text(value):
        if value is None:
            return False

        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _parse_datetime(value):
        if not value:
            return False

        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError:
            return False

        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

        return parsed
