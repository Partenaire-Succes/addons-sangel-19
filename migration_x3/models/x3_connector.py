# -*- coding: utf-8 -*-
import logging
import requests
from requests.auth import HTTPBasicAuth
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_logger = logging.getLogger(__name__)

X3_ENDPOINTS = {
    'plan_comptable':   'GACCOUN',
    'clients':          'BPCUSTOMER',
    'fournisseurs':     'BPSUPPLIER',
    'tiers':            'BPARTNER',
    'ecritures':        'GACCENTRY',
    'factures_ventes':  'SINVOICE',
    'factures_achats':  'PINVOICE',
    'balance':          'GBALANCE',
    'immobilisations':  'GASSET',
    'journaux':         'GJOURNAL',
    'devises':          'TABCUR',
    'taxes':            'TAXRAT',
}

X3_FIELDS = {
    'plan_comptable': ['ACC', 'DES', 'ACCTYP', 'CURTYP', 'ACCCLS'],
    'clients': [
        'BPCNUM', 'BPCNAM', 'CRY', 'CUR', 'PTE',
        'BPAADDRESS', 'TEL', 'WEB', 'ACCCUS',
    ],
    'fournisseurs': [
        'BPSNUM', 'BPSNAM', 'CRY', 'CUR', 'PTE',
        'BPAADDRESS', 'TEL', 'ACCSUP',
    ],
    'ecritures': [
        'NUM', 'JOU', 'ACCDAT', 'ACC', 'SNS',
        'AMTCUR', 'AMTLOC', 'CUR', 'DES', 'BPRNUM', 'DUDDAT',
    ],
    'factures_ventes': [
        'NUM', 'BPCNUM', 'INVDAT', 'INVDUDDAT',
        'AMTNOTAXCUR', 'AMTTAXCUR', 'CUR', 'STA',
    ],
    'factures_achats': [
        'NUM', 'BPSNUM', 'ACCDAT', 'INVDUDDAT',
        'AMTNOTAXCUR', 'AMTTAXCUR', 'CUR', 'STA',
    ],
}


class SageX3Connector:
    """
    Connecteur SData pour Sage X3.
    Classe Python pure — instanciée dans les wizards/models Odoo.

    Usage:
        connector = SageX3Connector(config_record)
        data = connector.get_plan_comptable()
    """

    def __init__(self, config):
        self.config = config
        self.base_url = self._build_base_url()
        self.session = self._build_session()

    def _build_base_url(self):
        url = self.config.server_url.rstrip('/')
        if self.config.port not in (80, 443):
            url = f"{url}:{self.config.port}"
        return f"{url}/sdata/{self.config.pool}/{self.config.dossier}"

    def _build_session(self):
        session = requests.Session()
        session.auth = HTTPBasicAuth(self.config.username, self.config.password)
        session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })
        session.verify = self.config.verify_ssl
        return session

    def fetch(self, endpoint, filters=None, fields=None, top=1000, all_pages=False):
        """Requête générique SData avec pagination automatique."""
        url = f"{self.base_url}/{endpoint}"
        params = {'$top': top, '$skip': 0}
        if filters:
            params['$filter'] = filters
        if fields:
            params['$select'] = ','.join(fields)

        all_results = []
        while True:
            try:
                _logger.info(f"[X3] GET {url} params={params}")
                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                resources = resp.json().get('$resources', [])
                all_results.extend(resources)
                _logger.info(f"[X3] +{len(resources)} records (total: {len(all_results)})")
                if all_pages and len(resources) == top:
                    params['$skip'] += top
                else:
                    break
            except requests.exceptions.RequestException as e:
                raise ConnectionError(f"Erreur API X3 ({endpoint}): {e}")

        return all_results

    def get_plan_comptable(self):
        return self.fetch(X3_ENDPOINTS['plan_comptable'],
                          fields=X3_FIELDS['plan_comptable'], all_pages=True)

    def get_clients(self):
        return self.fetch(X3_ENDPOINTS['clients'],
                          fields=X3_FIELDS['clients'], all_pages=True)

    def get_fournisseurs(self):
        return self.fetch(X3_ENDPOINTS['fournisseurs'],
                          fields=X3_FIELDS['fournisseurs'], all_pages=True)

    def get_ecritures(self, date_debut=None, date_fin=None):
        filters = None
        if date_debut and date_fin:
            filters = f"ACCDAT ge '{date_debut}' and ACCDAT le '{date_fin}'"
        elif date_debut:
            filters = f"ACCDAT ge '{date_debut}'"
        return self.fetch(X3_ENDPOINTS['ecritures'],
                          filters=filters, fields=X3_FIELDS['ecritures'], all_pages=True)

    def get_factures_ventes(self, statut='ALL'):
        filters = "STA eq '2'" if statut == 'OPEN' else None
        return self.fetch(X3_ENDPOINTS['factures_ventes'],
                          filters=filters, fields=X3_FIELDS['factures_ventes'], all_pages=True)

    def get_factures_achats(self, statut='ALL'):
        filters = "STA eq '2'" if statut == 'OPEN' else None
        return self.fetch(X3_ENDPOINTS['factures_achats'],
                          filters=filters, fields=X3_FIELDS['factures_achats'], all_pages=True)

    def get_preview(self, objet, limit=10):
        endpoint = X3_ENDPOINTS.get(objet)
        if not endpoint:
            raise ValueError(f"Objet X3 inconnu: {objet}")
        return self.fetch(endpoint, top=limit)
