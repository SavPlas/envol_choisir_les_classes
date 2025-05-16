import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from googleapiclient.discovery import build

# Authentification Google Sheets et Drive
def get_credentials():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        'C:\\Users\\savery.plasman\\Envol CLASSE\\credentials.json',
        scope
    )
    return creds

# Lire les données depuis le Google Sheet
def get_sheet_data(sheet_url):
    creds = get_credentials()
    client = gspread.authorize(creds)
    sheet = client.open_by_url(sheet_url)
    worksheet = sheet.get_worksheet(0)
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

# Extraire les classes
def get_classes(dataframe):
    return dataframe['Classe'].unique()

# Filtrer les élèves selon la ou les classes
def filter_data_by_class(dataframe, selected_classes):
    return dataframe[dataframe['Classe'].isin(selected_classes)]

# Créer un nouveau fichier Sheet et le déplacer dans le bon dossier
def create_new_sheet(dataframe, filename, folder_id):
    creds = get_credentials()
    client = gspread.authorize(creds)
    
    new_sheet = client.create(filename)
    worksheet = new_sheet.get_worksheet(0)
    worksheet.update([dataframe.columns.values.tolist()] + dataframe.values.tolist())

    # Récupérer l'ID du fichier nouvellement créé
    file_id = new_sheet.id

    # Déplacer le fichier dans le bon dossier Drive
    service = build('drive', 'v3', credentials=creds)
    file = service.files().get(fileId=file_id, fields='parents').execute()
    previous_parents = ",".join(file.get('parents'))
    service.files().update(
        fileId=file_id,
        addParents=folder_id,
        removeParents=previous_parents,
        fields='id, parents'
    ).execute()

# ---- Programme principal ----
if __name__ == '__main__':
    # URL du fichier source
    sheet_url = "https://docs.google.com/spreadsheets/d/1grfqH0rYRTRoE32OjUoh5pVCT9XWCXvEkRHU4KC2qVs/edit?usp=sharing"

    # ID du dossier Google Drive cible
    folder_id = "1uKc0nx4XxvNQG3IdY-icz8gti5iPIg6U"

    # Charger les données
    df = get_sheet_data(sheet_url)

    # Liste des classes
    classes = get_classes(df)
    print("Classes disponibles :")
    for idx, cls in enumerate(classes):
        print(f"{idx + 1}. {cls}")

    # Sélection par l'utilisateur
    selection = input("Entrez les numéros des classes à sélectionner (séparés par des virgules) : ")
    selected_classes = [classes[int(i.strip()) - 1] for i in selection.split(',')]

    # Filtrer les données
    filtered_df = filter_data_by_class(df, selected_classes)

    # Nom du fichier à créer
    base_name = input("Entrez le nom du fichier (sans extension) : ")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    final_name = f"{base_name}_{timestamp}"

    # Création du fichier
    create_new_sheet(filtered_df, final_name, folder_id)

    print(f"✅ Nouveau fichier créé : {final_name} dans le dossier Google Drive.")
