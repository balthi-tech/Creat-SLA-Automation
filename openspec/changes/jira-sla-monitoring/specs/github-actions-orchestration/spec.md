## ADDED Requirements

### Requirement: Workflow d'alerting SLA (sla-alert.yml)

Un workflow GitHub Actions SHALL exister à `.github/workflows/sla-alert.yml` et se déclencher selon deux modes :
- **Cron** : toutes les 30 minutes, du lundi au vendredi, entre 7h00 et 16h00 UTC (≈ 9h-18h Paris heure d'été)
- **Manuel** : `workflow_dispatch` pour permettre un déclenchement ad hoc

Le workflow SHALL :
1. Checkout du repo (avec `fetch-depth: 0` pour permettre le commit de `sla_state.json`)
2. Configurer Python 3.11
3. Installer les dépendances (`requests`)
4. Exécuter `check_sla.py`
5. Configurer git (`user.email`, `user.name`) et commiter `sla_state.json` si modifié

#### Scenario: Exécution cron en semaine dans les heures ouvrées

- **WHEN** il est lundi 10h00 UTC
- **THEN** le workflow se déclenche et exécute `check_sla.py`

#### Scenario: Pas d'exécution le week-end

- **WHEN** il est samedi
- **THEN** le cron GitHub Actions ne se déclenche pas (grâce au filtre `1-5` sur les jours)

#### Scenario: Commit de sla_state.json absent si aucun changement

- **WHEN** `check_sla.py` ne modifie pas `sla_state.json`
- **THEN** le step git détecte qu'il n'y a rien à commiter et se termine sans erreur

---

### Requirement: Workflow de rapport quotidien (sla-report.yml)

Un workflow GitHub Actions SHALL exister à `.github/workflows/sla-report.yml` et se déclencher :
- **Cron** : deux fois par jour en semaine — 7h00 UTC (≈ 9h Paris) et 12h00 UTC (≈ 14h Paris), du lundi au vendredi
- **Manuel** : `workflow_dispatch`

Le workflow SHALL :
1. Checkout du repo
2. Configurer Python 3.11
3. Installer les dépendances (`requests`)
4. Exécuter `report_sla.py`

#### Scenario: Exécution à 9h Paris un jour de semaine

- **WHEN** il est lundi 7h00 UTC
- **THEN** le workflow `sla-report.yml` se déclenche et poste le rapport sur Slack

#### Scenario: Déclenchement manuel

- **WHEN** l'utilisateur clique "Run workflow" dans GitHub Actions
- **THEN** le workflow s'exécute immédiatement quelle que soit l'heure

---

### Requirement: Secrets GitHub requis

Les deux workflows SHALL utiliser les secrets GitHub suivants, injectés comme variables d'environnement dans les steps Python :

| Secret             | Usage                                          |
|--------------------|------------------------------------------------|
| `JIRA_EMAIL`       | Email du compte Jira pour l'authentification Basic Auth |
| `JIRA_API_TOKEN`   | Token API Jira (généré sur id.atlassian.com)   |
| `JIRA_CLOUD_ID`    | `0178e060-69f7-4d7f-afb3-03faafd8b4c2`         |
| `JIRA_BASE_URL`    | `https://edenred.atlassian.net`                |
| `SLACK_WEBHOOK_URL`| URL du webhook Slack Incoming (api.slack.com)  |

Les scripts Python MUST lire ces valeurs depuis `os.environ` et lever une exception explicite si une variable est absente.

#### Scenario: Secret manquant

- **WHEN** `JIRA_API_TOKEN` n'est pas configuré dans les secrets GitHub
- **THEN** le script lève une `EnvironmentError` avec le nom du secret manquant, le workflow échoue avec un code non-zéro visible dans l'interface GitHub Actions

#### Scenario: Tous les secrets présents

- **WHEN** les 5 secrets sont correctement configurés
- **THEN** les scripts s'exécutent sans erreur d'authentification

---

### Requirement: Permissions minimales du workflow

Les workflows SHALL utiliser des permissions minimales : `contents: write` uniquement pour `sla-alert.yml` (nécessaire pour commiter `sla_state.json`). `sla-report.yml` n'a besoin que de `contents: read`.

#### Scenario: sla-alert.yml commit sla_state.json

- **WHEN** `check_sla.py` modifie `sla_state.json`
- **THEN** le step git dispose des droits d'écriture via `GITHUB_TOKEN` avec permission `contents: write`
