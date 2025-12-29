# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FNECertificationWizard(models.TransientModel):
    _name = 'fne.certification.wizard'
    _description = "Wizard de certification FNE"

    move_id = fields.Many2one(
        'account.move',
        string='Facture',
        required=True,
        readonly=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Client',
        related='move_id.partner_id',
        readonly=True
    )
    
    move_type = fields.Selection(
        related='move_id.move_type',
        readonly=True
    )
    
    fne_template = fields.Selection(
        related='move_id.fne_template',
        string='Type de client'
    )
    
    fne_payment_method = fields.Selection(
        related='move_id.fne_payment_method',
        string='Méthode de paiement'
    )
    
    commercial_message = fields.Text(
        string="Message commercial",
        help="Message commercial à afficher sur la facture"
    )
    
    footer = fields.Text(
        string="Pied de page",
        help="Message de pied de page personnalisé"
    )
    
    warning_message = fields.Html(
        string='Avertissement',
        compute='_compute_warning_message'
    )
    
    @api.depends('move_id', 'partner_id')
    def _compute_warning_message(self):
        """Afficher des avertissements si nécessaire"""
        for wizard in self:
            warnings = []
            
            # Vérifier le NCC pour B2B
            if wizard.fne_template == 'B2B' and not wizard.partner_id.vat:
                warnings.append("⚠️ Client B2B sans NCC (TVA)")
            
            # Vérifier email et téléphone
            if not wizard.partner_id.email:
                warnings.append("⚠️ Email client manquant")
            
            if not wizard.partner_id.phone and not wizard.partner_id.mobile:
                warnings.append("⚠️ Téléphone client manquant")
            
            # Vérifier les taxes
            has_taxes = any(
                line.tax_ids for line in wizard.move_id.invoice_line_ids
                if line.display_type == 'product'
            )
            if not has_taxes:
                warnings.append("⚠️ Aucune taxe sur les lignes de facture")
            
            if warnings:
                wizard.warning_message = "<div class='alert alert-warning'><ul>" + \
                    "".join(f"<li>{w}</li>" for w in warnings) + \
                    "</ul></div>"
            else:
                wizard.warning_message = "<div class='alert alert-success'>" \
                    "✓ Tous les contrôles sont OK</div>"
    
    @api.model
    def default_get(self, fields_list):
        """Pré-remplir avec les valeurs de la configuration"""
        res = super().default_get(fields_list)
        
        if self._context.get('active_id'):
            move = self.env['account.move'].browse(self._context['active_id'])
            res['move_id'] = move.id
            
            # Récupérer les valeurs par défaut de la config
            config = self.env['fne.config.settings'].get_active_config(move.company_id.id)
            if config:
                if config.commercial_message:
                    res['commercial_message'] = config.commercial_message
                if config.footer:
                    res['footer'] = config.footer
        
        return res
    
    def action_certify(self):
        """Lancer la certification FNE"""
        self.ensure_one()
        
        # Mettre à jour les champs optionnels si remplis
        vals = {}
        if self.commercial_message:
            vals['commercial_message'] = self.commercial_message
        if self.footer:
            vals['footer_note'] = self.footer
        
        if vals:
            self.move_id.write(vals)
        
        # Appeler la méthode de certification
        if self.move_type == 'out_refund':
            # Rediriger vers le wizard avoir
            return {
                'type': 'ir.actions.act_window',
                'name': _('Certifier avoir FNE'),
                'res_model': 'fne.refund.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'active_id': self.move_id.id}
            }
        else:
            # Certification normale
            return self.move_id.action_certify_fne()