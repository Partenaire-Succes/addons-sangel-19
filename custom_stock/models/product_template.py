from odoo import fields, models, api, _,tools
from odoo.exceptions import ValidationError, UserError
import re
import logging
from odoo.exceptions import AccessError
from odoo.tools import format_amount

_logger = logging.getLogger(__name__)


class ProductTemplateInherit(models.Model):
    _inherit = 'product.template'


    code_inventory_id = fields.Many2one(
        'code.inventory', 
        string='Code Inventaire'
    )
    radius_id = fields.Many2one(
        'radius.inventory',
        string="Rayon",
        copy=False,
        index=True,
    )
    s_radius_id = fields.Many2one(
        'sub.radius.inventory',
        string="Sous Rayon",
        copy=False,
        index=True,
    )
    family_id = fields.Many2one(
        'family.inventory',
        string="Famille Test",
        copy=False,
        index=True,
    )
    family_categ_id = fields.Many2one('product.category', string='Famille', copy=True)
    s_family_id = fields.Many2one(
        'sub.family.inventory',
        string="Sous Famille",
        copy=False,
        index=True,
    )

    purchase_count = fields.Integer(
        string='Achats',
        compute='_compute_purchase_count'
    )

    average_purchase_price = fields.Float(
        string="Prix moyen d'achat",
        compute="_compute_average_purchase_price",
        store=False  # pas stocké si on veut toujours recalculer à la volée
    )

    discount_ligne = fields.Boolean(
        string="Remise sur ligne",
        default=False,
        help="Cochez si ce produit peut bénéficier d'une remise par ligne."
    )

    discount_total_ligne = fields.Boolean(
        string="Remise sur le total test",
        default=False,
        help="Cochez si ce produit peut bénéficier d'une remise sur le total de la commande."
    )

    percentage_airsi = fields.Float(
        string="Taux AIRSI",
        default=0.0,
    )
    airsi_tax_id = fields.Many2one(
        'account.tax',
        string='Taxe AIRSI',
        domain=[('is_airsi', '=', True)],
        help='Taxe AIRSI à appliquer pour les clients à limite avec paiement à crédit'
    )

    # Nouveau champ pour activer/désactiver la synchronisation
    is_pack_parent = fields.Boolean(
        string="Article pack (carton)",
        help="Activez pour définir ce produit comme un carton/pack qui contient des unités.",
    )
    pack_child_product_id = fields.Many2one(
        "product.product",
        string="Sous-article (unité)",
        help="Produit unité contenu dans le carton.",
        # domain="[('detailed_type', '=', 'product')]",
    )

    pack_qty = fields.Integer(
        string="Qté par carton",
        default=0,
        help="Nombre d'unités contenues dans un carton.",
    )

    # Lecture pratique en équivalences (affichage)
    pack_equiv_cartons_available = fields.Float(
        string="Stock cartons (équiv.)",
        compute="_compute_pack_equivalences",
        digits="Product Unit of Measure",
        help="Nombre de cartons disponibles calculé à partir du stock des unités.",
    )

    pack_equiv_units_available = fields.Float(
        string="Stock unités (équiv.)",
        compute="_compute_pack_equivalences",
        digits="Product Unit of Measure",
        help="Nombre d'unités disponibles (stock réel si vous stockez en unités).",
    )

    pending_units = fields.Float(
        string="Unités en attente",
        default=0.0,
        help="Nombre d'unités vendues en attente de conversion en cartons complets"
    )

    code_article = fields.Char(
        string="Code Article",
        related='default_code',
        copy=False,
    )

    old_price = fields.Float("Ancien prix", readonly=True)

    ##################################- Champs Sage X3 ##################################

    cat_gestion_id = fields.Many2one(
        'product.category.x3',
        string='Catégorie article',
    )

    prod_family_x3_id = fields.Many2one(
        'product.family.x3',
        string='Famille article X3',
    )

    prod_type_x3_id = fields.Many2one(
        'product.type.x3',
        string='Type article',
    )

    prod_status_x3_id = fields.Many2one(
        'product.status.sage',
        string='Statut article',
    )

    price_unit_ttc = fields.Float(
        string="Prix Unitaire TTC",
        help="Prix de vente unitaire toutes taxes comprises.",
    )

    marque = fields.Char(
        string="Marque",
        help="Marque du produit.",
    )

    prod_cond = fields.Char(
        string="Conditionnement",
        help="Type de conditionnement du produit.",
    )

    price_carton = fields.Float(
        string="Prix Carton",
        help="Prix de vente par carton.",
    )

    price_negoce = fields.Float(
        string="Prix Négoce",
        help="Prix de vente pour les clients négoce.",
    )

    price_ecom = fields.Float(
        string="Prix E-commerce",
        help="Prix de vente pour les canaux e-commerce.",
    )

    is_yop_demi_gros = fields.Boolean(
        string="YOP 1/2 Gros",
        default=False,
        help="Cochez si ce produit fait partie de la gamme YOP 1/2 Gros.",
    )

    is_yop_detail = fields.Boolean(
        string="YOP Détail",
        default=False,
        help="Cochez si ce produit fait partie de la gamme YOP Détail.",
    )

    is_synacass_ci = fields.Boolean(
        string="Synacass CI",
        default=False,
        help="Cochez si ce produit fait partie de la gamme Synacass CI.",
    )

    is_square = fields.Boolean(
        string="Square",
        default=False,
        help="Cochez si ce produit fait partie de la gamme Square.",
    )

    is_bassam = fields.Boolean(
        string="Bassam",
        default=False,
        help="Cochez si ce produit fait partie de la gamme Bassam.",
    )

    is_koumassi = fields.Boolean(
        string="Koumassi",
        default=False,
        help="Cochez si ce produit fait partie de la gamme Koumassi.",
    )

    @api.depends('pack_child_product_id.qty_available', 'pack_qty')
    def _compute_pack_equivalences(self):
        for tmpl in self:
            tmpl.pack_equiv_cartons_available = 0
            tmpl.pack_equiv_units_available = 0
            if (getattr(tmpl, "is_pack_parent", False)
                    and tmpl.pack_child_product_id
                    and tmpl.pack_qty > 0):
                units = tmpl.pack_child_product_id.qty_available
                tmpl.pack_equiv_units_available = units
                tmpl.pack_equiv_cartons_available = units // tmpl.pack_qty

    @api.constrains("is_pack_parent", "pack_child_product_id", "pack_qty")
    def _check_pack_config(self):
        for template in self:
            if not template.is_pack_parent:
                continue

            if not template.pack_child_product_id or template.pack_qty <= 0:
                raise ValidationError(
                    _("Pour un article pack, renseignez le sous-article et une quantité par carton > 0.")
                )
            # Eviter référence à soi-même (via variantes)
            if template.pack_child_product_id.product_tmpl_id == template:
                raise ValidationError(_("Le sous-article ne peut pas être le même que l'article pack."))
            # UoM catégories compatibles
            if template.uom_id.category_id != template.pack_child_product_id.uom_id.category_id:
                raise ValidationError(
                    _("Le carton et l'unité doivent appartenir à la même catégorie d'UdM.")
                )

    def action_view_unit_product(self):
        """Action pour voir l'article unitaire"""
        self.ensure_one()
        if not self.unit_product_id:
            return

        return {
            'type': 'ir.actions.act_window',
            'name': 'Article Unitaire',
            'res_model': 'product.product',
            'res_id': self.unit_product_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def reset_pending_units_for_sales(self):
        """Méthode utilitaire pour remettre à zéro les compteurs (maintenance)"""
        self.ensure_one()
        if self.is_pack_parent:
            self.write({'pending_units': 0.0})
            _logger.info(f"[SALE_PACK_SYNC] Remise à zéro du compteur pour {self.name}")

    @api.model
    def reset_all_pending_units(self):
        """Remet à zéro tous les compteurs d'unités en attente"""
        pack_templates = self.search([('is_pack_parent', '=', True)])
        pack_templates.write({'pending_units': 0.0})
        _logger.info(f"[SALE_PACK_SYNC] Remise à zéro de {len(pack_templates)} compteurs")


    def reset_pack_sync_counters(self):
        """Remet à zéro les compteurs de synchronisation pack"""
        pack_templates = self.search([('is_pack_parent', '=', True)])
        pack_templates.write({'pending_units': 0.0})
        _logger.info(f"[PACK_SYNC] {len(pack_templates)} compteurs remis à zéro")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Compteurs remis à zéro'),
                'message': f'{len(pack_templates)} compteurs pack/unité remis à zéro',
                'type': 'success',
            }
        }

    def get_pack_sync_diagnostics(self):
        """Retourne les informations de diagnostic pour la synchronisation"""
        self.ensure_one()
        if not self.is_pack_parent:
            return {"status": "not_pack", "message": "Ce produit n'est pas un pack"}

        return {
            "status": "active",
            "pack_qty": self.pack_qty,
            "pending_units": self.pending_units,
            "child_product": self.pack_child_product_id.name if self.pack_child_product_id else "Non défini",
            "cartons_stock": self.qty_available,
            "units_stock": self.pack_child_product_id.qty_available if self.pack_child_product_id else 0,
            "theoretical_cartons": (
                        self.pack_child_product_id.qty_available / self.pack_qty) if self.pack_qty > 0 else 0,
        }

    @api.model_create_multi
    def create(self, vals_list):
        """
        Contrôle la création de produits - seuls les administrateurs produits peuvent créer
        """
        # Vérifier si l'utilisateur a le droit d'admin produit
        if not self.env.user.has_group('custom_stock.group_product_admin'):
            # Permettre la création automatique (import, synchronisation, etc.)
            # mais pas la création manuelle depuis l'interface
            context = self.env.context
            if not (context.get('install_mode') or
                    context.get('import_file') or
                    context.get('tracking_disable') or
                    context.get('create_product_product') or
                    self.env.context.get('skip_create_check')):
                raise AccessError(
                    "Seuls les administrateurs produits peuvent créer des produits manuellement. "
                    "Contactez votre administrateur système pour obtenir les droits nécessaires."
                )

        return super(ProductTemplateInherit, self).create(vals_list)

    @api.model
    def check_access_rights(self, operation, raise_exception=True):
        """
        Contrôle les droits d'accès selon l'opération
        """
        if operation == 'create':
            if not self.env.user.has_group('custom_stock.group_product_admin'):
                # Permettre les opérations système
                if not (self.env.context.get('install_mode') or
                        self.env.context.get('import_file') or
                        self.env.context.get('skip_create_check')):
                    if raise_exception:
                        raise AccessError(
                            "Vous n'avez pas les droits pour créer des produits. "
                            "Contactez votre administrateur système."
                        )
                    return False

        return super(ProductTemplateInherit, self).check_access_rights(operation, raise_exception)


class ProductProduct(models.Model):
    _inherit = "product.product"

    code_article = fields.Char(
        string="Code Article",
        copy=False,
        related='product_tmpl_id.code_article',
    )

    def action_view_pack_equivalence(self):
        self.ensure_one()
        tmpl = self.product_tmpl_id
        if not tmpl.is_pack_parent:
            return False
        message = _(
            "\nCartons (équiv.): %s\nUnités disponibles: %s\nQté par carton: %s",
            int(tmpl.pack_equiv_cartons_available),
            int(tmpl.pack_equiv_units_available),
            tmpl.pack_qty,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Équivalences de stock"),
                "message": message,
                "sticky": False,
                "type": "info",
            },
        }


    @api.model_create_multi
    def create(self, vals_list):
        """
        Contrôle la création des variantes de produits
        """
        # Vérifier si l'utilisateur a le droit d'admin produit
        if not self.env.user.has_group('custom_stock.group_product_admin'):
            # Permettre la création automatique de variantes
            context = self.env.context
            if not (context.get('install_mode') or
                    context.get('import_file') or
                    context.get('tracking_disable') or
                    context.get('create_product_product') or
                    context.get('skip_create_check')):
                raise AccessError(
                    "Seuls les administrateurs produits peuvent créer des variantes de produits manuellement."
                )
        return super(ProductProduct, self).create(vals_list)

