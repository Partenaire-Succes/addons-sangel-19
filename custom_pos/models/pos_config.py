import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

class PosConfig(models.Model):
    _inherit = 'pos.config'

    code_acces = fields.Char(string="Code d'accès pour rupture de stock")
    preset_remise_percentages = fields.Char(
        string="Preset Remise Percentages",
        default="10,20,45",
        help="Comma-separated remise percentages to display as quick buttons in payment screen. Example: 10,20,45"
    )
    # Cloture de caisse report fields
    depot_number = fields.Char(
        string="Numéro de dépôt",
        help="Numéro de dépôt affiché sur le ticket de clôture de caisse (ex: 02)"
    )
    poste_number = fields.Char(
        string="Numéro de poste",
        help="Numéro de poste affiché sur le ticket de clôture de caisse (ex: 05)"
    )

    # Note: Les champs code_acces et preset_remise_percentages sont automatiquement chargés
    # car pos.config charge tous les champs par défaut (pas de _load_pos_data_fields défini)
    # Ils seront disponibles dans this.config.code_acces en JavaScript

    # def get_preset_remise_list(self):
    #     """Parse and validate preset remise percentages."""
    #     if not self.preset_remise_percentages:
    #         return []
    #     try:
    #         # Split by comma and convert to integers, filter out invalid values
    #         values = [int(v.strip()) for v in self.preset_remise_percentages.split(',')]
    #         # Filter valid percentages (0-100)
    #         valid_values = [v for v in values if 0 <= v <= 100]
    #         return sorted(list(set(valid_values)))  # Remove duplicates and sort
    #     except (ValueError, AttributeError):
    #         _logger.warning(f"Invalid preset_remise_percentages format: {self.preset_remise_percentages}")
    #         return []