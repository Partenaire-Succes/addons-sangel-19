from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    # Prix unitaire original AVANT correction AVCO
    # Sauvegardé automatiquement par le module stock_avco_correction
    # avant toute mise à jour de price_unit ou value
    avco_original_price_unit = fields.Float(
        string="Prix unitaire original (avant correction AVCO)",
        digits=(16, 2),
        readonly=True,
        copy=False,
        help="Prix unitaire enregistré automatiquement avant la correction AVCO. "
             "Permet de tracer l'historique des corrections de migration ProgMag."
    )

    avco_original_value = fields.Float(
        string="Valeur originale (avant correction AVCO)",
        digits=(16, 2),
        readonly=True,
        copy=False,
        help="Valeur totale enregistrée automatiquement avant la correction AVCO."
    )

    avco_correction_date = fields.Datetime(
        string="Date de correction AVCO",
        readonly=True,
        copy=False,
        help="Date et heure à laquelle la correction AVCO a été appliquée."
    )

    avco_correction_user_id = fields.Many2one(
        'res.users',
        string="Corrigé par",
        readonly=True,
        copy=False,
        help="Utilisateur ayant appliqué la correction AVCO."
    )

    avco_corrected = fields.Boolean(
        string="Corrigé par AVCO",
        default=False,
        readonly=True,
        copy=False,
        help="Indique si ce mouvement a été corrigé par le module de correction AVCO."
    )
