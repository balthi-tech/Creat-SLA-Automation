import os
import sys
from datetime import datetime, timedelta, timezone

import requests

from jira_client import get_env_required, get_jira_bugs, get_open_tickets

# ---------------------------------------------------------------------------
# Team routing (report → DM Balthazar, ou fallback vacances)
# ---------------------------------------------------------------------------
BALTHAZAR_ID = "U039GQLN3EK"
JULIEN_ID    = "U047YNMN6"
JOHAN_ID     = "U047ZTJ5J"

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


def get_sla_formatted(issue, field):
    cf = issue["fields"].get(field)
    if not cf or not isinstance(cf, dict):
        return "N/A"
    items = cf.get("items")
    if not items:
        return "N/A"
    return items[0].get("formattedDurationString", "N/A")


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


def format_duration_secs(seconds):
    seconds = abs(int(seconds))
    hours   = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h{minutes:02d}"
    return f"{minutes}min"


def ticket_link(issue, base_url):
    key = issue["key"]
    return f"<{base_url}/browse/{key}|{key}>"

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
        print(f"[WARN] Impossible de vérifier le statut Slack : {exc}", file=sys.stderr)
        return False

# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def section_open_tickets(tickets, base_url):
    if not tickets:
        return "🟦 *Tickets ouverts*\nAucun ticket ouvert."
    lines = ["🟦 *Tickets ouverts*"]
    for t in tickets:
        f        = t["fields"]
        priority = (f.get("priority") or {}).get("name", "N/A")
        assignee = (f.get("assignee") or {}).get("displayName", "—")
        itype    = (f.get("issuetype") or {}).get("name", "N/A")
        summary  = (f.get("summary") or "")[:70]
        lines.append(f"• {ticket_link(t, base_url)} [{priority}] {summary} — {assignee} ({itype})")
    return "\n".join(lines)


def section_tto_active(bugs, now, base_url):
    active = []
    for b in bugs:
        if get_sla_status(b, "customfield_51130") == "IN PROGRESS":
            ms = get_sla_ms(b, "customfield_51131")
            if ms is not None:
                target = now + timedelta(milliseconds=ms)
                active.append((ms, b, target))
    active.sort(key=lambda x: x[0])

    if not active:
        return "⏱️ *TTO en cours*\nAucun TTO en cours."
    lines = ["⏱️ *TTO en cours*"]
    for ms, b, target in active:
        f        = b["fields"]
        priority = (f.get("priority") or {}).get("name", "N/A")
        assignee = (f.get("assignee") or {}).get("displayName", "—")
        remaining = get_sla_formatted(b, "customfield_51131")
        deadline  = target.strftime("%d/%m %H:%M")
        lines.append(f"• {ticket_link(b, base_url)} [{priority}] {remaining} restant → {deadline} — {assignee}")
    return "\n".join(lines)


def section_ttr_active(bugs, now, base_url):
    active = []
    for b in bugs:
        if get_sla_status(b, "customfield_51132") == "IN PROGRESS" and not is_paused(b):
            ms = get_sla_ms(b, "customfield_51129")
            if ms is not None:
                target = now + timedelta(milliseconds=ms)
                pct, _ = calc_pct_elapsed(b, now, "customfield_51129")
                active.append((ms, b, target, pct))
    active.sort(key=lambda x: x[0])

    if not active:
        return "🔵 *TTR en cours*\nAucun TTR en cours."
    lines = ["🔵 *TTR en cours*"]
    for ms, b, target, pct in active:
        f        = b["fields"]
        priority = (f.get("priority") or {}).get("name", "N/A")
        assignee = (f.get("assignee") or {}).get("displayName", "—")
        remaining = get_sla_formatted(b, "customfield_51129")
        deadline  = target.strftime("%d/%m %H:%M")
        pct_str   = f"{pct:.0f}%" if pct is not None else "N/A"
        lines.append(
            f"• {ticket_link(b, base_url)} [{priority}] {remaining} restant → {deadline} ({pct_str}) — {assignee}"
        )
    return "\n".join(lines)


def section_sla_paused(bugs, now, base_url):
    paused = [b for b in bugs if is_paused(b)]
    if not paused:
        return "⏸️ *SLA en pause*\nAucun SLA en pause."
    lines = ["⏸️ *SLA en pause*"]
    for b in paused:
        f        = b["fields"]
        priority = (f.get("priority") or {}).get("name", "N/A")
        assignee = (f.get("assignee") or {}).get("displayName", "—")
        since_str = f.get("statuscategorychangedate", "")
        if since_str:
            since     = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
            pause_dur = format_duration_secs((now - since).total_seconds())
            since_fmt = since.strftime("%d/%m %H:%M")
        else:
            pause_dur = "?"
            since_fmt = "?"
        ttr_frozen = get_sla_formatted(b, "customfield_51129")
        lines.append(
            f"• {ticket_link(b, base_url)} [{priority}] en pause depuis {since_fmt} ({pause_dur}) | TTR gelé: {ttr_frozen} — {assignee}"
        )
    return "\n".join(lines)


def section_breached(bugs, base_url):
    breached = []
    for b in bugs:
        if get_sla_status(b, "customfield_51132") == "BREACHED":
            ms = get_sla_ms(b, "customfield_51129")
            breached.append((ms if ms is not None else 0, b))
    breached.sort(key=lambda x: x[0])  # plus négatif en premier

    if not breached:
        return "❌ *SLA BREACHED*\nAucun SLA breached."
    lines = ["❌ *SLA BREACHED*"]
    for _, b in breached:
        f        = b["fields"]
        priority = (f.get("priority") or {}).get("name", "N/A")
        assignee = (f.get("assignee") or {}).get("displayName", "—")
        status   = (f.get("status") or {}).get("name", "N/A")
        overflow  = get_sla_formatted(b, "customfield_51129")
        pause_tag = " ⏸️" if is_paused(b) else ""
        lines.append(
            f"• {ticket_link(b, base_url)} [{priority}] dépassement: {overflow}{pause_tag} — {assignee} ({status})"
        )
    return "\n".join(lines)


def section_due_dates(bugs, now, base_url):
    today    = now.date()
    with_due = []
    for b in bugs:
        dd = b["fields"].get("duedate")
        if dd:
            from datetime import date as _date
            due_date  = _date.fromisoformat(dd)
            days_left = (due_date - today).days
            with_due.append((days_left, b, due_date))
    with_due.sort(key=lambda x: x[0])

    if not with_due:
        return "📅 *Échéances proches*\nAucune échéance renseignée."
    lines = ["📅 *Échéances proches*"]
    for days_left, b, due_date in with_due:
        f        = b["fields"]
        priority = (f.get("priority") or {}).get("name", "N/A")
        assignee = (f.get("assignee") or {}).get("displayName", "—")
        marker   = "🔴" if days_left < 3 else ("🟠" if days_left < 7 else "🟢")
        lines.append(
            f"• {marker} {ticket_link(b, base_url)} [{priority}] {due_date.strftime('%d/%m/%Y')} ({days_left}j) — {assignee}"
        )
    return "\n".join(lines)


def build_summary(open_tickets, bugs, now, base_url):
    tto_active = sum(1 for b in bugs if get_sla_status(b, "customfield_51130") == "IN PROGRESS")
    ttr_active = sum(
        1 for b in bugs
        if get_sla_status(b, "customfield_51132") == "IN PROGRESS" and not is_paused(b)
    )
    paused  = sum(1 for b in bugs if is_paused(b))
    breached = sum(1 for b in bugs if get_sla_status(b, "customfield_51132") == "BREACHED")
    due_count = sum(1 for b in bugs if b["fields"].get("duedate"))

    summary_line = (
        f"*{len(open_tickets)} tickets ouverts · {tto_active} TTO actifs · "
        f"{ttr_active} TTR actifs · {paused} en pause · {breached} BREACHED · {due_count} échéances*"
    )

    today  = now.date()
    urgent = []
    for b in bugs:
        ttr_status = get_sla_status(b, "customfield_51132")

        if ttr_status == "IN PROGRESS":
            ms = get_sla_ms(b, "customfield_51129")
            if ms is not None and 0 < ms < 4 * 3_600_000:
                urgent.append(f"• ⚡ {ticket_link(b, base_url)}: TTR restant < 4h")

        if ttr_status == "BREACHED":
            ms = get_sla_ms(b, "customfield_51129")
            if ms is not None and ms < -(7 * 24 * 3_600_000):
                urgent.append(f"• 🔥 {ticket_link(b, base_url)}: BREACH depuis > 7 jours")

        dd = b["fields"].get("duedate")
        if dd:
            from datetime import date as _date
            due_date = _date.fromisoformat(dd)
            if (due_date - today).days < 3:
                urgent.append(f"• 📅 {ticket_link(b, base_url)}: échéance dans < 3 jours")

    urgent_text = (
        "*Actions urgentes :*\n" + "\n".join(urgent)
        if urgent
        else "Aucune action urgente."
    )
    return f"{summary_line}\n\n{urgent_text}"

# ---------------------------------------------------------------------------
# Slack sending (DM, chunked blocks)
# ---------------------------------------------------------------------------

def _send_dm(user_id, blocks, slack_token):
    try:
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {slack_token}",
                "Content-Type": "application/json",
            },
            json={"channel": user_id, "blocks": blocks},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            print(f"[WARN] DM vers {user_id} échoué : {data.get('error')}", file=sys.stderr)
    except Exception as exc:
        print(f"[WARN] DM vers {user_id} exception : {exc}", file=sys.stderr)


def _sections_to_block_messages(sections):
    """
    Convertit une liste de textes de sections en messages Slack Block Kit.
    Découpe si un bloc dépasse 2900 chars ou si un message dépasse 49 blocs.
    """
    MAX_TEXT  = 2900
    MAX_BLOCS = 49

    header_blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📊 Rapport SLA — CREAT", "emoji": True},
        },
        {"type": "divider"},
    ]

    section_blocks = []
    for text in sections:
        if len(text) <= MAX_TEXT:
            section_blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        else:
            lines = text.split("\n")
            chunk = ""
            for line in lines:
                candidate = (chunk + "\n" + line).lstrip("\n")
                if len(candidate) > MAX_TEXT:
                    section_blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
                    chunk = line
                else:
                    chunk = candidate
            if chunk:
                section_blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
        section_blocks.append({"type": "divider"})

    all_blocks = header_blocks + section_blocks

    # Découpe en messages de MAX_BLOCS blocs
    messages = []
    for i in range(0, len(all_blocks), MAX_BLOCS):
        messages.append(all_blocks[i:i + MAX_BLOCS])
    return messages


def send_report(recipients, sections, slack_token):
    messages = _sections_to_block_messages(sections)
    for user_id in recipients:
        for msg_blocks in messages:
            _send_dm(user_id, msg_blocks, slack_token)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    env         = get_env_required("JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_BASE_URL", "SLACK_BOT_TOKEN")
    slack_token = env["SLACK_BOT_TOKEN"]
    base_url    = env["JIRA_BASE_URL"]

    print("[INFO] Vérification du statut vacation de Balthazar...")
    if is_balthazar_on_vacation(slack_token):
        print("[INFO] Balthazar est en vacances — rapport envoyé à Julien & Johan")
        recipients = [JULIEN_ID, JOHAN_ID]
    else:
        recipients = [BALTHAZAR_ID]

    print("[INFO] Récupération des données Jira...")
    bugs         = get_jira_bugs(env)
    open_tickets = get_open_tickets(env)
    print(f"[INFO] {len(bugs)} bug(s), {len(open_tickets)} ticket(s) ouverts")

    now = datetime.now(timezone.utc)

    if not bugs and not open_tickets:
        for uid in recipients:
            _send_dm(uid, [{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "📊 *Rapport SLA — CREAT*\nAucun ticket à reporter."},
            }], slack_token)
        return

    sections = [
        section_open_tickets(open_tickets, base_url),
        section_tto_active(bugs, now, base_url),
        section_ttr_active(bugs, now, base_url),
        section_sla_paused(bugs, now, base_url),
        section_breached(bugs, base_url),
        section_due_dates(bugs, now, base_url),
        build_summary(open_tickets, bugs, now, base_url),
    ]

    send_report(recipients, sections, slack_token)
    print(f"[INFO] Rapport envoyé à {recipients}")


if __name__ == "__main__":
    main()
