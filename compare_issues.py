import os
import pandas as pd

# Dosya isimleri
CSV_FOLDER = "csv_folder"
LATEST_FILE = os.path.join(CSV_FOLDER, "jira_latest.csv")   
UPLOADED_FILE = os.path.join(CSV_FOLDER, "jira_uploaded.csv")  
TO_ADD_FILE = os.path.join(CSV_FOLDER, "jira_to_add.csv")    

def compare_issues():
    # UPLOADED_FILE yoksa oluştur
    if not os.path.exists(UPLOADED_FILE):
        pd.DataFrame(columns=["Issue key"]).to_csv(UPLOADED_FILE, index=False)
        print(f"'{UPLOADED_FILE}' oluşturuldu (boş).")

    # TO_ADD_FILE yoksa oluştur
    if not os.path.exists(TO_ADD_FILE):
        pd.DataFrame(columns=["Issue key"]).to_csv(TO_ADD_FILE, index=False)
        print(f"'{TO_ADD_FILE}' oluşturuldu (boş).")

    # CSV dosyalarını oku
    if os.path.exists(LATEST_FILE) and os.path.getsize(LATEST_FILE) > 0:
        latest_df = pd.read_csv(LATEST_FILE, encoding="utf-8-sig")
    else:
        latest_df = pd.DataFrame(columns=["Issue key"])

    if os.path.exists(UPLOADED_FILE) and os.path.getsize(UPLOADED_FILE) > 0:
        uploaded_df = pd.read_csv(UPLOADED_FILE, encoding="utf-8-sig")
    else:
        uploaded_df = pd.DataFrame(columns=["Issue key"])

    # Karşılaştırma
    if not uploaded_df.empty:
        to_add_df = latest_df[~latest_df['Issue key'].isin(uploaded_df['Issue key'])]
    else:
        to_add_df = latest_df.copy()

    # TO_ADD_FILE olarak kaydet
    to_add_df.to_csv(TO_ADD_FILE, index=False, encoding="utf-8-sig")
    print(f"{len(to_add_df)} yeni issue '{TO_ADD_FILE}' dosyasına eklendi.")
