from odoo import fields, models, api, _
from odoo.exceptions import ValidationError  

class StockScrapBreakers(models.Model):
    _inherit = "stock.scrap.breakers"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Groupe de casses'
    _rec_name = 'name'

    name = fields.Char(string="Nom", required=True, copy=False)
    start = fields.Datetime(string="Début", required=True, copy=False)
    end = fields.Datetime(string="Fin", required=True, copy=False)
    scrap_ids = fields.One2many('stock.scrap', 'breaker_id')
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('done', 'Terminé'),
        ('cancelled', 'Annulé'),
    ], string="État", default='draft', tracking=True)

    def action_validate_breaker(self):
        """Valide le groupe de rebuts en confirmant tous les rebuts associés"""
        for breaker in self:
            breaker.state = 'done'
    
    def action_cancel_breaker(self):
        """Annule le groupe de rebuts"""
        for breaker in self:
            breaker.state = 'cancelled'

    def action_set_to_draft(self):
        """Remet le groupe de rebuts à l'état brouillon"""
        for breaker in self:
            breaker.state = 'draft'

    def unlink(self):
        for breaker in self:
            if breaker.state != 'draft':
                raise ValidationError(_("Vous ne pouvez supprimer que des groupes de casses en état 'Brouillon'."))
        return super(StockScrapBreakers, self).unlink()

class StockScrap(models.Model):
    _inherit = "stock.scrap"

    breaker_id = fields.Many2one('stock.scrap.breakers', string="Groupe de casses", copy=False)