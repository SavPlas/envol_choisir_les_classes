import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from collections import Counter
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import tempfile
import os # Ajouté pour supprimer les fichiers temporaires
import pytz # Gardé pour la gestion du fuseau horaire

# === CONFIGURATION ===
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Dossier ID où tu souhaites enregistrer le fichier sur Google Drive
# Ce FOLDER_ID peut aussi être mis dans st.secrets si vous voulez le rendre configurable
FOLDER_ID = "1uKc0nx4XxvNQG3IdY-icz8gti5iPIg6U" # À adapter si besoin, ou le lire depuis st.secrets

# Colonnes à garder (ajustez cette liste si elle est spécifique à ce projet)
COLONNES_UTILISEES = [
    "Classe", "Classe Groupe", "Nom", "Prénom", "Date De Naissance", "Nom / Prénom de l'élève", "Genre",
    "PersonneID", "Responsable 1 Nom", "Responsable 1 Prénom", "Responsable 1 Titre", "Responsable 1 Rue",
    "Responsable 1 Numéro", "Responsable1_BP", "Responsable 1 Localité", "Responsable 1 CP"
]

# === FONCTIONS UTILITAIRES ===

def extract_sheet_id(url):
    """Extraire l'ID du Google Sheet à partir de son URL"""
    if "/d/" in url:
        return url.split("/d/")[1].split("/")[0]
    return None

def make_headers_unique(headers):
    """Rendre les en-têtes uniques si nécessaire"""
    count = Counter()
    result = []
    for h in headers:
        h = h.strip()
        if count[h] == 0:
            result.append(h)
        else:
            result.append(f"{h}_{count[h]}")
        count[h] += 1
    return result

# --- Fonction d'authentification Google modifiée pour utiliser st.secrets ---
@st.cache_resource # Permet de ne charger les identifiants qu'une seule fois
def get_google_credentials():
    """
    Récupère les identifiants du compte de service Google depuis st.secrets
    et retourne un objet ServiceAccountCredentials (pour gspread) et les identifiants bruts (pour googleapiclient).
    """
    required_keys = [
        "type", "project_id", "private_key_id", "private_key",
        "client_email", "client_id", "auth_uri", "token_uri",
        "auth_provider_x509_cert_url", "client_x509_cert_url",
        "universe_domain"
    ]

    creds_info = {}

    # Vérification de l'existence de la section des secrets Google
    if "google_service_account" not in st.secrets:
        st.error("Erreur de configuration : La section '[google_service_account]' est manquante dans vos secrets Streamlit. "
                 "Veuillez vous assurer que votre fichier secrets.toml sur Streamlit Cloud est correctement configuré.")
        st.stop() # Arrête l'application si les secrets ne sont pas trouvés

    # Récupération de chaque clé sous la section 'google_service_account'
    for key in required_keys:
        if key not in st.secrets["google_service_account"]:
            st.error(f"Erreur de configuration : La clé '{key}' est manquante "
                     f"dans la section '[google_service_account]' de vos secrets Streamlit.")
            st.stop()
        creds_info[key] = st.secrets["google_service_account"][key]

    try:
        # gspread utilise ServiceAccountCredentials
        gspread_creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, SCOPES)

        # googleapiclient.discovery.build utilise un objet Credentials directement
        # Le format de creds_info est déjà ce dont il a besoin, mais on va le convertir
        # en un objet google.oauth2.service_account.Credentials pour plus de clarté
        google_api_creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, SCOPES)

        return gspread_creds, google_api_creds
    except Exception as e:
        st.error(f"Erreur lors de la création des identifiants Google. "
                 f"Vérifiez le format de votre clé privée et l'ensemble des informations de votre compte de service. Détail : {e}")
        st.stop() # Arrête l'application en cas d'échec d'authentification

# --- Fonctions de chargement et création des feuilles de calcul ---

def charger_dataframe_depuis_google_sheet(url, gspread_client):
    """Charger les données depuis un Google Sheet"""
    sheet_id = extract_sheet_id(url)
    if not sheet_id:
        st.error("URL de Google Sheet invalide. Assurez-vous qu'elle contient '/d/'.")
        return None
    try:
        sheet = gspread_client.open_by_key(sheet_id).sheet1
        all_values = sheet.get_all_values()
        if not all_values:
            st.warning("La feuille est vide.")
            return pd.DataFrame()
        headers = make_headers_unique(all_values[0])
        data = all_values[1:]
        df = pd.DataFrame(data, columns=headers)
        return df
    except Exception as e:
        st.error(f"Erreur lors du chargement de la feuille : {e}. "
                 "Vérifiez que le compte de service a les permissions d'accès au Google Sheet.")
        return None

def get_drive_service(google_api_creds):
    """Retourne un service Google Drive authentifié"""
    return build('drive', 'v3', credentials=google_api_creds)

def create_spreadsheet_with_data(title, df_filtered, google_api_creds, folder_id=FOLDER_ID):
    """Créer une feuille de calcul Google Sheets avec les données filtrées"""
    temp_file_path = None # Initialiser à None
    try:
        # Créer un fichier CSV temporaire
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='w', encoding='utf-8') as temp_file:
            df_filtered.to_csv(temp_file.name, index=False)
            temp_file_path = temp_file.name # Garder le chemin pour MediaFileUpload

        metadata = {
            'name': title,
            'mimeType': 'application/vnd.google-apps.spreadsheet', # Type MIME pour Google Sheets
            'parents': [folder_id]
        }

        media = MediaFileUpload(temp_file_path, mimetype='text/csv', resumable=True)
        drive_service = get_drive_service(google_api_creds)

        file = drive_service.files().create(body=metadata, media_body=media, fields='id').execute()

        return file.get("id")

    except Exception as e:
        st.error(f"Erreur lors de la création de la feuille Google Sheets : {e}. "
                 "Vérifiez que le compte de service a les permissions d'écriture dans le dossier Drive spécifié.")
        return None
    finally:
        # Supprimer le fichier temporaire après l'upload, même en cas d'erreur
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

def get_classes(dataframe):
    """Extraire les classes uniques du DataFrame"""
    # Assurez-vous que la colonne 'Classe' existe avant d'essayer d'y accéder
    if 'Classe' in dataframe.columns:
        return sorted(dataframe['Classe'].unique().tolist()) # Retourne une liste triée
    else:
        st.warning("La colonne 'Classe' est manquante dans votre Google Sheet. Impossible de filtrer par classe.")
        return []

def filter_data_by_class(dataframe, selected_classes):
    """Filtrer les données selon les classes sélectionnées"""
    if 'Classe' in dataframe.columns and selected_classes:
        return dataframe[dataframe['Classe'].isin(selected_classes)]
    return pd.DataFrame() # Retourne un DataFrame vide si pas de classe ou pas de sélection

# === Interface Streamlit ===
st.set_page_config(
    page_title="ENVOL : Choix des classes",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="auto"
)

st.title("ENVOL : choix des classes")
st.markdown("---")

st.info("Cette application charge les données d'un Google Sheet, vous permet de filtrer par classe, "
        "puis exporte les données filtrées vers un nouveau Google Sheet dans un dossier Drive spécifié. "
        "Les identifiants Google sont gérés de manière sécurisée via les secrets Streamlit.")

# Récupération des identifiants au démarrage de l'application (utilisant st.secrets)
gspread_creds, google_api_creds = get_google_credentials()
client = gspread.authorize(gspread_creds) # Initialisation du client gspread

url_sheet = st.text_input("🔗 Veuillez coller l'URL du fichier Google Sheet à traiter : ")

if url_sheet:
    st.info("📥 Chargement du fichier Google Sheet...")
    df = charger_dataframe_depuis_google_sheet(url_sheet, client)

    if df is not None and not df.empty:
        classes = get_classes(df)
        
        if classes: # S'il y a des classes à sélectionner
            selected_classes = st.multiselect("Sélectionnez les classes à exporter :", classes)

            if selected_classes:
                filtered_df = filter_data_by_class(df, selected_classes)
                
                if not filtered_df.empty:
                    st.success(f"✅ {len(filtered_df)} élèves sélectionnés.")
                    st.dataframe(filtered_df.head()) # Aperçu des données

                    nom_utilisateur = st.text_input("📝 Entrez un nom pour le fichier généré : ")
                    if nom_utilisateur:
                        if st.button("Créer le Google Sheet avec les données filtrées"):
                            with st.spinner("Création du Google Sheet en cours..."):
                                # Utiliser pytz pour ajuster le fuseau horaire
                                # J'ai mis 'Europe/Brussels' car c'est le fuseau horaire pour Mons
                                fuseau_horaire_local = pytz.timezone('Europe/Brussels')
                                timestamp = pd.to_datetime("now", utc=True).tz_convert(fuseau_horaire_local).strftime("%Y-%m-%d_%Hh%M")

                                # Générer le nom du fichier avec la date et l'heure locale
                                nouveau_nom = f"{nom_utilisateur} - {timestamp}"
                                st.info(f"📝 Nom du fichier final : {nouveau_nom}")

                                file_id = create_spreadsheet_with_data(nouveau_nom, filtered_df, google_api_creds)

                                if file_id:
                                    st.success(f"✅ Nouveau fichier créé : [Ouvrir le fichier]({f'https://docs.google.com/spreadsheets/d/{file_id}'})")
                                    st.info(f"📁 Fichier enregistré dans le dossier Google Drive ID : {FOLDER_ID}")
                                else:
                                    st.error("❌ La création du fichier Google Sheet a échoué.")
                    else:
                        st.warning("Veuillez entrer un nom pour le fichier généré avant de continuer.")
                else:
                    st.warning("Aucun élève trouvé pour les classes sélectionnées. Veuillez ajuster votre sélection ou vérifier les données source.")
            else:
                st.info("Sélectionnez une ou plusieurs classes pour filtrer les données.")
        else:
            st.warning("Aucune classe disponible pour la sélection. Vérifiez que la colonne 'Classe' existe et contient des données dans votre Google Sheet.")
    else:
        st.warning("Impossible de charger les données du Google Sheet ou le Google Sheet est vide. Veuillez vérifier l'URL et les permissions.")
else:
    st.info("Veuillez coller l'URL de votre Google Sheet ci-dessus pour commencer.")

st.markdown("---")
st.markdown("Développé avec ❤️ pour ENVOL via Streamlit et Google APIs")
