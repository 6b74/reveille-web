import requests
import json
import base64


def get_current_sha(repo, path, pat, branch="main"):
    """Get the current file SHA - required by GitHub API to update an existing file."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github.v3+json",
    }
    r = requests.get(url, headers=headers, params={"ref": branch})
    if r.status_code == 200:
        return r.json().get("sha")
    return None  # file doesn't exist yet, first publish


def publish_brief(brief, repo, pat, branch="main"):
    path = "briefs/today.json"
    content = json.dumps(brief, indent=2, ensure_ascii=False)
    encoded = base64.b64encode(content.encode()).decode()

    sha = get_current_sha(repo, path, pat, branch)

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {
        "message": f"daily brief: {brief['date']} (issue #{brief['issue']})",
        "content": encoded,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha  # required when updating an existing file

    r = requests.put(url, headers=headers, json=payload)

    if r.status_code in (200, 201):
        print(f"  published to {repo}/{path}")
        return True
    else:
        print(f"  publish failed: {r.status_code} {r.text}")
        return False
