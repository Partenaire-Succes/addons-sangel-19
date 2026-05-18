# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


class SageX3Mapper:
    """
    Transforme les données Sage X3 en vals Odoo.
    Classe Python pure — instanciée dans les wizards/models Odoo.

    Usage:
        mapper = SageX3Mapper(env)
        mapped, errors = mapper.map_plan_comptable(x3_records)
    """

    def __init__(self, env):
        """
        :param env: odoo Environment (self.env dans un model/wizard)
        """
        self.env = env

    # ── Plan comptable ────────────────────────────────────────────────────────

    def map_plan_comptable(self, x3_records):
        """X3 GACCOUN → vals pour account.account"""
        result, errors = [], []
        for rec in x3_records:
            try:
                code = rec.get('ACC', '').strip()
                if not code:
                    continue
                result.append({
                    'code': code,
                    'name': rec.get('DES', code),
                    'account_type': self._map_account_type(rec.get('ACCTYP', '')),
                })
            except Exception as e:
                errors.append({'record': rec, 'error': str(e)})
                _logger.warning(f"[MAPPER] Plan comptable erreur: {e} | {rec}")
        return result, errors

    def _map_account_type(self, x3_type):
        mapping = {
            '1': 'asset_receivable',
            '2': 'liability_payable',
            '3': 'asset_cash',
            '4': 'income',
            '5': 'expense',
            '6': 'equity',
            '7': 'asset_current',
            '8': 'liability_current',
        }
        return mapping.get(str(x3_type), 'expense')

    # ── Tiers ─────────────────────────────────────────────────────────────────

    def map_clients(self, x3_records):
        """X3 BPCUSTOMER → vals pour res.partner (customer)"""
        result, errors = [], []
        for rec in x3_records:
            try:
                vals = self._map_partner_base(rec)
                vals.update({
                    'customer_rank': 1,
                    'ref': rec.get('BPCNUM', ''),
                })
                result.append(vals)
            except Exception as e:
                errors.append({'record': rec, 'error': str(e)})
        return result, errors

    def map_fournisseurs(self, x3_records):
        """X3 BPSUPPLIER → vals pour res.partner (supplier)"""
        result, errors = [], []
        for rec in x3_records:
            try:
                vals = self._map_partner_base(rec)
                vals.update({
                    'supplier_rank': 1,
                    'ref': rec.get('BPSNUM', ''),
                })
                result.append(vals)
            except Exception as e:
                errors.append({'record': rec, 'error': str(e)})
        return result, errors

    def _map_partner_base(self, rec):
        nom = (rec.get('BPCNAM') or rec.get('BPSNAM') or 'Sans nom').strip()
        adresse = rec.get('BPAADDRESS', {})
        if isinstance(adresse, list):
            adresse = adresse[0] if adresse else {}
        country_id = self._get_country(rec.get('CRY', ''))
        return {
            'name': nom,
            'phone': rec.get('TEL', ''),
            'website': rec.get('WEB', ''),
            'street': adresse.get('ADD1', '') if isinstance(adresse, dict) else '',
            'street2': adresse.get('ADD2', '') if isinstance(adresse, dict) else '',
            'city': adresse.get('CTY', '') if isinstance(adresse, dict) else '',
            'zip': adresse.get('ZIP', '') if isinstance(adresse, dict) else '',
            'country_id': country_id,
            'is_company': True,
        }

    def _get_country(self, code):
        if not code:
            return False
        country = self.env['res.country'].search(
            [('code', '=', code.upper())], limit=1)
        return country.id if country else False

    # ── Écritures comptables ──────────────────────────────────────────────────

    def map_ecritures(self, x3_records):
        """X3 GACCENTRY → vals pour account.move (type: entry)"""
        # Regrouper par numéro de pièce
        pieces = {}
        for rec in x3_records:
            num = rec.get('NUM', '')
            if num not in pieces:
                pieces[num] = {'journal': rec.get('JOU', ''),
                               'date': rec.get('ACCDAT', ''), 'lignes': []}
            pieces[num]['lignes'].append(rec)

        result, errors = [], []
        for num, piece in pieces.items():
            try:
                journal_id = self._get_journal(piece['journal'])
                line_ids = []
                for ligne in piece['lignes']:
                    account_id = self._get_account(ligne.get('ACC', ''))
                    if not account_id:
                        continue
                    montant = float(ligne.get('AMTLOC', 0) or 0)
                    sens = ligne.get('SNS', 'D')
                    line_ids.append((0, 0, {
                        'account_id': account_id,
                        'name': ligne.get('DES', '/'),
                        'debit': montant if sens == 'D' else 0.0,
                        'credit': montant if sens == 'C' else 0.0,
                        'date_maturity': self._parse_date(ligne.get('DUDDAT')),
                    }))
                if line_ids:
                    result.append({
                        'move_type': 'entry',
                        'ref': num,
                        'date': self._parse_date(piece['date']),
                        'journal_id': journal_id,
                        'line_ids': line_ids,
                    })
            except Exception as e:
                errors.append({'piece': num, 'error': str(e)})
                _logger.warning(f"[MAPPER] Écriture {num}: {e}")
        return result, errors

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_account(self, code):
        if not code:
            return False
        account = self.env['account.account'].search(
            [('code', '=', code.strip()),
             ('company_id', '=', self.env.company.id)], limit=1)
        if not account:
            _logger.warning(f"[MAPPER] Compte introuvable: {code}")
        return account.id if account else False

    def _get_journal(self, code):
        if code:
            journal = self.env['account.journal'].search(
                [('code', '=', code.strip())], limit=1)
            if journal:
                return journal.id
        # Fallback: journal des OD
        journal = self.env['account.journal'].search(
            [('type', '=', 'general')], limit=1)
        return journal.id if journal else False

    def _parse_date(self, x3_date):
        from odoo import fields
        if not x3_date:
            return fields.Date.today()
        try:
            x3_date = str(x3_date).strip()
            if len(x3_date) == 8 and x3_date.isdigit():
                return f"{x3_date[:4]}-{x3_date[4:6]}-{x3_date[6:8]}"
            if '/' in x3_date:
                p = x3_date.split('/')
                return f"{p[2]}-{p[1]}-{p[0]}"
            return x3_date
        except Exception:
            from odoo import fields
            return fields.Date.today()
