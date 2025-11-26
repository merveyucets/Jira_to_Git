import os
import requests
import json
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
MASTER_PROJECT_ID = os.getenv("MASTER_PROJECT_ID")
TEAM_PROJECT_MAP = json.loads(os.getenv("TEAM_PROJECT_MAP", "{}"))
GROUP_ID = os.getenv("GROUP_ID")  # Grup milestone'ları için

HEADERS = {
    "PRIVATE-TOKEN": GITLAB_TOKEN,
    "Content-Type": "application/json"
}

def get_all_issues(project_id):
    """Belirli proje altındaki tüm issue'ları getir."""
    issues = []
    page = 1
    while True:
        url = f"https://gitlab.com/api/v4/projects/{project_id}/issues?per_page=100&page={page}"
        r = requests.get(url, headers=HEADERS)
        if r.status_code != 200:
            print(f"⚠️ Hata: project {project_id} issue alınamadı ({r.status_code})")
            break
        data = r.json()
        if not data:
            break
        issues.extend(data)
        page += 1
    return issues

def delete_issue(project_id, iid):
    """Tek bir issue'yu sil."""
    url = f"https://gitlab.com/api/v4/projects/{project_id}/issues/{iid}"
    r = requests.delete(url, headers=HEADERS)
    if r.status_code == 204:
        print(f"🗑️ Silindi: project={project_id} IID={iid}")
    else:
        print(f"⚠️ Silinemedi: project={project_id} IID={iid} ({r.status_code}) {r.text}")

def delete_all_issues():
    """Master ve tüm stajyer projelerindeki tüm issue'ları sil."""
    project_ids = set([int(MASTER_PROJECT_ID)] + [pid for pid in TEAM_PROJECT_MAP.values() if pid])
    print(f"Temizlenecek projeler: {project_ids}")

    for pid in project_ids:
        issues = get_all_issues(pid)
        print(f"Project {pid}: {len(issues)} issue bulundu. Siliniyor...")
        for issue in issues:
            delete_issue(pid, issue["iid"])

    print("✅ Tüm issue'lar silindi.")

def get_all_group_milestones(group_id):
    """Belirli grup altındaki tüm milestone'ları getir."""
    milestones = []
    page = 1
    while True:
        url = f"https://gitlab.com/api/v4/groups/{group_id}/milestones?per_page=100&page={page}"
        r = requests.get(url, headers=HEADERS)
        if r.status_code != 200:
            print(f"⚠️ Hata: Group {group_id} milestone alınamadı ({r.status_code})")
            break
        data = r.json()
        if not data:
            break
        milestones.extend(data)
        page += 1
    return milestones

def delete_group_milestones():
    """Tüm grup milestone'larını sil."""
    if not GROUP_ID:
        print("⚠️ GROUP_ID .env dosyasında bulunamadı. Milestone silme atlandı.")
        return
    milestones = get_all_group_milestones(GROUP_ID)
    print(f"Group {GROUP_ID}: {len(milestones)} milestone bulundu. Siliniyor...")
    for m in milestones:
        url = f"https://gitlab.com/api/v4/groups/{GROUP_ID}/milestones/{m['id']}"
        r = requests.delete(url, headers=HEADERS)
        if r.status_code == 204:
            print(f"🗑️ Silindi: Milestone '{m['title']}' ({m['id']})")
        else:
            print(f"⚠️ Silinemedi: Milestone '{m['title']}' ({m['id']}) ({r.status_code}) {r.text}")
    print("✅ Tüm grup milestone'ları silindi.")

if __name__ == "__main__":
    confirm = input("⚠️ DİKKAT: Tüm projelerdeki issue'lar ve grup milestone'ları silinsin mi? (y/n): ")
    if confirm.lower() == "y":
        delete_all_issues()
        delete_group_milestones()
    else:
        print("🚫 İşlem iptal edildi.")
