## ADDED Requirements

### Requirement: Récupération des bugs actifs depuis Jira

Le système SHALL interroger l'API Jira Cloud avec la requête JQL suivante :
`project = CREAT AND issuetype = Bug AND status not in (Done, Closed, Resolved, "To Deploy PROD") ORDER BY created DESC`

Les champs récupérés MUST inclure : `summary, status, assignee, priority, created, statuscategorychangedate, customfield_51129, customfield_51130, customfield_51131, customfield_51132`.

Le système SHALL gérer la pagination Jira (paramètres `startAt` / `maxResults`) pour récupérer tous les tickets, même si leur nombre dépasse 50.

#### Scenario: Récupération paginée

- **WHEN** l'API retourne `total > maxResults`
- **THEN** le script effectue plusieurs appels successifs jusqu'à avoir récupéré tous les tickets

#### Scenario: Authentification échouée

- **WHEN** les credentials Jira sont invalides ou absents
- **THEN** le script lève une exception avec un message d'erreur explicite et se termine avec un code de sortie non-zéro

---

### Requirement: Mapping Jira email → Slack User ID

Le système SHALL utiliser un dictionnaire de correspondance codé en dur dans le script pour résoudre l'assignee Jira vers un Slack User ID :

```python
JIRA_TO_SLACK = {
    "balthazar.roque@consulting-for.edenred.com": "U039GQLN3EK",
    "julien.blatecky@consulting-for.edenred.com": "U047YNMN6",
    "johan.dufau@consulting-for.edenred.com":     "U047ZTJ5J",
    "sylviane.tran@consulting-for.edenred.com":   "UCRGT6DGE",
    "louan.bengmah@consulting-for.edenred.com":   "U04J01NACP5",
    "thibault.vlacich@consulting-for.edenred.com":"U0D6GEBHQ",
}
BALTHAZAR_SLACK_ID = "U039GQLN3EK"
JULIEN_SLACK_ID    = "U047YNMN6"
JOHAN_SLACK_ID     = "U047ZTJ5J"
```

Si l'email de l'assignee n'est pas dans le dictionnaire, le DM à l'assigné est ignoré (sans erreur).

#### Scenario: Assigné connu dans le mapping

- **WHEN** `assignee.emailAddress` existe dans `JIRA_TO_SLACK`
- **THEN** le DM est envoyé à l'User ID correspondant

#### Scenario: Assigné inconnu dans le mapping

- **WHEN** `assignee.emailAddress` n'est pas dans `JIRA_TO_SLACK`
- **THEN** le script continue sans envoyer de DM assigné, sans lever d'erreur

---

### Requirement: Détection du statut vacation de Balthazar

Au début de chaque exécution, le système SHALL appeler l'API Slack `users.profile.get` avec le User ID `U039GQLN3EK` pour vérifier le statut de vacation.

Balthazar est considéré **en vacances** si :
- `profile.status_emoji` est `":palm_tree:"` **ET/OU**
- `profile.status_text` contient `"En vacances"` (insensible à la casse)

Quand Balthazar est en vacances, les alertes qui lui seraient destinées MUST être redirigées vers **Julien (`U047YNMN6`) ET Johan (`U047ZTJ5J`) simultanément**.

#### Scenario: Balthazar disponible

- **WHEN** le statut Slack de Balthazar ne contient ni 🌴 ni "En vacances"
- **THEN** toutes les alertes TTO/TTR lui sont envoyées en DM

#### Scenario: Balthazar en vacances

- **WHEN** `status_emoji == ":palm_tree:"` ou `status_text` contient `"en vacances"`
- **THEN** les DMs partent à Julien ET Johan à la place de Balthazar

#### Scenario: Erreur API Slack lors de la vérification statut

- **WHEN** l'appel `users.profile.get` échoue (timeout, token invalide)
- **THEN** le script suppose que Balthazar est disponible et continue normalement (fail-safe)

---

### Requirement: Calcul du % TTR écoulé

Pour chaque ticket dont `customfield_51132 == "IN PROGRESS"`, le système SHALL calculer le pourcentage de TTR écoulé via la formule wall-clock :

```
remaining_ms = customfield_51129.items[0].milliseconds
target_date  = now + timedelta(milliseconds=remaining_ms)
pct_elapsed  = (now - created).total_seconds() / (target_date - created).total_seconds() * 100
```

`remaining_ms` peut être négatif si le SLA est déjà breached mais toujours marqué IN PROGRESS.

#### Scenario: TTR en cours, seuil non atteint

- **WHEN** `customfield_51132 == "IN PROGRESS"` et `pct_elapsed < 50`
- **THEN** aucune alerte n'est envoyée

#### Scenario: TTR en cours, seuil 50% atteint

- **WHEN** `customfield_51132 == "IN PROGRESS"` et `50 <= pct_elapsed < 75`
- **THEN** un DM Slack de niveau 50% est envoyé à Balthazar (ou fallback) ET à l'assigné du ticket (si pas déjà envoyé)

#### Scenario: TTR en cours, seuil 75% atteint

- **WHEN** `customfield_51132 == "IN PROGRESS"` et `75 <= pct_elapsed < 90`
- **THEN** un DM Slack de niveau 75% est envoyé à Balthazar (ou fallback) ET à l'assigné du ticket (si pas déjà envoyé)

#### Scenario: TTR en cours, seuil 90% atteint

- **WHEN** `customfield_51132 == "IN PROGRESS"` et `pct_elapsed >= 90`
- **THEN** un DM Slack de niveau 90% est envoyé à Balthazar (ou fallback) ET à l'assigné du ticket (si pas déjà envoyé)

---

### Requirement: Alertes TTO

Pour chaque ticket dont `customfield_51130 == "IN PROGRESS"`, le système SHALL calculer le % TTO écoulé de la même façon (via `customfield_51131.items[0].milliseconds`) et envoyer des DMs aux mêmes seuils (50%, 75%, 90%, BREACH).

Les alertes TTO sont envoyées **uniquement à Balthazar** (ou Julien+Johan si vacation). L'assigné du ticket ne reçoit PAS les alertes TTO.

#### Scenario: TTO seuil 50% atteint

- **WHEN** `customfield_51130 == "IN PROGRESS"` et TTO `pct_elapsed >= 50`
- **THEN** un DM TTO est envoyé à Balthazar (ou fallback), pas à l'assigné

#### Scenario: TTO BREACHED

- **WHEN** `customfield_51130 == "BREACHED"`
- **THEN** un DM BREACH TTO est envoyé à Balthazar (ou fallback) uniquement

---

### Requirement: Détection et alerte BREACH TTR

Pour chaque ticket dont `customfield_51132 == "BREACHED"`, le système SHALL envoyer un DM de niveau BREACH à Balthazar (ou fallback) ET à l'assigné.

#### Scenario: Nouveau BREACH TTR détecté

- **WHEN** `customfield_51132 == "BREACHED"` et aucune alerte BREACH n'a encore été envoyée pour ce ticket
- **THEN** des DMs BREACH sont envoyés à Balthazar (ou fallback) ET à l'assigné, et l'état `"{key}_BREACHED"` est enregistré dans `sla_state.json`

#### Scenario: BREACH déjà alerté

- **WHEN** `customfield_51132 == "BREACHED"` et l'état `"{key}_BREACHED"` existe déjà dans `sla_state.json`
- **THEN** aucun nouveau DM n'est envoyé

---

### Requirement: Anti-doublon via sla_state.json

Le système SHALL maintenir un fichier `sla_state.json` à la racine du repo contenant les alertes déjà envoyées, sous la forme `{"CREAT-123_TTR_50": true, "CREAT-123_TTO_75": true, ...}`.

Les clés incluent le type de SLA (`TTR` ou `TTO`) pour éviter les collisions : `"{key}_TTR_{seuil}"` et `"{key}_TTO_{seuil}"`.

Le fichier MUST être lu au début de chaque exécution et commité (via `git commit`) à la fin si son contenu a changé.

#### Scenario: Alerte déjà envoyée

- **WHEN** la clé `"{ticket_key}_TTR_{seuil}"` existe dans `sla_state.json`
- **THEN** aucun nouveau DM n'est envoyé pour ce ticket à ce seuil TTR

#### Scenario: Commit automatique de l'état

- **WHEN** au moins une alerte a été envoyée ou au moins un état a été nettoyé
- **THEN** le fichier `sla_state.json` est commité dans le repo avec le message `"chore: update sla_state.json [skip ci]"`

---

### Requirement: Reset automatique si SLA recalculé

Si un ticket repasse sous un seuil déjà alerté (ex: après une pause longue recalculée), le système SHALL supprimer l'entrée correspondante de `sla_state.json`.

#### Scenario: Reset d'un seuil supérieur non encore atteint

- **WHEN** `pct_elapsed < 75` et l'état `"{key}_TTR_75"` existe dans `sla_state.json`
- **THEN** l'entrée `"{key}_TTR_75"` est supprimée de `sla_state.json`

#### Scenario: Nettoyage complet si ticket terminé

- **WHEN** `customfield_51132` est `"MET"` ou `"No SLA"` ET `customfield_51130` est `"MET"` ou `"No SLA"`
- **THEN** toutes les entrées `"{key}_TTR_*"` et `"{key}_TTO_*"` sont supprimées de `sla_state.json`

---

### Requirement: Pas d'alerte de progression pendant une pause SLA

Le système SHALL considérer qu'un SLA est en pause si `status.name.lower()` contient `"attente"`.

Pendant la pause, les alertes de progression (50/75/90%) ne doivent PAS être envoyées. Les alertes BREACH déjà existantes ne sont pas supprimées.

#### Scenario: Ticket en attente, seuil atteint

- **WHEN** `customfield_51132 == "IN PROGRESS"` et `pct_elapsed >= 50` et `status.name.lower()` contient `"attente"`
- **THEN** aucun DM n'est envoyé

#### Scenario: Ticket sort d'une pause, seuil toujours atteint

- **WHEN** le statut ne contient plus `"attente"` et `pct_elapsed >= 50` et la clé d'alerte n'existe pas dans `sla_state.json`
- **THEN** le DM correspondant est envoyé

---

### Requirement: Format des messages Slack DM (Block Kit)

Chaque DM d'alerte SHALL utiliser le format `attachments` avec `color` et des `blocks` structurés.
Les DMs sont envoyés via `chat.postMessage` de l'API Slack avec `channel: "{slack_user_id}"`.

| Seuil        | Couleur    | Contexte du DM                          |
|--------------|------------|-----------------------------------------|
| TTO/TTR 50%  | `#eab308`  | Informatif                              |
| TTO/TTR 75%  | `#f97316`  | Avertissement                           |
| TTO/TTR 90%  | `#dc2626`  | Urgent                                  |
| BREACHED     | `#7f1d1d`  | Critique                                |

Les champs MUST inclure : ticket (lien cliquable vers Jira), résumé, priorité, assigné, type de SLA (TTO ou TTR), % écoulé, deadline calculée.

#### Scenario: DM bien formé pour TTR 90%

- **WHEN** une alerte TTR 90% est envoyée
- **THEN** le payload `chat.postMessage` contient `channel: "U039GQLN3EK"` (ou fallback), `color: "#dc2626"`, et un lien `https://edenred.atlassian.net/browse/{key}`

#### Scenario: Erreur envoi DM non-bloquante

- **WHEN** l'API Slack retourne un statut HTTP non-2xx pour un DM
- **THEN** le script logue l'erreur et continue avec les tickets suivants
