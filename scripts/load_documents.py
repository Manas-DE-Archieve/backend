import requests
from pathlib import Path

BASE_URL = "http://localhost:8000"

LOGIN_URL = f"{BASE_URL}/api/auth/login"
UPLOAD_URL = f"{BASE_URL}/api/documents/upload"

DATA_PATH = Path("../test_data/documents")

EMAIL = "admin@example.com"
PASSWORD = "strongpassword123"


def get_token():
    response = requests.post(
        LOGIN_URL,
        json={
            "email": EMAIL,
            "password": PASSWORD
        }
    )

    if response.status_code != 200:
        raise Exception(f"❌ Login failed: {response.text}")

    token = response.json()["access_token"]
    print("🔐 Authenticated")

    return token


def upload_file(file_path, headers):
    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f)}
        response = requests.post(UPLOAD_URL, files=files, headers=headers)

    if response.status_code in (200, 201):
        print(f"✅ Uploaded: {file_path.name}")
    else:
        print(f"❌ Failed: {file_path.name} -> {response.text}")


def main():
    token = get_token()

    headers = {
        "Authorization": f"Bearer {token}"
    }

    files = list(DATA_PATH.glob("*.txt"))
    print(f"📂 Found {len(files)} files")

    for file in files:
        upload_file(file, headers)


if __name__ == "__main__":
    main()