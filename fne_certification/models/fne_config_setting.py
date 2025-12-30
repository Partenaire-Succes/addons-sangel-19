# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import logging

_logger = logging.getLogger(__name__)

class FneConfigSettings(models.Model):
    _name = 'fne.config.settings'
    _description = 'Paramètres de connexion FNE'
    _rec_name = 'fne_point_of_sale'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    is_fne_enabled = fields.Boolean(
        string="Activer la certification FNE",
        default=False,
        help="Active la certification automatique via l'API FNE"
    )
    
    environment = fields.Selection([
        ('test', 'Test'),
        ('production', 'Production')
    ], string='Environnement', default='test', required=True)
    
    fne_api_token = fields.Char(
        string='Token API FNE',
        required=True,
        help="Clé API fournie par la DGI (visible dans Paramétrage après validation)"
    )
    
    fne_api_url = fields.Char(
        string='URL API',
        compute='_compute_api_url',
        store=True,
        readonly=True
    )
    
    fne_point_of_sale = fields.Char(
        string='Point de vente',
        required=True,
        help="Code du point de vente (ex: 23)"
    )
    
    fne_establishment = fields.Char(
        string='Établissement',
        required=True,
        help="Nom de l'établissement (ex: Orange Riviera Mpouto)"
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company
    )
    
    auto_certify_on_post = fields.Boolean(
        string="Certification automatique",
        default=True,
        help="Certifier automatiquement à la validation de la facture"
    )
    
    commercial_message = fields.Text(
        string="Message commercial",
        help="Message commercial par défaut sur les factures"
    )
    
    footer = fields.Text(
        string="Pied de page",
        help="Texte du pied de page des factures"
    )
    
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validé')
    ], string='Statut', default='draft', tracking=True)

    @api.depends('environment')
    def _compute_api_url(self):
        for rec in self:
            if rec.environment == 'test':
                rec.fne_api_url = 'http://54.247.95.108/ws'
            else:
                # L'URL de production sera fournie par la DGI après validation
                rec.fne_api_url = ''

    def action_validate(self):
        self.write({'state': 'validated'})

    def test_connection(self):
        """Tester la connexion à l'API FNE"""
        self.ensure_one()
        
        if not self.fne_api_token:
            raise UserError(_("Veuillez configurer le token API FNE."))
        
        if not self.fne_api_url:
            raise UserError(_("L'URL de l'API n'est pas configurée."))
        
        headers = {
            'Authorization': f'Bearer {self.fne_api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Test de connexion simple
        test_data = {
            "invoiceType": "sale",
            "paymentMethod": "cash",
            "template": "B2C",
            "isRne": False,
            "clientCompanyName": "Test Client",
            "clientPhone": "0000000000",
            "clientEmail": "test@example.com",
            "pointOfSale": self.fne_point_of_sale,
            "establishment": self.fne_establishment,
            "items": [{
                "taxes": ["TVA"],
                "description": "Test Article",
                "quantity": 1,
                "amount": 1000,
                "measurementUnit": "pcs"
            }]
        }
        
        try:
            response = requests.post(
                f'{self.fne_api_url}/external/invoices/sign',
                headers=headers,
                json=test_data,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connexion réussie!'),
                        'message': _('La connexion à l\'API FNE est fonctionnelle.'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                error_msg = response.json().get('message', 'Erreur inconnue')
                raise UserError(_(f"Erreur de connexion: {error_msg}"))
                
        except requests.exceptions.RequestException as e:
            _logger.error(f"Erreur de connexion FNE: {str(e)}")
            raise UserError(_(f"Impossible de se connecter à l'API FNE: {str(e)}"))

    @api.constrains('company_id')
    def _check_unique_config_per_company(self):
        for rec in self:
            if self.search_count([('company_id', '=', rec.company_id.id), ('id', '!=', rec.id)]) > 0:
                raise ValidationError(_("Une seule configuration FNE est autorisée par société."))

    @api.model
    def get_active_config(self, company_id=None):
        """Récupérer la configuration active"""
        if not company_id:
            company_id = self.env.company.id
        
        config = self.search([
            ('company_id', '=', company_id),
            ('is_fne_enabled', '=', True)
        ], limit=1)
        
        return config