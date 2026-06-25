## ADDED Requirements

### Requirement: Collecte des données pour le rapport

Le système SHALL effectuer deux requêtes JQL pour générer le rapport :

1. **Tickets ouverts** : `project = CREAT AND status = "Ouvert" ORDER BY created DESC`
   - Champs : `summary, status, assignee, priority, issuetype, created`

2. **Bugs actifs** : `project = CREAT AND issuetype = Bug AND status not in (Done, Closed, Resolved, "To Deploy PROD") ORDER BY created DESC`
   - Champs : `summary, status, assignee, priority, created, statuscategorychangedate, duedate, customfield_51129, customfield_51130, customfield_51131, customfield_51132, customfield_47323, customfield_13393`

Les deux requêtes MUST gérer la pagination.

#### Scenario: Collecte complète

- **WHEN** le script est déclenché
- **THEN** les deux requêtes JQL sont exécutées et tous les tickets sont chargés en mémoire avant de générer le rapport

---

### Requirement: Section 1 — Tickets ouverts

Le rapport SHALL inclure une section listant les tickets au statut "Ouvert".

Colonnes : clé (lien Jira), résumé, type, priorité, assigné.

#### Scenario: Tickets ouverts présents

- **WHEN** la requête retourne au moins un ticket au statut "Ouvert"
- **THEN** la section affiche un tableau avec un ticket par ligne

#### Scenario: Aucun ticket ouvert

- **WHEN** la requête ne retourne aucun ticket
- **THEN** la section affiche "Aucun ticket ouvert."

---

### Requirement: Section 2 — TTO en cours

Le rapport SHALL lister les bugs dont `customfield_51130 == "IN PROGRESS"`, triés par TTO restant croissant (`customfield_51131.items[0].milliseconds`).

Colonnes : clé, résumé, priorité, assigné, TTO restant (`formattedDurationString`), date limite calculée (`now + remaining_ms`).

#### Scenario: TTO en cours présents

- **WHEN** au moins un bug a `customfield_51130 == "IN PROGRESS"`
- **THEN** ces tickets sont listés du TTO le plus court au plus long

#### Scenario: Aucun TTO en cours

- **WHEN** aucun bug n'est en TTO actif
- **THEN** la section affiche "Aucun TTO en cours."

---

### Requirement: Section 3 — TTR en cours

Le rapport SHALL lister les bugs dont `customfield_51132 == "IN PROGRESS"` ET dont le statut Jira ne contient pas `"attente"`, triés par TTR restant croissant.

Colonnes : clé, résumé, priorité, assigné, TTR restant (`formattedDurationString`), date limite calculée, % écoulé.

#### Scenario: TTR en cours présents (hors pause)

- **WHEN** des bugs sont en TTR actif et non en pause
- **THEN** ces tickets apparaissent triés du TTR le plus court au plus long avec le % écoulé

#### Scenario: Aucun TTR en cours

- **WHEN** aucun bug n'est en TTR actif hors pause
- **THEN** la section affiche "Aucun TTR en cours."

---

### Requirement: Section 4 — SLA en pause

Le rapport SHALL lister les bugs dont le statut Jira contient `"attente"`.

Colonnes : clé, résumé, priorité, assigné, en pause depuis (`statuscategorychangedate`), durée de pause calculée (`now - statuscategorychangedate`), TTR gelé (`formattedDurationString`).

#### Scenario: Tickets en pause présents

- **WHEN** au moins un bug a un statut contenant "attente"
- **THEN** ces tickets sont listés avec la durée de pause calculée dynamiquement

#### Scenario: Aucun ticket en pause

- **WHEN** aucun bug n'est en pause
- **THEN** la section affiche "Aucun SLA en pause."

---

### Requirement: Section 5 — SLA BREACHED

Le rapport SHALL lister les bugs dont `customfield_51132 == "BREACHED"`, triés du dépassement le plus ancien (milliseconds le plus négatif en premier).

Colonnes : clé, résumé, priorité, assigné, dépassement (valeur absolue de `formattedDurationString`), statut courant (actif ou en pause).

#### Scenario: SLA breached présents

- **WHEN** au moins un bug est en BREACH
- **THEN** ces tickets sont listés du plus ancien breach au plus récent

#### Scenario: Aucun BREACH

- **WHEN** aucun bug n'est breached
- **THEN** la section affiche "Aucun SLA breached."

---

### Requirement: Section 6 — Échéances proches

Le rapport SHALL lister les tickets dont `duedate` est non-null, triés par date croissante, avec des marqueurs visuels :
- 🔴 si `duedate - today < 3 jours`
- 🟠 si `3 jours <= duedate - today < 7 jours`

#### Scenario: Échéances proches présentes

- **WHEN** au moins un ticket a une `duedate` renseignée
- **THEN** les tickets sont listés avec le marqueur coloré et le nombre de jours restants

#### Scenario: Aucune échéance renseignée

- **WHEN** aucun ticket n'a de `duedate`
- **THEN** la section affiche "Aucune échéance renseignée."

---

### Requirement: Synthèse finale et actions urgentes

Le rapport SHALL se terminer par une ligne de synthèse au format :
`X tickets ouverts · Y TTO actifs · Z TTR actifs · N en pause · M BREACHED · P échéances`

Suivie d'une liste d'actions urgentes pour les tickets répondant à au moins un des critères :
- TTR restant < 4h
- BREACH depuis > 7 jours
- Duedate dans < 3 jours

#### Scenario: Actions urgentes présentes

- **WHEN** au moins un ticket répond à un critère d'urgence
- **THEN** la synthèse liste ces tickets avec leur critère d'urgence

#### Scenario: Aucune action urgente

- **WHEN** aucun ticket ne répond aux critères d'urgence
- **THEN** la synthèse affiche "Aucune action urgente."

---

### Requirement: Envoi du rapport sur Slack

Le rapport complet SHALL être posté sur Slack via le même Incoming Webhook que les alertes, en utilisant le format Block Kit.

Le rapport MUST être découpé en plusieurs messages Slack si le contenu dépasse la limite de 3000 caractères par bloc.

#### Scenario: Rapport posté avec succès

- **WHEN** le script se termine normalement
- **THEN** le rapport est posté sur Slack et chaque section est lisible

#### Scenario: Rapport vide (aucun ticket)

- **WHEN** les deux requêtes JQL ne retournent aucun résultat
- **THEN** un message minimal est posté indiquant "Aucun ticket à reporter."
