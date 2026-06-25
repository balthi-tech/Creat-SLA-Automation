## Context

Projet greenfield sur un repo GitHub dédié. Le board Jira CREAT (Jira Cloud, `edenred.atlassian.net`) utilise un plugin SLA tiers (non JSM natif) qui expose les données via des custom fields. Les SLA TTO et TTR sont calculés dynamiquement par le plugin à chaque appel API — les millisecondes restantes sont recalculées en tenant compte des horaires ouvrés, des jours fériés et des pauses de statut.

L'équipe n'a actuellement aucune visibilité automatisée. Les alertes doivent être envoyées sur Slack via Incoming Webhook.

## Goals / Non-Goals

**Goals:**
- Alerter sur Slack en quasi-temps-réel aux seuils 50/75/90% du TTR écoulé et en cas de BREACH
- Poster un rapport consolidé en 6 sections deux fois par jour (9h et 14h Paris, lun-ven)
- Anti-doublon strict : un seuil ne génère qu'une seule alerte par ticket (reset si SLA recalculé)
- Déploiement 100% GitHub Actions, sans infrastructure externe

**Non-Goals:**
- Calcul en heures ouvrées pour le % écoulé (approximation wall-clock acceptée — le plugin recalcule le remaining_ms en heures ouvrées, notre % est donc une approximation)
- Interface web ou dashboard
- Gestion des SLA TTO dans les alertes (seul TTR est tracké pour les alertes ; TTO apparaît dans le rapport)
- Notifications push, email, ou Teams

## Decisions

### D1 — Calcul de la deadline TTR via `remaining_ms` (pas de date fixe stockée)

Le plugin SLA recalcule dynamiquement les millisecondes restantes à chaque appel API, en tenant compte des pauses et des horaires ouvrés. On calcule donc :
```
target_date = now + timedelta(milliseconds=remaining_ms)
pct_elapsed = (now - created).total_seconds() / (target_date - created).total_seconds() * 100
```
**Pourquoi pas** : extraire une date fixe depuis les commentaires → fragile, dépend du format textuel du plugin.

### D2 — État des alertes dans `sla_state.json` commité dans le repo

Clé : `"{ticket_key}_{seuil}"` (ex: `"CREAT-123_75"`). Le fichier est lu au début de chaque run et commité à la fin si modifié.

**Pourquoi pas** : variable d'environnement ou artifact GitHub Actions → ne persiste pas entre les runs. Base de données externe → complexité inutile pour ce volume.

**Risque** : race condition si deux runners tournent simultanément. Mitigation : le cron est toutes les 30 min, le script tourne en ~10s — overlap très improbable.

### D3 — Deux scripts Python séparés (alerting vs rapport)

`check_sla.py` : logique d'alerting, tourne toutes les 30 min. `report_sla.py` : logique de rapport, tourne 2x/jour. Séparation des responsabilités, facilite le debug et l'évolution indépendante.

**Pourquoi pas** : un seul script avec flag — moins lisible, les deux logiques se polluent.

### D4 — Pause SLA détectée par le statut Jira (contient "attente")

Si `status.name.lower()` contient `"attente"`, le SLA est considéré en pause. On n'envoie pas d'alerte de progression (on envoie quand même les BREACH existants si applicable).

### D5 — DMs Slack via Bot Token (pas de Incoming Webhook)

Toutes les notifications sont des **DMs** envoyés via `chat.postMessage` de l'API Slack avec `channel: "{user_id}"`. Un Incoming Webhook ne peut poster que dans un canal fixe — il est donc inutilisable pour les DMs.

**Scopes Bot requis :** `chat:write`, `users.profile:read`

Secret GitHub : `SLACK_BOT_TOKEN` (`xoxb-...`).

### D6 — Pas de canal broadcast (pour l'instant)

Toutes les alertes (50/75/90%/BREACH, TTO et TTR) et le rapport quotidien partent uniquement en DM. Un canal `#creat-sla-alerts` pourra être ajouté ultérieurement.

### D7 — Détection vacation via Slack status API

L'API `users.profile.get` est appelée au début de chaque run pour vérifier le statut de Balthazar. Condition vacation : `status_emoji == ":palm_tree:"` OU `status_text` contient `"en vacances"` (insensible à la casse). En cas d'erreur API, fail-safe vers "disponible".

## Risks / Trade-offs

- **% wall-clock vs heures ouvrées** → La divergence est acceptable pour l'alerting (quelques heures d'écart max). Documenté dans le rapport.
- **sla_state.json commité** → GitHub peut désactiver les crons sur repos inactifs après 60 jours sans commit. Mitigation : le commit de `sla_state.json` à chaque run maintient le repo actif.
- **Secrets GitHub requis** → Si un secret est absent ou expiré, le script échoue silencieusement. Mitigation : le workflow GitHub Actions log l'erreur dans les annotations. Remplacer `SLACK_WEBHOOK_URL` par `SLACK_BOT_TOKEN`.
- **Volume de tickets** → L'API Jira pagine à 50 résultats par défaut. Si le board dépasse 50 bugs actifs, il faut paginer. Mitigation : le script doit gérer la pagination (`startAt` + `maxResults`).

## Open Questions

- Faut-il un seuil d'alerte sur le TTO également, ou uniquement le TTR ?
- La mention `<!here>` doit-elle cibler un utilisateur Slack spécifique plutôt que tout le canal ?
- Doit-on ignorer les tickets de priorité P5 pour les alertes ?
