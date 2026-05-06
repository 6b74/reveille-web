import os
import json
import requests
import base64
from dotenv import load_dotenv
from feeds import load_feed_config, fetch_all_feeds
from generator import generate_brief
from publisher import publish_brief

load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_PAT = os.environ["GITHUB_PAT"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")


def get_issue_number():
    """Fetch current issue number from the repo. Railway filesystem is ephemeral
    so we store the counter in the repo itself."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/briefs/issue.txt"
    headers = {
        "Authorization": f"token {GITHUB_PAT}",
        "Accept": "application/vnd.github.v3+json",
    }
    r = requests.get(url, headers=headers, params={"ref": GITHUB_BRANCH})
    if r.status_code == 200:
        num = int(base64.b64decode(r.json()["content"]).decode().strip())
        return num + 1
    return 1


def save_issue_number(num):
    """Write the new issue number back to the repo."""
    path = "briefs/issue.txt"
    content = base64.b64encode(str(num).encode()).decode()

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_PAT}",
        "Accept": "application/vnd.github.v3+json",
    }
    r = requests.get(url, headers=headers, params={"ref": GITHUB_BRANCH})
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {
        "message": f"issue counter: {num}",
        "content": content,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    requests.put(url, headers=headers, json=payload)


def main():
    print("[reveille-web] starting daily brief generation")

    print("step 1/4: fetching issue number")
    issue = get_issue_number()
    print(f"  issue #{issue}")

    print("step 2/4: fetching feeds")
    config = load_feed_config()
    feeds = fetch_all_feeds(config)

    print("step 3/4: generating brief")
    brief = generate_brief(feeds, issue)

    print("step 4/4: publishing to GitHub")
    ok = publish_brief(brief, GITHUB_REPO, GITHUB_PAT, GITHUB_BRANCH)

    if ok:
        save_issue_number(issue)
        print(f"[reveille-web] done. issue #{issue} published.")
    else:
        print("[reveille-web] publish failed. check logs.")
        exit(1)


if __name__ == "__main__":
    main()
