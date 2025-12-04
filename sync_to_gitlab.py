import csv
import requests
import pandas as pd
import os
from dateutil import parser
from dotenv import load_dotenv
from jira_auto_export import fetch_jira_csv
from compare_issues import compare_issues
import sys
import json
from urllib.parse import quote
from requests.auth import HTTPBasicAuth

# .env dosyasını yükle
load_dotenv()

# --- .ENV DEĞİŞKENLERİ ---
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
MASTER_PROJECT_ID = os.getenv("MASTER_PROJECT_ID")
TEAM_PROJECT_MAP = json.loads(os.getenv("TEAM_PROJECT_MAP", "{}"))
GROUP_ID = os.getenv("GROUP_ID")  # Yeni: milestone'lar burada açılacak
JIRA_URL = os.getenv("JIRA_URL")  # Örn: http://10.0.38.254
JIRA_EMAIL = os.getenv("JIRA_EMAIL")  # Jira kullanıcı adı
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")  # Şifre veya API token
JQL = "project = GYT AND created >= -2d"
CSV_FILE = "jira_export_all.csv"


HEADERS = {
    "PRIVATE-TOKEN": GITLAB_TOKEN,
    "Content-Type": "application/json"
}

# --- Jira'da Assignee yapılan birini Gitlab'de de atamak için
ASSIGNEE_MAP = {
    "merve.yucetas": 31250282,
    "affan.bugra.ozaytas": 31073378,
    "burak.kiraz": 31073379,
}

# --- İlgili takımları projeler ile eşleştirmek için. Şimdilik ilgili stajyereler paremetresi kullanılıyor.
STAJYER_PROJECT_MAP = {
    "affan.bugra.ozaytas": TEAM_PROJECT_MAP.get("GYT Test ve Otomasyon"),
    "merve.yucetas": TEAM_PROJECT_MAP.get("GYT Proje Yönetimi"),
    "burak.kiraz": TEAM_PROJECT_MAP.get("GYT Simülasyon")
}

# ------------------- CSV DOSYA İSİMLERİ -------------------

CSV_FOLDER = "csv_folder"
TO_ADD_FILE = os.path.join(CSV_FOLDER, "jira_to_add.csv")
UPLOADED_FILE = os.path.join(CSV_FOLDER, "jira_uploaded.csv")
LATEST_FILE = os.path.join(CSV_FOLDER, "jira_latest.csv")


  
# ------------------- ROBUST CSV OKUYUCU -------------------
def read_jira_csv_robustly(filename):
    issues = []
    try:
        with open(filename, encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = [h.strip() for h in next(reader)]
            stajyer_indices = [i for i, col_name in enumerate(header) if "İlgili Stajyerler" in col_name]

            for row_data in reader:
                issue = {}
                stajyer_list_raw = []
                for idx in stajyer_indices:
                    if idx < len(row_data):
                        val = row_data[idx].strip()
                        if val:
                            stajyer_list_raw.extend([s.strip() for s in val.split(",") if s.strip()])
                for h, v in zip(header, row_data):
                    issue[h.strip()] = v.strip()
                issues.append(issue)
    except FileNotFoundError:
        print(f"❌ Hata: '{filename}' dosyası bulunamadı.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Hata: CSV okunamadı. Hata: {e}")
        sys.exit(1)
    return issues

# ------------------- TEMİZLİK VE YARDIMCI FONKSİYONLAR -------------------
def parse_date(date_str):
    if not date_str:
        return None
    try:
        return parser.parse(date_str).strftime("%Y-%m-%d")
    except Exception:
        return None

def seconds_to_gitlab_duration(seconds):
    if seconds is None or seconds == "":
        return None
    try:
        sec = int(float(seconds))
    except Exception:
        return None
    if sec <= 0:
        return None
    hours = sec // 3600
    minutes = (sec % 3600) // 60
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "0m"

def link_issues(parent_project_id, parent_iid, target_project_id, target_iid):
    url = f"https://gitlab.com/api/v4/projects/{parent_project_id}/issues/{parent_iid}/links"
    data = {
        "target_project_id": target_project_id,
        "target_issue_iid": target_iid,
        "link_type": "relates_to"
    }
    r = requests.post(url, headers=HEADERS, json=data)
    if r.status_code not in (200, 201, 409):
        print(f"⚠️ Link hatası ({r.status_code}): {r.text}")

def find_or_create_group_milestone(title):
    url = f"https://gitlab.com/api/v4/groups/{GROUP_ID}/milestones"
    
    # Var mı kontrol et
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200:
        for m in r.json():
            if m["title"].strip().lower() == title.strip().lower():
                return m

    # Yoksa oluştur
    payload = {"title": title}
    r = requests.post(url, headers=HEADERS, json=payload)
    if r.status_code == 201:
        print(f"✨ Issue Milestone'u oluşturuldu: {row.get('Summary')}")
        return r.json()
    else:
        print(f"⚠️ Group Milestone oluşturulamadı: {r.status_code} {r.text}")
        return None
# ------------------- Stajyer alanlarını test etmek için -------------------
# --- JIRA TEST REQUEST (hata yutmalı) ---
try:
    test_url = f"{JIRA_URL}/rest/api/2/issue/GYT-126"
    test_response = requests.get(
        test_url,
        headers={"Authorization": f"Bearer {JIRA_API_TOKEN}"}
    )
    if test_response.status_code == 200:
        print("[JIRA TEST REQUEST] Başarılı ✅")
    else:
        print(f"[JIRA TEST REQUEST] Uyarı: {test_response.status_code}")
except Exception as e:
    print(f"[JIRA TEST REQUEST] Hata yutuldu: {e}")



# ------------------- ANA İŞLEMLER -------------------
if __name__ == "__main__":
    fetch_jira_csv()
    compare_issues()
    rows = read_jira_csv_robustly(TO_ADD_FILE)  
    print(f"\nToplam {len(rows)} Jira kaydı okundu.")

    for i, row in enumerate(rows, start=1):
        title = (row.get("Summary") or "Untitled").strip()
        jira_key = row.get("Issue key") or ""
        print(f"\n--- {i}/{len(rows)}: İşleniyor {jira_key} - {title} --- \n")

        ilgili_stajyerler = row.get("İlgili Stajyerler", "").split(",")
        ilgili_stajyerler = [s.strip() for s in ilgili_stajyerler if s.strip()]
        print(f"➡️ Tespit Edilen Takımlar: {', '.join(ilgili_stajyerler) or 'Yok'}")

        orig_description = (row.get("Description") or "").strip()
        labels = [lbl for lbl in [jira_key, row.get("Priority")] if lbl]
        due_date = parse_date(row.get("Due Date"))
        original_estimate = seconds_to_gitlab_duration(row.get("Original Estimate"))
        time_spent = seconds_to_gitlab_duration(row.get("Time Spent"))

        time_summary = (
            f"**Jira Bilgileri**\n"
            f"- Orijinal Jira Key: {jira_key}\n\n"
            f"**Zaman Takibi**\n"
            f"- Orijinal Tahmin: {original_estimate or 'N/A'}\n"
            f"- Harcanan Zaman: {time_spent or 'N/A'}\n\n"
            f"**Tarihler:**\n"
            f"- Bitiş Tarihi: {due_date or 'N/A'}\n\n"
        )
        description = time_summary + "--- Orijinal Açıklama ---\n\n" + orig_description

        if row.get("Labels"):
            labels += [x.strip() for x in row["Labels"].split(",") if x.strip()]
        labels_str = ",".join(labels)

        # 🏷️ Group Milestone (Summary bazlı, tüm projelerde ortak)
        milestone = find_or_create_group_milestone(title)

        # --- Master Issue Oluşturma ---
        assignee_jira = row.get("Assignee")
        master_assignee_id = ASSIGNEE_MAP.get(assignee_jira)

        master_data = {
            "title": title,
            "description": description,
            "labels": labels_str,
            "time_estimate": original_estimate,
            "spent_time": time_spent,
        }
        if due_date:
            master_data["due_date"] = due_date
        if master_assignee_id:
            master_data["assignee_ids"] = [master_assignee_id]
        if milestone:
            master_data["milestone_id"] = milestone["id"]

        master_url = f"https://gitlab.com/api/v4/projects/{MASTER_PROJECT_ID}/issues"
        master_resp = requests.post(master_url, headers=HEADERS, json=master_data)

        if master_resp.status_code == 201:
            master_issue = master_resp.json()
            master_iid = master_issue["iid"]
            print(f"✅ Ana Issue Oluşturuldu: {row.get('Summary')}")
        else:
            print(f"⚠️ Master issue oluşturulamadı ({jira_key}): {master_resp.status_code} {master_resp.text}")
            continue

        # --- Child Issue'ları Oluşturma ve Linkleme ---
        for stajyer in ilgili_stajyerler:
            proj_id = STAJYER_PROJECT_MAP.get(stajyer)
            if not proj_id:
                print(f"⚠️ Stajyer '{stajyer}' için proje ID'si bulunamadı. Atlanyor.")
                continue

            child_assignee_id = ASSIGNEE_MAP.get(stajyer)
            child_description = (
                f"**Ana Issue:** Project {MASTER_PROJECT_ID}, IID {master_iid} ({master_issue['web_url']})\n\n"
                f"--- Orijinal Açıklama ---\n\n{orig_description}"
            )


            # Child issue başlığı için proje adını API'den al
            proj_info_url = f"https://gitlab.com/api/v4/projects/{proj_id}"
            proj_info_resp = requests.get(proj_info_url, headers=HEADERS)
            if proj_info_resp.status_code == 200:
                proj_name = proj_info_resp.json().get("name", "Unknown Project")
            else:
                proj_name = "Unknown Project"


            child_data = {
                "title": f"{title} ({proj_name})",
                "description": child_description,
                "labels": labels_str,
                "time_estimate": original_estimate,
                "spent_time": time_spent
            }
            if due_date:
                child_data["due_date"] = due_date
            if child_assignee_id:
                child_data["assignee_ids"] = [child_assignee_id]
            if milestone:
                child_data["milestone_id"] = milestone["id"]

            child_url = f"https://gitlab.com/api/v4/projects/{proj_id}/issues"
            child_resp = requests.post(child_url, headers=HEADERS, json=child_data)

            if child_resp.status_code == 201:
                child_issue = child_resp.json()
                child_iid = child_issue["iid"]
                link_issues(int(MASTER_PROJECT_ID), master_iid, proj_id, child_iid)
                print(f"  -> Child Issue Oluşturuldu: {child_data['title']} ve Ana Issue ile linklendi.")
            else:
                print(f"⚠️ Child issue oluşturulamadı (stajyer {stajyer}): {child_resp.status_code} {child_resp.text}")
            
            if master_resp.status_code == 201:
                master_issue = master_resp.json()
                master_iid = master_issue["iid"]
                print(f"✅ Ana Issue Oluşturuldu: {row.get('Summary')}")

                    # --- uploaded CSV'yi güncelle ---
                if os.path.exists(UPLOADED_FILE) and os.path.getsize(UPLOADED_FILE) > 0:
                    uploaded_df = pd.read_csv(UPLOADED_FILE, encoding="utf-8-sig")
                else:
                    uploaded_df = pd.DataFrame(columns=row.keys())

                # Eğer aynı Issue key zaten varsa tekrar ekleme
                if not ((uploaded_df['Issue key'] == row['Issue key']).any()):
                    uploaded_df = pd.concat([uploaded_df, pd.DataFrame([row])], ignore_index=True)
                    uploaded_df.to_csv(UPLOADED_FILE, index=False, encoding="utf-8-sig")
                    print(f"'{row['Issue key']}' uploaded CSV'ye eklendi.")
                else:
                    print(f"'{row['Issue key']}' zaten uploaded CSV'de mevcut, tekrar eklenmedi.")


    print("\n✅ Aktarım tamamlandı. Tüm takımlar için issue'lar oluşturuldu ve grup milestone'una eklendi.\n")

    