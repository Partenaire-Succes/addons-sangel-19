import requests
import json
import csv
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================
BASE_URL = "http://172.16.2.150:8030"
AUTH_URL = f"{BASE_URL}/api/Auth/login"
CUSTOMERS_URL = f"{BASE_URL}/api/Customers"
USERNAME = "odoo"
PASSWORD = "InterfaceX3_Odoo"

PAGE_SIZE = 100
TIMEOUT = 30


def authenticate():
    """Authentification et récupération du token JWT"""
    print("🔐 Authentification en cours...")
    try:
        auth_data = {"username": USERNAME, "password": PASSWORD}
        response = requests.post(AUTH_URL, json=auth_data, timeout=15)
        
        if response.status_code in (200, 201):
            token = response.json().get("token")
            print("✅ Authentification réussie\n")
            return token
        else:
            print(f"❌ Erreur d'authentification : {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Exception lors de l'authentification : {e}")
        return None


def get_all_contacts(token):
    """
    Récupère tous les contacts depuis l'API avec pagination
    
    Args:
        token: Token JWT d'authentification
        
    Returns:
        Liste de tous les contacts
    """
    print("👥 Récupération de tous les contacts...")
    print(f"{'='*80}\n")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    all_contacts = []
    page = 1
    
    while True:
        try:
            params = {"pageNumber": page, "pageSize": PAGE_SIZE}
            response = requests.get(CUSTOMERS_URL, headers=headers, params=params, timeout=TIMEOUT)
            
            if response.status_code != 200:
                print(f"❌ Erreur HTTP {response.status_code} à la page {page}")
                break
            
            data = response.json()
            contacts = data.get("items", [])
            
            if not contacts:
                print(f"⚠️ Aucun contact trouvé à la page {page}")
                break
            
            all_contacts.extend(contacts)
            total_count = data.get("totalCount", 0)
            print(f"📄 Page {page} : {len(contacts)} contacts récupérés (Total: {len(all_contacts)}/{total_count})")
            
            # Vérifier s'il y a une page suivante
            if not data.get("hasNextPage", False):
                print(f"\n✅ Récupération terminée : {len(all_contacts)} contacts au total")
                break
            
            page += 1
            
        except Exception as e:
            print(f"❌ Erreur à la page {page} : {e}")
            break
    
    return all_contacts


def export_to_json(contacts, filename=None):
    """
    Exporte les contacts en JSON
    
    Args:
        contacts: Liste des contacts
        filename: Nom du fichier (auto-généré si None)
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"contacts_sage_x3_{timestamp}.json"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(contacts, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Export JSON réussi : {filename}")
        print(f"   📊 Nombre de contacts : {len(contacts)}")
        return filename
    except Exception as e:
        print(f"❌ Erreur lors de l'export JSON : {e}")
        return None


def export_to_csv(contacts, filename=None):
    """
    Exporte les contacts en CSV
    
    Args:
        contacts: Liste des contacts
        filename: Nom du fichier (auto-généré si None)
    """
    if not contacts:
        print("⚠️ Aucun contact à exporter")
        return None
    
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"contacts_sage_x3_{timestamp}.csv"
    
    try:
        # Récupérer toutes les clés possibles
        all_keys = set()
        for contact in contacts:
            all_keys.update(contact.keys())
        
        fieldnames = sorted(all_keys)
        
        with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            writer.writerows(contacts)
        
        print(f"\n💾 Export CSV réussi : {filename}")
        print(f"   📊 Nombre de contacts : {len(contacts)}")
        print(f"   📋 Nombre de colonnes : {len(fieldnames)}")
        return filename
    except Exception as e:
        print(f"❌ Erreur lors de l'export CSV : {e}")
        return None


def display_summary(contacts):
    """Affiche un résumé des contacts récupérés"""
    if not contacts:
        print("⚠️ Aucun contact à afficher")
        return
    
    print(f"\n{'='*80}")
    print(f"📊 RÉSUMÉ DES CONTACTS")
    print(f"{'='*80}")
    print(f"   Nombre total de contacts : {len(contacts)}")
    
    # Afficher les 5 premiers contacts
    print(f"\n   👥 Aperçu des 5 premiers contacts :")
    print(f"   {'-'*76}")
    
    for idx, contact in enumerate(contacts[:5], start=1):
        code = contact.get('bpcnuM_0', 'N/A')
        name = contact.get('bprnaM_0', 'N/A')
        city = contact.get('ctY_0', 'N/A')
        phone = contact.get('teL_0', 'N/A')
        print(f"   {idx}. [{code}] {name}")
        print(f"      📍 {city} | 📞 {phone}")
    
    if len(contacts) > 5:
        print(f"\n   ... et {len(contacts) - 5} autres contacts")
    
    print(f"   {'-'*76}")
    print(f"{'='*80}\n")


def main():
    """Fonction principale"""
    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║        👥 EXPORT DE TOUS LES CONTACTS SAGE X3                        ║
║                                                                       ║
║        Interface API : InterfaceX3 API v1                            ║
║        Endpoint : http://172.16.2.150:8030                           ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
    """)
    
    # Authentification
    token = authenticate()
    if not token:
        print("❌ Impossible de continuer sans authentification")
        return
    
    # Récupération de tous les contacts
    contacts = get_all_contacts(token)
    
    if not contacts:
        print("⚠️ Aucun contact récupéré")
        return
    
    # Afficher le résumé
    display_summary(contacts)
    
    # Demander le format d'export
    print("📝 Format d'export :")
    print("   1. JSON")
    print("   2. CSV")
    print("   3. Les deux")
    
    choice = input("\n👉 Votre choix (1, 2 ou 3) : ").strip()
    
    if choice == "1":
        export_to_json(contacts)
    elif choice == "2":
        export_to_csv(contacts)
    elif choice == "3":
        export_to_json(contacts)
        export_to_csv(contacts)
    else:
        print("⚠️ Choix invalide, export JSON par défaut")
        export_to_json(contacts)
    
    print("\n✅ Traitement terminé !")


if __name__ == "__main__":
    main()