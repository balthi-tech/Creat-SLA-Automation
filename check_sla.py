import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

from jira_client import get_env_required, get_jira_bugs

# ---------------------------------------------------------------------------
# Team mapping : Jira email → Slack User ID
# ---------------------------------------------------------------------------
JIRA_TO_SLACK = {
    "balthazar.roque@consulting-for.edenred.com": "U039GQLN3EK",
    "julien.blatecky@consulting-for.edenred.com": "U047YNMN6",
    "johan.dufau@consulting-for.edenred.com":      "U047ZTJ5J",
    "sylviane.tran@consulting-for.edenred.com":    "UCRGT6DGE",
    "louan.bengmah@consulting-for.edenred.com":    "U04J01NACP5",
    "thibault.vlacich@consulting-for.edenred.com": "U0D6GEBHQ",
}

BALTHAZAR_ID = "U039GQLN3EK"
JULIEN_ID    = "U047YNMN6"
JOHAN_ID     = "U047ZTJ5J"

STATE_FILE = "sla_state.json"
THRESHOLDS = [50, 75, 90]

LEVEL_COLORS = {
    50:         "#eab308",
    75:         "#f97316",
    90:         "#dc2626",
    "BREACHED": "#7f1d1d",
}

LEVEL_EMOJI = {
    50:         "🟡",
    75:         "🟠",
    90:         "🔴",
    "BREACHED": "🚨",
}

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)

# ---------------------------------------------------------------------------
# SLA helpers
# ---------------------------------------------------------------------------

def is_paused(issue):
    status_name = (issue["fields"].get("status") or {}).get("name", "")
    return "attente" in status_name.lower()


def get_sla_status(issue, field):
    v = issue["fields"].get(field)
    if v is None:
        return "No SLA"
    if isinstance(v, dict):
        return v.get("value", "No SLA")
    return v


def get_sla_ms(issue, field):
    cf = issue["fields"].get(field)
    if not cf or not isinstance(cf, dict):
        return None
    items = cf.get("items")
    if not items:
        return None
    return items[0].get("milliseconds")


def calc_pct_elapsed(issue, now, ms_field):
    remaining_ms = get_sla_ms(issue, ms_field)
    if remaining_ms is None:
        return None, None
    created_str = issue["fields"]["created"]
    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
    target_date = now + timedelta(milliseconds=remaining_ms)
    total_secs = (target_date - created).total_seconds()
    if total_secs <= 0:
        return 100.0, target_date
    elapsed_secs = (now - created).total_seconds()
    return (elapsed_secs / total_secs) * 100, target_date

# ---------------------------------------------------------------------------
# Vacation detection
# ---------------------------------------------------------------------------

def is_balthazar_on_vacation(slack_token):
    try:
        resp = requests.get(
            "https://slack.com/api/users.profile.get",
            headers={"Authorization": f"Bearer {slack_token}"},
            params={"user": BALTHAZAR_ID},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            return False
        profile = data.get("profile", {})
        emoji = profile.get("status_emoji", "")
        text  = profile.get("status_text", "")
        return ":palm_tree:" in emoji or "en vacances" in text.lower()
    except Exception as exc:
        print(f"[WARN] Impossible de vérifier le statut Slack de Balthazar : {exc}", file=sys.stderr)
        return False

# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def get_ttr_recipients(assignee_email, is_vacation):
    recipients = [JULIEN_ID, JOHAN_ID] if is_vacation else [BALTHAZAR_ID]
    if assignee_email:
        slack_id = JIRA_TO_SLACK.get(assignee_email)
        if slack_id and slack_id not in recipients:
            recipients.append(slack_id)
    return recipients


def get_tto_recipients(is_vacation):
    return [JULIEN_ID, JOHAN_ID] if is_vacation else [BALTHAZAR_ID]

# ---------------------------------------------------------------------------
# Slack DM builder & sender
# ---------------------------------------------------------------------------

def build_slack_dm(issue, level, pct, target_date, sla_type):
    key       = issue["key"]
    base_url  = os.environ.get("JIRA_BASE_URL", "https://edenred.atlassian.net")
    fields    = issue["fields"]
    summary   = fields.get("summary", "")
    priority  = (fields.get("priority") or {}).get("name", "N/A")
    assignee  = (fields.get("assignee") or {}).get("displayName", "Non assigné")
    color     = LEVEL_COLORS.get(level, "#888888")
    emoji     = LEVEL_EMOJI.get(level, "⚠️")

    if level == "BREACHED":
        header_text = f"{emoji} SLA {sla_type} BREACHED — {key} [{priority}]"
        pct_text    = "100%+"
    else:
        header_text = f"{emoji} SLA {sla_type} {level}% — {key} [{priority}]"
        pct_text    = f"{pct:.0f}%"

    deadline_text = target_date.strftime("%d/%m/%Y %H:%M UTC") if target_date else "N/A"

    return {
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": header_text, "emoji": True},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Ticket:*\n<{base_url}/browse/{key}|{key}>"},
                            {"type": "mrkdwn", "text": f"*Priorité:*\n{priority}"},
                            {"type": "mrkdwn", "text": f"*Assigné:*\n{assignee}"},
                            {"type": "mrkdwn", "text": f"*{sla_type} écoulé:*\n{pct_text}"},
                            {"type": "mrkdwn", "text": f"*Deadline:*\n{deadline_text}"},
                            {"type": "mrkdwn", "text": f"*Type SLA:*\n{sla_type}"},
                        ],
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Résumé:* {summary}"},
                    },
                ],
            }
        ]
    }


def send_dm(user_id, payload, slack_token):
    try:
        body = {"channel": user_id, **payload}
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {slack_token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            print(f"[WARN] DM vers {user_id} échoué : {data.get('error')}", file=sys.stderr)
    except Exception as exc:
        print(f"[WARN] DM vers {user_id} exception : {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Core SLA processing loop
# ---------------------------------------------------------------------------

def process_sla(bugs, state, now, is_vacation, slack_token, sla_type):
    if sla_type == "TTR":
        status_field = "customfield_51132"
        ms_field     = "customfield_51129"
    else:
        status_field = "customfield_51130"
        ms_field     = "customfield_51131"

    changed = False

    for issue in bugs:
        key         = issue["key"]
        sla_status  = get_sla_status(issue, status_field)
        assignee_email = (issue["fields"].get("assignee") or {}).get("emailAddress")

        # Ticket terminé → nettoyage de tous ses états
        if sla_status in ("MET", "No SLA"):
            stale = [k for k in state if k.startswith(f"{key}_{sla_type}_")]
            for k in stale:
                del state[k]
                changed = True
            continue

        # BREACHED
        if sla_status == "BREACHED":
            breach_key = f"{key}_{sla_type}_BREACHED"
            if breach_key not in state:
                _, target_date = calc_pct_elapsed(issue, now, ms_field)
                payload = build_slack_dm(issue, "BREACHED", 100, target_date, sla_type)
                recipients = (
                    get_ttr_recipients(assignee_email, is_vacation)
                    if sla_type == "TTR"
                    else get_tto_recipients(is_vacation)
                )
                for uid in recipients:
                    send_dm(uid, payload, slack_token)
                state[breach_key] = True
                changed = True
                print(f"[ALERTE] {key} {sla_type} BREACHED → DM envoyé à {recipients}")
            continue

        # IN PROGRESS avec seuils
        if sla_status != "IN PROGRESS":
            continue

        if is_paused(issue):
            continue

        pct, target_date = calc_pct_elapsed(issue, now, ms_field)
        if pct is None:
            continue

        for threshold in THRESHOLDS:
            t_key = f"{key}_{sla_type}_{threshold}"
            if pct >= threshold:
                if t_key not in state:
                    payload = build_slack_dm(issue, threshold, pct, target_date, sla_type)
                    recipients = (
                        get_ttr_recipients(assignee_email, is_vacation)
                        if sla_type == "TTR"
                        else get_tto_recipients(is_vacation)
                    )
                    for uid in recipients:
                        send_dm(uid, payload, slack_token)
                    state[t_key] = True
                    changed = True
                    print(f"[ALERTE] {key} {sla_type} {threshold}% ({pct:.1f}%) → DM envoyé à {recipients}")
            else:
                if t_key in state:
                    del state[t_key]
                    changed = True
                    print(f"[RESET] {key} {sla_type} {threshold}% réinitialisé (pct={pct:.1f}%)")

    return changed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    env          = get_env_required("JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_BASE_URL", "SLACK_BOT_TOKEN")
    slack_token  = env["SLACK_BOT_TOKEN"]

    print("[INFO] Vérification du statut vacation de Balthazar...")
    is_vacation = is_balthazar_on_vacation(slack_token)
    if is_vacation:
        print("[INFO] Balthazar est en vacances — routing vers Julien & Johan")

    print("[INFO] Récupération des bugs Jira...")
    bugs = get_jira_bugs(env)
    print(f"[INFO] {len(bugs)} bug(s) récupéré(s)")

    state = load_state()
    now   = datetime.now(timezone.utc)

    changed_ttr = process_sla(bugs, state, now, is_vacation, slack_token, "TTR")
    changed_tto = process_sla(bugs, state, now, is_vacation, slack_token, "TTO")

    if changed_ttr or changed_tto:
        save_state(state)
        print("[INFO] sla_state.json mis à jour.")
    else:
        print("[INFO] Aucun changement d'état.")


if __name__ == "__main__":
    main()
