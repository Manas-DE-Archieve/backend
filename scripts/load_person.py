import requests
from pathlib import Path

BASE_URL = "http://localhost:8000"

LOGIN_URL = f"{BASE_URL}/api/auth/login"
UPLOAD_URL = f"{BASE_URL}/api/documents/upload"
PERSON_URL = f"{BASE_URL}/api/persons"

DATA_PATH = Path("../test_data/documents")

EMAIL = "kanybekovdaniel6@gmail.com"
PASSWORD = "sAmat.2004h"


def get_token():
    response = requests.post(
        LOGIN_URL,
        json={
            "email": EMAIL,
            "password": PASSWORD
        }
    )

    if not response.ok:
        raise Exception(f"Login failed: {response.text}")

    return response.json()["access_token"]


def upload_document(file_path, headers):
    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f)}
        response = requests.post(UPLOAD_URL, files=files, headers=headers)

    if not response.ok:
        print(f"❌ Upload failed: {file_path.name} -> {response.text}")
        return None

    print(f"✅ Document uploaded: {file_path.name}")
    return response.json()


def create_person(file_path, headers):
    # 💡 простой парсинг имени из файла
    name = file_path.stem.replace("_", " ").title()

    data = {
        "full_name": name,
        "birth_year": None,
        "death_year": None,
        "region": "Unknown",
        "charge": "Unknown",
        "biography": f"Auto-generated from document: {file_path.name}",
        "force": True 
    }

    response = requests.post(PERSON_URL, json=data, headers=headers)

    # Улучшенная проверка на то, вернуло ли API предупреждение о дубликате
    if response.ok and response.json().get("duplicates_found"):
        print(f"⚠️ Duplicate ignored for: {name}")
        return None

    if not response.ok:
        print(f"❌ Person failed: {file_path.name} -> {response.text}")
        return None

    print(f"👤 Person created: {name}")
    return response.json()

def main():
    token = get_token()

    headers = {
        "Authorization": f"Bearer {token}"
    }

    files = list(DATA_PATH.glob("*.txt"))
    print(f"📂 Found {len(files)} files")

    for file in files:
        upload_document(file, headers)
        create_person(file, headers)


if __name__ == "__main__":
    main()