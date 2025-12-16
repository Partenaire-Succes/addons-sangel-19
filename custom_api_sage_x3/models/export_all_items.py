import requests
import json
import csv
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================
BASE_URL = "http://172.16.2.150:8030"
AUTH_URL = f"{BASE_URL}/api/Auth/login"
ITEMS_URL = f"{BASE_URL}/api/Items"
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


def get_all_items(token):
    """
    Récupère tous les articles depuis l'API avec pagination
    
    Args:
        token: Token JWT d'authentification
        
    Returns:
        Liste de tous les articles
    """
    print("📦 Récupération de tous les articles...")
    print(f"{'='*80}\n")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    all_items = []
    page = 1
    
    while True:
        try:
            params = {"pageNumber": page, "pageSize": PAGE_SIZE}
            response = requests.get(ITEMS_URL, headers=headers, params=params, timeout=TIMEOUT)
            
            if response.status_code != 200:
                print(f"❌ Erreur HTTP {response.status_code} à la page {page}")
                break
            
            data = response.json()
            items = data.get("items", [])
            
            if not items:
                print(f"⚠️ Aucun article trouvé à la page {page}")
                break
            
            all_items.extend(items)
            total_count = data.get("totalCount", 0)
            print(f"📄 Page {page} : {len(items)} articles récupérés (Total: {len(all_items)}/{total_count})")
            
            # Vérifier s'il y a une page suivante
            if not data.get("hasNextPage", False):
                print(f"\n✅ Récupération terminée : {len(all_items)} articles au total")
                break
            
            page += 1
            
        except Exception as e:
            print(f"❌ Erreur à la page {page} : {e}")
            break
    
    return all_items


def export_to_json(items, filename=None):
    """
    Exporte les articles en JSON
    
    Args:
        items: Liste des articles
        filename: Nom du fichier (auto-généré si None)
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"articles_sage_x3_{timestamp}.json"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Export JSON réussi : {filename}")
        print(f"   📊 Nombre d'articles : {len(items)}")
        return filename
    except Exception as e:
        print(f"❌ Erreur lors de l'export JSON : {e}")
        return None


def export_to_csv(items, filename=None):
    """
    Exporte les articles en CSV
    
    Args:
        items: Liste des articles
        filename: Nom du fichier (auto-généré si None)
    """
    if not items:
        print("⚠️ Aucun article à exporter")
        return None
    
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"articles_sage_x3_{timestamp}.csv"
    
    try:
        # Récupérer toutes les clés possibles
        all_keys = set()
        for item in items:
            all_keys.update(item.keys())
        
        fieldnames = sorted(all_keys)
        
        with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            writer.writerows(items)
        
        print(f"\n💾 Export CSV réussi : {filename}")
        print(f"   📊 Nombre d'articles : {len(items)}")
        print(f"   📋 Nombre de colonnes : {len(fieldnames)}")
        return filename
    except Exception as e:
        print(f"❌ Erreur lors de l'export CSV : {e}")
        return None


def display_summary(items):
    """Affiche un résumé des articles récupérés"""
    if not items:
        print("⚠️ Aucun article à afficher")
        return
    
    print(f"\n{'='*80}")
    print(f"📊 RÉSUMÉ DES ARTICLES")
    print(f"{'='*80}")
    print(f"   Nombre total d'articles : {len(items)}")
    
    # Afficher les 5 premiers articles
    print(f"\n   📦 Aperçu des 5 premiers articles :")
    print(f"   {'-'*76}")
    
    for idx, item in enumerate(items[:5], start=1):
        ref = item.get('itmreF_0', 'N/A')
        name = item.get('itmdeS1_0', 'N/A')
        price = item.get('basprI_0', 0)
        print(f"   {idx}. [{ref}] {name} - Prix: {price} XOF")
    
    if len(items) > 5:
        print(f"   ... et {len(items) - 5} autres articles")
    
    print(f"   {'-'*76}")
    print(f"{'='*80}\n")


def main():
    """Fonction principale"""
    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║        📦 EXPORT DE TOUS LES ARTICLES SAGE X3                        ║
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
    
    # Récupération de tous les articles
    items = get_all_items(token)
    
    if not items:
        print("⚠️ Aucun article récupéré")
        return
    
    # Afficher le résumé
    display_summary(items)
    
    # Demander le format d'export
    print("📝 Format d'export :")
    print("   1. JSON")
    print("   2. CSV")
    print("   3. Les deux")
    
    choice = input("\n👉 Votre choix (1, 2 ou 3) : ").strip()
    
    if choice == "1":
        export_to_json(items)
    elif choice == "2":
        export_to_csv(items)
    elif choice == "3":
        export_to_json(items)
        export_to_csv(items)
    else:
        print("⚠️ Choix invalide, export JSON par défaut")
        export_to_json(items)
    
    print("\n✅ Traitement terminé !")


if __name__ == "__main__":
    main()