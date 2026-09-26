import json
import logging
from datetime import datetime, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CoresaCatalog(models.Model):
    """Lectura del catalogo Coresa que expone internal-api.

    No guarda nada: el panel lee en vivo. Lo unico que se cachea son las
    marcas, porque sacarlas exige recorrer las 5.400 filas. Es un Model y no
    un AbstractModel porque los abstractos no entran en ir.model y entonces
    no se les puede dar ACL, que es lo que habilita la llamada por RPC.
    """

    _name = "coresa.catalog"
    _description = "Catalogo Coresa"

    name = fields.Char(default="Catalogo")

    API_TIMEOUT = 60
    FACETS_PARAM = "coresa_panel.catalog_facets_cache"
    FACETS_TTL_HOURS = 12
    # macroFamilia existe en la API pero viene null en todo el catalogo, asi
    # que no se expone como filtro.
    CATALOG_FILTERS = ("sku", "marca", "subFamilia", "search", "disponible")

    # Ficha tecnica: se muestran solo los que tengan valor.
    SPEC_FIELDS = [
        ("Material", "Material"), ("Color", "Color"), ("Tipo_Montaje", "Tipo de montaje"),
        ("Tipo_Instalacion", "Tipo de instalación"), ("Soporte", "Soporte"),
        ("IP", "IP"), ("IK", "IK"), ("Anti_Vandalico", "Antivandálico"),
        ("Apto_Exterior", "Apto exterior"), ("Alimentacion", "Alimentación"),
        ("Tension_Entrada", "Tensión de entrada"), ("Tension_Salida", "Tensión de salida"),
        ("Potencia_Nominal", "Potencia nominal"), ("Potencia_Max", "Potencia máxima"),
        ("Corriente", "Corriente"), ("Polos", "Polos"),
        ("Ciclos_Electricos", "Ciclos eléctricos"), ("Ciclos_Mecanicos", "Ciclos mecánicos"),
        ("Lumenes", "Lúmenes"), ("Temp_Color", "Temperatura de color"),
        ("Angulo", "Ángulo"), ("Dimerizable", "Dimerizable"), ("Tipo_Luz", "Tipo de luz"),
        ("Tipo_Camara", "Tipo de cámara"), ("Tipo_Lente", "Tipo de lente"),
        ("Resolucion", "Resolución"), ("Canales", "Canales"), ("Mic", "Micrófono"),
        ("Audio_Bidireccional", "Audio bidireccional"), ("Reconocimiento_IA", "Reconocimiento IA"),
        ("Capacidad_Rostros", "Capacidad de rostros"), ("SATA", "SATA"), ("HDMI", "HDMI"),
        ("Tipo_Conexion", "Tipo de conexión"), ("Tipo_Conector", "Tipo de conector"),
        ("POE", "PoE"), ("Puertos_POE", "Puertos PoE"), ("Ancho_Banda", "Ancho de banda"),
        ("Certificado", "Certificado"),
    ]

    LOGISTICS_FIELDS = [
        ("Unidad_Medida", "Unidad de medida"), ("CantMinima", "Cantidad mínima"),
        ("CantIntermedia", "Cantidad intermedia"), ("CantMaster", "Cantidad master"),
        ("Alto_cm", "Alto (cm)"), ("Ancho_cm", "Ancho (cm)"), ("Largo_cm", "Largo (cm)"),
        ("Peso_kg", "Peso (kg)"), ("Volumen_cc", "Volumen (cc)"),
        ("Dimensiones_Texto", "Dimensiones"),
        ("CodBarra_Unitario", "Código de barras"), ("CodBarra_Master", "Código master"),
        ("Cod_Alternativo", "Código alternativo"), ("Impuestos", "Impuestos"),
    ]

    # ------------------------------------------------------------------
    @api.model
    def _api_base_url(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("coresa_panel.internal_api_base_url", "https://internal.solediluminacion.com")
            .rstrip("/")
        )

    @api.model
    def _api_key(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("coresa_panel.internal_api_key", "_internal")
            .strip()
        )

    @api.model
    def _api_get(self, path, params=None):
        try:
            response = requests.get(
                "%s%s" % (self._api_base_url(), path),
                params=params or {},
                headers={"accept": "*/*", "x-internal-api-key": self._api_key()},
                timeout=self.API_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            raise UserError(_("Error consultando el catálogo Coresa: %s") % error) from error
        except ValueError as error:
            raise UserError(_("El catálogo no devolvió JSON válido.")) from error

    # ------------------------------------------------------------------
    @api.model
    def get_catalog_page(self, limit=48, offset=0, filters=None):
        params = {"limit": limit, "offset": offset}
        for key, value in (filters or {}).items():
            if key in self.CATALOG_FILTERS and str(value or "").strip():
                params[key] = str(value).strip()
        payload = self._api_get("/internal/coresa/products", params)
        payload = payload if isinstance(payload, dict) else {}
        pagination = payload.get("pagination") or {}
        return {
            "items": [
                self._product_payload(item)
                for item in (payload.get("items") or [])
                if isinstance(item, dict)
            ],
            "pagination": {
                "limit": self._as_int(pagination.get("limit")) or limit,
                "offset": self._as_int(pagination.get("offset")),
                "total": self._as_int(pagination.get("total")),
            },
        }

    @api.model
    def _product_payload(self, item):
        return {
            "sku": item.get("SKU") or "",
            "description": item.get("Descripcion") or "",
            "brand": item.get("Marca") or "",
            "family": item.get("Sub_Familia") or "",
            "available": self._as_int(item.get("Disponible")),
            "priceList": self._as_float(item.get("Precio_Lista_1")),
            "currency": item.get("Moneda") or "",
            "priceArs": self._as_float(item.get("Precio_Convertido")),
            "image": item.get("URL_Imagen") or "",
            "datasheet": item.get("URL_Datasheet") or "",
            "web": item.get("URL_Web") or "",
            "specs": self._detail_rows(item, self.SPEC_FIELDS),
            "logistics": self._detail_rows(item, self.LOGISTICS_FIELDS),
        }

    @api.model
    def _detail_rows(self, item, definition):
        rows = []
        for key, label in definition:
            value = item.get(key)
            if value is None or value == "" or value is False:
                continue
            rows.append({"label": label, "value": str(value)})
        return rows

    # ------------------------------------------------------------------
    @api.model
    def get_catalog_facets(self, force=False):
        """Marcas con su conteo. Recorrer 5.400 filas tarda, asi que el
        resultado se cachea: el panel lo pide aparte del listado."""
        param = self.env["ir.config_parameter"].sudo()
        cached = param.get_param(self.FACETS_PARAM, "")
        if cached and not force:
            try:
                data = json.loads(cached)
                computed = datetime.fromisoformat(data.get("computedAt"))
                if datetime.utcnow() - computed < timedelta(hours=self.FACETS_TTL_HOURS):
                    return data
            except (ValueError, TypeError):
                pass

        brands = {}
        offset = 0
        total = 0
        for _page in range(40):
            payload = self._api_get(
                "/internal/coresa/products", {"limit": 500, "offset": offset}
            )
            items = (payload or {}).get("items") or []
            total = self._as_int(((payload or {}).get("pagination") or {}).get("total"))
            for item in items:
                brand = (item or {}).get("Marca")
                if brand:
                    brands[brand] = brands.get(brand, 0) + 1
            offset += len(items)
            if not items or offset >= total:
                break

        data = {
            "brands": [
                {"value": name, "total": count}
                for name, count in sorted(brands.items(), key=lambda entry: -entry[1])
            ],
            "total": total,
            "computedAt": datetime.utcnow().isoformat(),
        }
        param.set_param(self.FACETS_PARAM, json.dumps(data))
        return data

    # ------------------------------------------------------------------
    @api.model
    def _as_int(self, value):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    @api.model
    def _as_float(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
