from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _check_pickings_validated_for_invoicing(self):
        """Lève une exception (avec message clair et drôle) si une commande a
        des transferts liés (réceptions/livraisons) qui ne sont pas encore à
        l'état "Fait". Centralise la vérification afin qu'elle s'applique à
        TOUTES les voies de facturation : facture classique, acompte en
        pourcentage et acompte à montant fixe — voir _create_invoices ci-dessous
        et SaleAdvancePaymentInv._create_invoices."""
        for order in self:
            pickings_en_attente = order.picking_ids.filtered(
                lambda p: p.state not in ('done', 'cancel')
            )
            if pickings_en_attente:
                raise UserError(_(
                    "🎭 Alerte facture prématurée !\n\n"
                    "Vous voulez facturer la commande %(order)s alors que sa marchandise\n"
                    "est encore en train de faire du tourisme dans l'entrepôt... 🧳\n\n"
                    "Le client va recevoir une facture... et un courant d'air ? 🌬️\n\n"
                    "👉 Validez d'abord la réception/livraison (%(pickings)s), et tout ira bien !",
                    order=order.name,
                    pickings=", ".join(pickings_en_attente.mapped('name')),
                ))

    def _create_invoices(self, grouped=False, final=False, date=None):
        """Override : interdit de facturer une commande tant que ses
        livraisons/réceptions liées ne sont pas validées (état "Fait")."""
        self._check_pickings_validated_for_invoicing()
        return super()._create_invoices(grouped=grouped, final=final, date=date)


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def _create_invoices(self, sale_orders):
        """Override : applique le même garde-fou aux acomptes (pourcentage et
        montant fixe), qui ne passaient pas par sale.order._create_invoices et
        échappaient donc au contrôle. La méthode 'delivered' route déjà vers
        sale_orders._create_invoices (qui fait le contrôle) — pas besoin de le
        refaire ici, on éviterait juste un message en double."""
        if self.advance_payment_method != 'delivered':
            sale_orders._check_pickings_validated_for_invoicing()
        return super()._create_invoices(sale_orders)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    code_article = fields.Char(string='Code article')