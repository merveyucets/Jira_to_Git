import csv
import requests
import os
from dateutil import parser
from dotenv import load_dotenv
import sys

load_dotenv()

GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
PROJECT_ID = os.getenv("PROJECT_ID")

HEADERS = {
    "PRIVATE-TOKEN": GITLAB_TOKEN,
    "Content-Type": "application/json"
}

ASSIGNEE_MAP = {
    "merve.yucetas": 31250282,
    "affan.bugra.ozaytas" : 31073378,
}

# ------------------- 🧹 TEMİZLİK (DELETE ALL) -------------------

def get_all_issues():
    """Projeden tüm issue'ları çeker (sayfa sayfa)."""
    issues = []
    page = 1
    while True:
        url = f"https://gitlab.com/api/v4/projects/{PROJECT_ID}/issues?per_page=100&page={page}"
        r = requests.get(url, headers=HEADERS)
        if r.status_code != 200:
            print(f"⚠️ Hata: {r.status_code} {r.text}")
            break
        data = r.json()
        if not data:
            break
        issues.extend(data)
        page += 1
    return issues

def delete_issue(iid):
    """Tek bir issue'yu siler."""
    url = f"https://gitlab.com/api/v4/projects/{PROJECT_ID}/issues/{iid}"
    r = requests.delete(url, headers=HEADERS)
    if r.status_code == 204:
        print(f"🗑️ Silindi: IID={iid}")
    else:
        print(f"⚠️ Silinemedi (IID={iid}): {r.status_code} {r.text}")
        
def delete_all_issues():
    issues = get_all_issues()
    print(f"Toplam {len(issues)} issue bulundu.")
    for issue in issues:
        delete_issue(issue["iid"])
    print("✅ Tüm issue'lar silindi.")


if __name__ == "__main__":
    if "--delete-all" in sys.argv:
        confirm = input("⚠️ TÜM issue'lar silinsin mi? (y/n): ")
        if confirm.lower() == "y":
            delete_all_issues()
        else:
            print("🚫 İşlem iptal edildi.")
        exit()
        
# ------------------- 💼 ANA PROGRAM -------------------
        
def parse_date(date_str):
    if not date_str:
        return None
    try:
        return parser.parse(date_str).strftime("%Y-%m-%d")
    except Exception:
        return None

def seconds_to_gitlab_duration(seconds):
    """
    Saniye (int veya numeric-string) -> GitLab duration string, örn: '2h 30m'
    Eğer seconds None/''/0 dönerse None.
    """
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

def parse_work_ratio(ratio_str, original_sec, spent_sec):
    """
    Eğer CSV'de Work Ratio geldiyse onu temizler ('40%' -> 40)
    yoksa hesapla: spent / original * 100 (yuvarlanmış)
    """
    if ratio_str:
        try:
            return float(str(ratio_str).strip().replace("%",""))
        except Exception:
            pass
    # hesapla (güvenli)
    try:
        o = int(float(original_sec)) if original_sec not in (None, "") else 0
        s = int(float(spent_sec)) if spent_sec not in (None, "") else 0
        if o > 0:
            return round((s / o) * 100, 2)
    except Exception:
        pass
    return None

def link_as_child(parent_iid, child_iid):
    """GitLab'da Child-Parent ilişkisi kurar."""
    url = f"https://gitlab.com/api/v4/projects/{PROJECT_ID}/issues/{parent_iid}/links"
    data = {
        "target_project_id": PROJECT_ID,  # ✅ eksik parametre eklendi
        "target_issue_iid": child_iid,
        "link_type": "relates_to"         # isteğe bağlı, "blocks"/"is_blocked_by" da olabilir
    }
    r = requests.post(url, headers=HEADERS, json=data)
    if r.status_code == 201:
        print(f"🔗 {child_iid} → {parent_iid} altına başarıyla eklendi.")
    else:
        print(f"⚠️ Child link hatası ({r.status_code}): {r.text}")


issue_map = {}
# ---------- MAIN ----------
with open("jira_export_all.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    
for i, row in enumerate(rows, start=1):
    clean_row = {k.strip(): v for k, v in row.items()}
    title = (clean_row.get("Summary") or "Untitled").strip()
    print(f"{i}. title = {title}")
    
    jira_id = row.get("Issue id") or ""
    parent_id = row.get("Parent id") or ""

    orig_description = (row.get("Description") or "").strip()
    jira_key = row.get("Issue key") or ""
    issue_type = (row.get("Issue Type") or "").strip().lower()
    labels = [lbl for lbl in [jira_key, row.get("Priority")] if lbl]

    # Dates
    start_date = parse_date(row.get("Created"))
    due_date = parse_date(row.get("Due Date"))

    # RAW seconds from CSV (may be empty strings)
    original_sec_raw = row.get("Original Estimate")
    remaining_sec_raw = row.get("Remaining Estimate")
    spent_sec_raw = row.get("Time Spent")
    work_ratio_raw = row.get("Work Ratio")

    # Eğer Remaining boşsa -> remaining = original - spent (saniye cinsinden)
    try:
        o_sec = int(float(original_sec_raw)) if original_sec_raw not in (None, "") else 0
    except Exception:
        o_sec = 0
    try:
        s_sec = int(float(spent_sec_raw)) if spent_sec_raw not in (None, "") else 0
    except Exception:
        s_sec = 0
    try:
        r_sec = int(float(remaining_sec_raw)) if remaining_sec_raw not in (None, "") else None
    except Exception:
        r_sec = None

    if r_sec is None and o_sec > 0:
        computed_remaining = max(o_sec - s_sec, 0)
    else:
        computed_remaining = r_sec if r_sec is not None else None

    # Convert to GitLab duration strings
    original_estimate = seconds_to_gitlab_duration(o_sec)   # örn "40h"
    remaining_estimate = seconds_to_gitlab_duration(computed_remaining)
    time_spent = seconds_to_gitlab_duration(s_sec)

    # Work ratio
    work_ratio = parse_work_ratio(work_ratio_raw, o_sec, s_sec)

    # Description: include time summary + start/due
    time_summary = (
        f"**Time Tracking Summary**\n"
        f"- Original Estimate: {original_estimate or 'N/A'}\n"
        f"- Time Spent: {time_spent or 'N/A'}\n"
        f"- Remaining: {remaining_estimate or 'N/A'}\n"
        f"- Work Ratio: {str(work_ratio) + '%' if work_ratio is not None else 'N/A'}\n\n"
        f"**Start Date (from Jira Created):** {start_date or 'N/A'}\n\n"
    )
    description = time_summary + orig_description

    if issue_type == "task":
        labels.append("📁 Epic")       # Üst görev
    elif issue_type == "sub-task":
        labels.append("Subtask")       # Alt görev

    if row.get("Labels"):
        labels += [x.strip() for x in row["Labels"].split(",") if x.strip()]
    labels_str = ",".join(labels)

    assignee_jira = row.get("Assignee")
    assignee_id = ASSIGNEE_MAP.get(assignee_jira)

    
    data = {
        "title": title,
        "description": description,
        "labels": labels_str
    }
    if due_date:
        data["due_date"] = due_date
    if assignee_id:
        data["assignee_ids"] = [assignee_id]
    

    # create issue
    url = f"https://gitlab.com/api/v4/projects/{PROJECT_ID}/issues"
    r = requests.post(url, headers=HEADERS, json=data)

    if r.status_code == 201:
        issue_iid = r.json()["iid"]
        print(f"✅ {i}. {title} → Issue oluşturuldu (iid={issue_iid}).")
        # 🔸 Issue eşlemesini kaydet
        if jira_id:
            issue_map[jira_id] = {"iid": issue_iid, "parent": parent_id}

        # Votes -> award emojis
        vote_count = int(row.get("Votes") or 0)
        if vote_count > 0:
            print(f"   👍 {vote_count} onay eklenecek...")
            emoji_url = f"https://gitlab.com/api/v4/projects/{PROJECT_ID}/issues/{issue_iid}/award_emoji"
            for _ in range(vote_count):
                emoji_resp = requests.post(emoji_url, headers=HEADERS, json={"name": "thumbsup"})
                if emoji_resp.status_code == 201:
                    pass
                else:
                    print(f"      ⚠️ Emoji eklenemedi: {emoji_resp.status_code} {emoji_resp.text}")

        # Set time estimate (Original Estimate)
        if original_estimate:
            est_url = f"https://gitlab.com/api/v4/projects/{PROJECT_ID}/issues/{issue_iid}/time_estimate"
            est_resp = requests.post(est_url, headers=HEADERS, json={"duration": original_estimate})
            print(f"   ⏱️ Time estimate set: {original_estimate} ({est_resp.status_code})")

        # Add spent time
        if time_spent:
            spent_url = f"https://gitlab.com/api/v4/projects/{PROJECT_ID}/issues/{issue_iid}/add_spent_time"
            spent_resp = requests.post(spent_url, headers=HEADERS, json={"duration": time_spent})
            print(f"   🕓 Time spent added: {time_spent} ({spent_resp.status_code})")

    else:
        print(f"⚠️ {i}. {title} → Hata ({r.status_code}): {r.text}")

# 2️⃣ Parent-child ilişkilerini kur
print("\n--- 🧩 Child ilişkileri oluşturuluyor ---")
for jira_id, info in issue_map.items():
    parent_id = info["parent"]
    if parent_id and parent_id in issue_map:
        parent_iid = issue_map[parent_id]["iid"]
        child_iid = info["iid"]
        link_as_child(parent_iid, child_iid)
        
        
        
        


#python sync_to_gitlab.py --delete-all
