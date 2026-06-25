import os
import sys
import requests
from requests.auth import HTTPBasicAuth


def get_env_required(*names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise EnvironmentError(
            f"Variables d'environnement manquantes : {', '.join(missing)}"
        )
    return {n: os.environ[n] for n in names}


def _jira_search(jql, fields, env):
    base_url = env["JIRA_BASE_URL"]
    auth = HTTPBasicAuth(env["JIRA_EMAIL"], env["JIRA_API_TOKEN"])
    headers = {"Accept": "application/json"}

    issues = []
    start_at = 0
    max_results = 50

    while True:
        resp = requests.get(
            f"{base_url}/rest/api/3/search",
            auth=auth,
            headers=headers,
            params={
                "jql": jql,
                "fields": ",".join(fields),
                "startAt": start_at,
                "maxResults": max_results,
            },
            timeout=30,
        )
        if resp.status_code == 401:
            print("[ERROR] Authentification Jira échouée — vérifiez JIRA_EMAIL et JIRA_API_TOKEN", file=sys.stderr)
            sys.exit(1)
        resp.raise_for_status()
        data = resp.json()
        issues.extend(data["issues"])
        if start_at + max_results >= data["total"]:
            break
        start_at += max_results

    return issues


def get_jira_bugs(env):
    jql = (
        'project = CREAT AND issuetype = Bug '
        'AND status not in (Done, Closed, Resolved, "To Deploy PROD") '
        'ORDER BY created DESC'
    )
    fields = [
        "summary", "status", "assignee", "priority", "created",
        "statuscategorychangedate", "duedate",
        "customfield_51129", "customfield_51130",
        "customfield_51131", "customfield_51132",
        "customfield_47323", "customfield_13393",
    ]
    return _jira_search(jql, fields, env)


def get_open_tickets(env):
    jql = 'project = CREAT AND status = "Ouvert" ORDER BY created DESC'
    fields = ["summary", "status", "assignee", "priority", "issuetype", "created"]
    return _jira_search(jql, fields, env)
