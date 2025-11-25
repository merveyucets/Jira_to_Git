import csv
import requests
import os
from dateutil import parser
from dotenv import load_dotenv
import sys
import json
from urllib.parse import quote

# .env dosyasını yükle
load_dotenv()

# --- .ENV DEĞİŞKENLERİ ---
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
MASTER_PROJECT_ID = os.getenv("MASTER_PROJECT_ID")
TEAM_PROJECT_MAP = json.loads(os.getenv("TEAM_PROJECT_MAP", "{}"))

HEADERS = {
    "PRIVATE-TOKEN": GITLAB_TOKEN,
    "Content-Type": "application/json"
}

# --- KULLANICI VE PROJE EŞLEŞTİRMELERİ ---
ASSIGNEE_MAP = {
    "merve.yucetas": 31250282,
    "affan.bugra.ozaytas" : 31073378,
    "burak.kiraz": 31073379,
    # Diğer atamaları buraya eklediğinizden emin olun!
}

STAJYER_PROJECT_MAP = {
    "affan.bugra.ozaytas": TEAM_PROJECT_MAP.get("GYT Test ve Otomasyon"),
    "merve.yucetas": TEAM_PROJECT_MAP.get("GYT Proje Yönetimi"),
    "burak.kiraz": TEAM_PROJECT_MAP.get("GYT Simülasyon")
    # Diğer stajyerleri ve projelerini buraya eklediğinizden emin olun!
}

# ------------------- ROBUST CSV OKUYUCU (SORUNUN ÇÖZÜLDÜĞÜ YER) -------------------

def read_jira_csv_robustly(filename):
    """
    CSV'yi manuel olarak okur, 'İlgili Stajyerler' başlığını içeren tüm sütunları
    indeks bazında toplayarak tek bir '__ROBUST_STAJYER_LIST__' anahtarına kaydeder.
    """
    issues = []
    
    try:
        with open(filename, encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = [h.strip() for h in next(reader)] # Başlığı oku ve temizle
            
            # 'İlgili Stajyerler' içeren tüm sütunların indekslerini bul
            stajyer_indices = [i for i, col_name in enumerate(header) if "İlgili Stajyerler" in col_name]

            for row_data in reader:
                issue = {}
                
                # --- 1. Robust Stajyerleri Çekme (Tüm ilgili sütunlardan) ---
                stajyer_list_raw = []
                for idx in stajyer_indices:
                    if idx < len(row_data):
                        val = row_data[idx].strip()
                        if val:
                            # Virgülle ayrılmış birden çok stajyer varsa onları ayır
                            stajyer_list_raw.extend([s.strip() for s in val.split(",") if s.strip()])
                
                # Temizlenmiş listeyi özel bir anahtara kaydet
                issue['__ROBUST_STAJYER_LIST__'] = list(set([s for s in stajyer_list_raw if s and '@' not in s]))
                
                # --- 2. Diğer Sütunları Çekme (Diğer alanlar için DictReader davranışını taklit et) ---
                # Başlık adları aynı olsa bile (DictReader'da olduğu gibi) sonuncuyu kaydeder.
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

# ------------------- TEMİZLİK VE YARDIMCI FONKSİYONLAR (DEĞİŞMEDİ) -------------------

def get_all_issues(project_id):
    issues = []
    page = 1
    while True:
        url = f"https://gitlab.com/api/v4/projects/{project_id}/issues?per_page=100&page={page}"
        r = requests.get(url, headers=HEADERS)
        if r.status_code != 200:
            break
        data = r.json()
        if not data:
            break
        issues.extend(data)
        page += 1
    return issues

def delete_issue(project_id, iid):
    url = f"https://gitlab.com/api/v4/projects/{project_id}/issues/{iid}"
    r = requests.delete(url, headers=HEADERS)
    if r.status_code == 204:
        print(f"🗑️ Silindi: project={project_id} IID={iid}")
    else:
        print(f"⚠️ Silinemedi (project={project_id} IID={iid}): {r.status_code} {r.text}")
        
def delete_all_issues():
    project_ids = set([int(MASTER_PROJECT_ID)] + [pid for pid in TEAM_PROJECT_MAP.values() if pid])
    
    print(f"Temizlenecek Proje ID'leri: {project_ids}")
    for pid in project_ids:
        issues = get_all_issues(pid)
        print(f"Project {pid}: Toplam {len(issues)} issue bulundu.")
        for issue in issues:
            delete_issue(pid, issue["iid"])
    print("✅ Tüm issue'lar silindi.")

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

def find_milestone(project_id, title):
    safe_title = quote(title)
    url = f"https://gitlab.com/api/v4/projects/{project_id}/milestones?search={safe_title}"
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200:
        for m in r.json():
            if m.get("title") == title:
                return m
    return None

def create_milestone(project_id, title, due_date=None):
    url = f"https://gitlab.com/api/v4/projects/{project_id}/milestones"
    data = {"title": title}
    if due_date:
        data["due_date"] = due_date
    
    r = requests.post(url, headers=HEADERS, json=data)
    if r.status_code == 201:
        print(f"✨ Milestone oluşturuldu: Project {project_id}, Title: {title}")
        return r.json()
    else:
        print(f"⚠️ Milestone oluşturulamadı (Project {project_id}, {r.status_code}): {r.text}")
        return None

def ensure_milestone_id(project_id, title, due_date=None):
    if not project_id:
        return None
        
    milestone = find_milestone(project_id, title)
    if not milestone:
        milestone = create_milestone(project_id, title, due_date)
    return milestone

# ------------------- ANA İŞLEMLER -------------------

if __name__ == "__main__":
    if "--delete-all" in sys.argv:
        confirm = input("⚠️ DİKKAT: TÜM issue'lar silinsin mi? (y/n): ")
        if confirm.lower() == "y":
            delete_all_issues()
        else:
            print("🚫 İşlem iptal edildi.")
        exit()

    # 🔥 YENİ ROBUST OKUMA FONKSİYONUNU KULLAN
    rows = read_jira_csv_robustly("jira_export_all.csv")

    print(f"Toplam {len(rows)} Jira kaydı okundu.")

    for i, row in enumerate(rows, start=1):
        # CSV'yi okurken zaten temizlenmişti, bu satıra gerek kalmadı ancak güvenilirlik için bırakılabilir
        # clean_row = {k.strip(): v for k, v in row.items()} 
        
        title = (row.get("Summary") or "Untitled").strip()
        jira_key = row.get("Issue key") or ""
        print(f"\n--- {i}/{len(rows)}: İşleniyor {jira_key} - {title} ---")

        # 🔥 MANUEL OLARAK ÇEKİLMİŞ STAJYER LİSTESİNİ KULLAN
        ilgili_stajyerler = row.get('__ROBUST_STAJYER_LIST__', [])
        print(f"➡️ Tespit Edilen Stajyerler: {', '.join(ilgili_stajyerler) or 'Yok'}")

        # --- Metadata ve Açıklama Hazırlığı ---
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

        # --- 1. Master Issue Oluşturma ---
        assignee_jira = row.get("Assignee")
        master_assignee_id = ASSIGNEE_MAP.get(assignee_jira)
        milestone_title = row.get("Epic Link") or "Default Sprint"
        
        master_milestone = ensure_milestone_id(
            MASTER_PROJECT_ID,
            milestone_title,
            due_date=due_date
        )

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
        if master_milestone:
            master_data["milestone_id"] = master_milestone["id"]

        master_url = f"https://gitlab.com/api/v4/projects/{MASTER_PROJECT_ID}/issues"
        master_resp = requests.post(master_url, headers=HEADERS, json=master_data)
        
        if master_resp.status_code == 201:
            master_issue = master_resp.json()
            master_iid = master_issue["iid"]
            print(f"✅ Master Issue Oluşturuldu: {master_issue['web_url']}")
        else:
            print(f"⚠️ Master issue oluşturulamadı ({jira_key}): {master_resp.status_code} {master_resp.text}")
            continue

        # --- 2. Child Issue'ları Oluşturma ve Linkleme ---
        master_proj = int(MASTER_PROJECT_ID)

        for stajyer in ilgili_stajyerler:
            proj_id = STAJYER_PROJECT_MAP.get(stajyer)

            if not proj_id:
                print(f"⚠️ Stajyer '{stajyer}' için proje ID'si bulunamadı (STAJYER_PROJECT_MAP'i kontrol edin). Atlanyor.")
                continue

            child_assignee_id = ASSIGNEE_MAP.get(stajyer)

            child_description = (
                f"**Ana Issue:** Project {master_proj}, IID {master_iid} ({master_issue['web_url']})\n\n"
                f"--- Orijinal Açıklama ---\n\n"
                f"{orig_description}"
            )
            
            # Milestone: Child Proje için al/oluştur (Proje ID'sine özel)
            child_milestone = ensure_milestone_id(
                proj_id,
                milestone_title,
                due_date=due_date
            )

            child_data = {
                "title": title + f" (İş Paketi - {stajyer.split('.')[0].title()})",
                "description": child_description,
                "labels": labels_str,
                "time_estimate": original_estimate,
                "spent_time": time_spent
            }
            if due_date:
                child_data["due_date"] = due_date
            if child_assignee_id:
                child_data["assignee_ids"] = [child_assignee_id]
            if child_milestone:
                child_data["milestone_id"] = child_milestone["id"]

            child_url = f"https://gitlab.com/api/v4/projects/{proj_id}/issues"
            child_resp = requests.post(child_url, headers=HEADERS, json=child_data)
            
            if child_resp.status_code == 201:
                child_issue = child_resp.json()
                child_iid = child_issue["iid"]
                
                link_issues(master_proj, master_iid, proj_id, child_iid) 
                print(f"  -> Child Issue Oluşturuldu ({stajyer}): {child_issue['web_url']} ve Master ile linklendi.")
            else:
                print(f"⚠️ Child issue oluşturulamadı (stajyer {stajyer}, project {proj_id}): {child_resp.status_code} {child_resp.text}")

    print("\n✅ Aktarım tamamlandı. Tüm stajyerler için issue'lar oluşturuldu ve linklendi.")