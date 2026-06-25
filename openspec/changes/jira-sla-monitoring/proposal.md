## Why

Le board CREAT ne dispose d'aucune visibilité proactive sur l'état des SLA (TTO/TTR) des bugs. Les violations de SLA sont découvertes après coup, sans alerte automatique ni rapport consolidé, ce qui génère des retards et un risque de breaches non traités.

## What Changes

- Création d'un script Python `check_sla.py` qui interroge l'API Jira toutes les 30 minutes et envoie des alertes Slack aux seuils 50%, 75%, 90% du TTR écoulé et en cas de BREACH
- Création d'un script Python `report_sla.py` qui génère un rapport consolidé en 6 sections posté sur Slack deux fois par jour (9h et 14h Paris)
- Création de deux GitHub Actions workflows pour orchestrer ces scripts en cron
- Création d'un fichier `sla_state.json` pour tracker les alertes déjà envoyées et éviter les doublons

## Capabilities

### New Capabilities

- `sla-alerting`: Détection et notification Slack en temps quasi-réel des tickets Jira dont le TTR approche ou dépasse le seuil SLA, avec anti-doublon et reset automatique
- `sla-reporting`: Rapport quotidien complet (2x/jour) de l'état du board CREAT : tickets ouverts, TTO en cours, TTR en cours, SLA en pause, SLA breached, échéances proches
- `github-actions-orchestration`: Workflows GitHub Actions avec cron pour déclencher les scripts Python en semaine aux horaires ouvrés

### Modified Capabilities

_(Aucune — projet greenfield)_

## Impact

- **Nouveau repo** : projet greenfield, aucun code existant à modifier
- **API Jira Cloud** : lecture seule via Basic Auth (email + API token), endpoint `https://edenred.atlassian.net/rest/api/3/search`
- **Custom fields SLA** : `customfield_51129/51130/51131/51132` (plugin tiers, non natif JSM)
- **Slack** : envoi via Incoming Webhook (aucune dépendance SMTP ni OAuth)
- **Secrets GitHub** : `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_CLOUD_ID`, `JIRA_BASE_URL`, `SLACK_WEBHOOK_URL`
- **sla_state.json** : fichier d'état commité dans le repo — ne contient que des clés de tickets et seuils, aucune donnée sensible
