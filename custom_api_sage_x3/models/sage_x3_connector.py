"""
Module de connexion centralisé pour l'API SAGE X3
"""
import requests
import logging
import time

_logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "http://172.16.2.150:8030"
AUTH_URL = f"{BASE_URL}/api/Auth/login"
USERNAME = "odoo"
PASSWORD = "InterfaceX3_Odoo"

# Endpoints
ITEMS_URL = f"{BASE_URL}/api/Items"
CUSTOMERS_URL = f"{BASE_URL}/api/Customers"
ORDERS_SEND_URL = f"{BASE_URL}/api/Orders/batch"
ORDERS_RECEIVE_URL = f"{BASE_URL}/api/Orders/deliveries"
ACCOUNTING_ENTRIES_URL = f"{BASE_URL}/api/Accounting/entries/batch"

# Paramètres
TIMEOUT = 30
MAX_RETRIES = 3


class SageX3Connector:
    """Gestionnaire de connexion SAGE X3"""
    
    def __init__(self):
        self._token = None
        self._token_expiry = None
    
    def authenticate(self):
        """
        Authentification auprès de SAGE X3
        
        Returns:
            str: Token JWT ou None si échec
        """
        try:
            auth_data = {"username": USERNAME, "password": PASSWORD}
            response = requests.post(AUTH_URL, json=auth_data, timeout=15)
            
            if response.status_code in (200, 201):
                data = response.json()
                self._token = data.get("token")
                _logger.info("✅ Authentification SAGE X3 réussie")
                return self._token
            else:
                _logger.error("❌ Authentification échouée: HTTP %s - %s", 
                            response.status_code, response.text)
                return None
                
        except Exception as e:
            _logger.exception("❌ Exception authentification: %s", str(e))
            return None
    
    def get_headers(self):
        """
        Retourne les headers avec le token d'authentification
        
        Returns:
            dict: Headers HTTP
        """
        if not self._token:
            self.authenticate()
        
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def safe_get(self, url, params=None, timeout=TIMEOUT):
        """
        Appel GET avec retry et authentification automatique
        
        Args:
            url: URL de l'endpoint
            params: Paramètres GET (optionnel)
            timeout: Timeout en secondes
            
        Returns:
            requests.Response: Réponse HTTP
        """
        headers = self.get_headers()
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
                
                # Si token expiré, réauthentifier
                if response.status_code == 401:
                    _logger.warning("⚠️ Token expiré, réauthentification...")
                    self.authenticate()
                    headers = self.get_headers()
                    response = requests.get(url, headers=headers, params=params, timeout=timeout)
                
                if response.status_code in (200, 201):
                    return response
                    
                _logger.warning("⚠️ Tentative %s échouée: HTTP %s", 
                              attempt, response.status_code)
                
            except requests.exceptions.RequestException as e:
                _logger.warning("⚠️ Exception réseau (tentative %s): %s", attempt, str(e))
            
            if attempt < MAX_RETRIES:
                time.sleep(2)
        
        # Dernière tentative sans retry
        return requests.get(url, headers=headers, params=params, timeout=timeout)
    
    def safe_post(self, url, data, timeout=TIMEOUT):
        """
        Appel POST avec retry et authentification automatique
        
        Args:
            url: URL de l'endpoint
            data: Données JSON à envoyer
            timeout: Timeout en secondes
            
        Returns:
            requests.Response: Réponse HTTP
        """
        headers = self.get_headers()
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
                
                # Si token expiré, réauthentifier
                if response.status_code == 401:
                    _logger.warning("⚠️ Token expiré, réauthentification...")
                    self.authenticate()
                    headers = self.get_headers()
                    response = requests.post(url, headers=headers, json=data, timeout=timeout)
                
                if response.status_code in (200, 201):
                    return response
                    
                _logger.warning("⚠️ Tentative %s échouée: HTTP %s - %s", 
                              attempt, response.status_code, response.text)
                
            except requests.exceptions.RequestException as e:
                _logger.warning("⚠️ Exception réseau (tentative %s): %s", attempt, str(e))
            
            if attempt < MAX_RETRIES:
                time.sleep(2)
        
        # Dernière tentative sans retry
        return requests.post(url, headers=headers, json=data, timeout=timeout)


# Instance globale du connecteur
_connector = None

def get_connector():
    """
    Retourne l'instance unique du connecteur SAGE X3
    
    Returns:
        SageX3Connector: Instance du connecteur
    """
    global _connector
    if _connector is None:
        _connector = SageX3Connector()
    return _connector