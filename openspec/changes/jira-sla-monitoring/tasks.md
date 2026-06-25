## 1. Initialisation du repo

- [x] 1.1 Créer `sla_state.json` à la racine avec le contenu `{}`
- [x] 1.2 Créer `requirements.txt` avec la dépendance `requests`
- [x] 1.3 Créer le dossier `.github/workflows/`

## 2. Script check_sla.py — Alerting

- [x] 2.1 Implémenter la fonction `get_jira_bugs()` : appel API Jira avec authentification Basic Auth, JQL bugs actifs, pagination complète
- [x] 2.2 Implémenter la fonction `load_state()` / `save_state()` : lecture/écriture de `sla_state.json`
- [x] 2.3 Implémenter la fonction `is_paused(issue)` : détection du statut "attente" dans `status.name`
- [x] 2.4 Implémenter la fonction `calc_pct_elapsed(issue, now)` : calcul du % TTR écoulé via `now + timedelta(ms=remaining_ms)`
- [x] 2.5 Implémenter `is_balthazar_on_vacation(slack_token)` : appel `users.profile.get` avec User ID `U039GQLN3EK`, détecte emoji `:palm_tree:` ou texte "en vacances", fail-safe si erreur API
- [x] 2.6 Implémenter `get_recipients(assignee_email, is_vacation)` : retourne la liste des Slack User IDs à notifier selon le type (TTO → Balthazar/fallback seulement ; TTR → Balthazar/fallback + assigné)
- [x] 2.7 Implémenter `build_slack_dm(issue, level, pct, target_date, sla_type)` : payload Block Kit avec couleur, champs (ticket, résumé, priorité, assigné, type SLA, % écoulé, deadline)
- [x] 2.8 Implémenter `send_dm(user_id, payload, slack_token)` : POST vers `https://slack.com/api/chat.postMessage` avec `channel: user_id`, gestion erreurs non-bloquante
- [x] 2.9 Implémenter la boucle principale TTR : pour chaque bug, évaluer BREACH / seuils 50/75/90, anti-doublon clé `{key}_TTR_{seuil}`, reset, nettoyage si MET/No SLA
- [x] 2.10 Implémenter la boucle principale TTO : même logique avec `customfield_51130/51131`, clés `{key}_TTO_{seuil}`, destinataire Balthazar uniquement (pas l'assigné)
- [x] 2.11 Implémenter le commit git automatique de `sla_state.json` si modifié (via `subprocess`)
- [x] 2.12 Ajouter la validation des variables d'environnement requises au démarrage (`JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_BASE_URL`, `SLACK_BOT_TOKEN`)

## 3. Script report_sla.py — Rapport quotidien

- [x] 3.1 Réutiliser / factoriser la fonction `get_jira_bugs()` (extraction dans un module commun `jira_client.py` ou duplication acceptable)
- [x] 3.2 Implémenter `get_open_tickets()` : requête JQL `status = "Ouvert"`
- [x] 3.3 Implémenter `section_open_tickets(tickets)` : formatage Section 1 — tickets ouverts
- [x] 3.4 Implémenter `section_tto_active(bugs, now)` : formatage Section 2 — TTO en cours, trié par `customfield_51131.items[0].milliseconds` croissant
- [x] 3.5 Implémenter `section_ttr_active(bugs, now)` : formatage Section 3 — TTR en cours hors pause, trié par TTR restant croissant avec % écoulé
- [x] 3.6 Implémenter `section_sla_paused(bugs, now)` : formatage Section 4 — SLA en pause, durée calculée depuis `statuscategorychangedate`
- [x] 3.7 Implémenter `section_breached(bugs)` : formatage Section 5 — BREACH, trié par milliseconds le plus négatif en premier
- [x] 3.8 Implémenter `section_due_dates(bugs, now)` : formatage Section 6 — échéances proches avec marqueurs 🔴/🟠
- [x] 3.9 Implémenter `build_summary(...)` : ligne de synthèse + liste d'actions urgentes (TTR < 4h, breach > 7j, duedate < 3j)
- [x] 3.10 Implémenter l'envoi Slack : découpage du rapport en plusieurs messages si > 3000 caractères par bloc
- [x] 3.11 Ajouter la validation des variables d'environnement requises (`JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_BASE_URL`, `SLACK_BOT_TOKEN`)

## 4. GitHub Actions Workflows

- [x] 4.1 Créer `.github/workflows/sla-alert.yml` : cron `*/30 7-16 * * 1-5`, `workflow_dispatch`, checkout avec `fetch-depth: 0`, Python 3.11, `pip install requests`, exécution `check_sla.py`, secret `SLACK_BOT_TOKEN`, permission `contents: write`
- [x] 4.2 Créer `.github/workflows/sla-report.yml` : cron `0 7,12 * * 1-5`, `workflow_dispatch`, checkout, Python 3.11, `pip install requests`, exécution `report_sla.py`, secret `SLACK_BOT_TOKEN`, permission `contents: read`
- [x] 4.3 Vérifier la syntaxe YAML des deux workflows (indentation, secrets bien référencés)

## 5. Validation manuelle

- [x] 5.1 Configurer les 5 secrets dans GitHub Settings > Secrets and variables > Actions
- [ ] 5.2 Déclencher `sla-alert.yml` manuellement (`workflow_dispatch`) et vérifier le message Slack reçu
- [ ] 5.3 Déclencher `sla-report.yml` manuellement et vérifier le rapport Slack reçu
- [ ] 5.4 Vérifier que `sla_state.json` est bien commité après la première exécution de `check_sla.py`
- [ ] 5.5 Vérifier qu'une seconde exécution immédiate ne génère pas de doublon d'alerte
