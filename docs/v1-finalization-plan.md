# REBEL — Plan de finalisation V1

Date de référence : 3 août 2026

## Objectif de la V1

Livrer une version exploitable de REBEL dans laquelle :

- chaque track analysable possède un embedding CLAP versionné ;
- les tracks similaires sont classées directement par similarité cosinus dans l'espace CLAP ;
- la carte 3D représente fidèlement les voisinages locaux sans être présentée comme une mesure exacte ;
- l'ingestion, l'analyse, la recherche de similarité et l'affichage 3D sont couverts par des tests automatisés ;
- l'interface permet de comprendre pourquoi deux tracks sont rapprochées ;
- les erreurs et fallbacks sont visibles, mesurables et récupérables.

## Définition de « accurate »

La V1 sépare deux notions :

1. **Similarité ADN** : score cosinus exact entre embeddings CLAP 512D, utilisé pour le classement et l'API.
2. **Proximité 3D** : projection UMAP destinée à l'exploration visuelle, validée par sa conservation des voisins mais jamais utilisée comme score de vérité.

La V1 est considérée accurate lorsque :

- une track ne peut jamais être son propre voisin ;
- les résultats de similarité sont déterministes pour un catalogue et un modèle donnés ;
- tous les résultats exposent le score, le modèle et la version de l'embedding ;
- la médiane du rappel des 10 voisins CLAP dans les 10 à 15 voisins 3D atteint au moins 70 % sur le corpus de validation ;
- la trustworthiness UMAP à `k=10` atteint au moins 0,90 sur le corpus de validation ;
- les seuils « proche » et « très proche » sont calibrés sur les scores réels du catalogue et non codés arbitrairement ;
- les positions fallback sont explicitement distinguées des positions issues de CLAP.

## État initial constaté

- L'extraction du segment central, CLAP, Qdrant et UMAP sont présents.
- Les tests de positionnement passent lorsqu'ils sont exécutés isolément.
- La suite combinée ralentit fortement car l'extracteur audio désactive globalement Numba JIT avant le chargement d'UMAP.
- L'endpoint `/similar` n'existe pas encore.
- Le positionnement approximatif peut inclure la track cible et des positions nulles parmi ses voisins.
- Les similarités négatives peuvent actuellement devenir des poids de positionnement.
- Les fallbacks audio et les positions CLAP cohabitent sans distinction produit suffisamment claire.
- La Sonic Map est encore séparée de l'expérience React principale et ne présente pas de score ADN explicable.

## Phase 1 — Stabiliser le runtime

### Travaux

- Retirer la modification globale de `NUMBA_DISABLE_JIT` des modules partagés.
- Isoler les éventuels contournements Librosa sans affecter UMAP dans le même worker.
- Réduire les allocations mémoire des tests audio longs.
- Vérifier le comportement avec 30, 1 000 et 5 000 embeddings.
- Séparer les workers audio/embedding et positionnement si l'isolation en processus unique reste fragile.
- Uniformiser la configuration CLAP entre `.env`, `.env.example` et les métadonnées stockées.

### Critères d'acceptation

- Les 8 tests existants terminent dans un même processus.
- Le test UMAP à 1 000 embeddings termine en moins de 60 secondes sur la machine de référence.
- Aucun module audio ne modifie globalement le runtime d'un module de positionnement.
- Le worker peut enchaîner `audio_features → embedding → position` sans fuite mémoire manifeste.

### État au 22 novembre 2026 (branche `phase1-runtime-stabilization`)

- [x] Plus aucune modification globale de `NUMBA_DISABLE_JIT` ; un test le vérifie.
- [x] UMAP, scikit-learn et librosa sont importés à la demande ; la collecte pytest passe d'environ 50 s à moins de 2 s.
- [x] Les 35 tests hors `phase6_legacy` passent dans un même processus (environ 17 s avec les caches chauds).
- [x] UMAP : 30 embeddings en 11 s (compilation numba au premier appel), 1 000 en 2,4 s, 5 000 en 45 s (pic à 1,2 Go).
- [x] Chargement audio par soundfile + soxr, identique à librosa, y compris pour les WAV 24 bits et float.
- [x] Configuration CLAP alignée entre les deux `.env.example`.
- [x] Le module `processing/audio_assets/` est désormais versionné (il était exclu par `.gitignore`).
- [x] Chaîne du worker avec le vrai modèle CLAP (MacBook, 11 morceaux FLAC réels, 3 passes) : mémoire stable à 1 456 Mo, +0 Mo après échauffement. Médiane par morceau : caractéristiques audio 4,75 s, segment central + embedding 1,08 s.
- Constats à traiter dans les phases suivantes :
  - Le chargement de CLAP a pris 1 024 s, probablement parce que le checkpoint est sur un Bureau synchronisé par iCloud et non téléchargé. En développement, garder `checkpoints/` hors d'iCloud ; en production, l'intégrer à l'image ou au volume.
  - Ce sont les caractéristiques audio qui ralentissent le worker (environ 4 fois plus longues que l'embedding) : elles analysent le morceau entier à 22 050 Hz.
  - Intel OpenMP (torch) et LLVM OpenMP (scikit-learn/UMAP) sont chargés dans le même processus, avec un risque de blocage ou de crash. Cela justifie de séparer les workers embedding et positionnement.
- [ ] Réécrire les tests `test_phase6_*`, exclus par défaut (marqueur `phase6_legacy`), contre les vraies API (phase 6).
- Point de vigilance : à 5 000 embeddings synthétiques, le rappel des voisins tombe à 0,37, juste au-dessus du seuil provisoire de 0,35. La calibration de la phase 4 est prioritaire.

### État au 22 novembre 2026 : parcours de bout en bout réel (branche `phase2-e2e-ci`)

- [x] Test E2E sans mock (`music-pipeline/tests/e2e`) : 12 morceaux générés et servis en local, ingestion → preview → features → CLAP/Qdrant → position → `/similar` → `/sonic-map` → `/version`. Il passe sur une stack vierge, en local et dans GitHub Actions (`music-pipeline.yml`, avec le vrai checkpoint CLAP).
- [x] Workers séparés : `analysis` (CLAP) et `positioning` (UMAP), chaînés par RQ `depends_on` ; un échec marque les étapes suivantes comme échouées.
- [x] Bugs corrigés grâce au parcours réel :
  - ingestion par URL directe (`other`) sans adaptateur : `preview_fetch` échouait toujours ;
  - `ON CONFLICT (track_id)` sur `embeddings` sans index unique sur une base neuve (migration `20261122_embeddings_track_unique.sql`) ;
  - blocage du worker de positionnement sur lui-même (transaction de lecture ouverte plus `ALTER TABLE`) au premier job après chaque démarrage ;
  - `docker-compose.yml` fixé à Qdrant 1.7.4, incompatible avec `query_points` : passage à 1.12.6.
- [x] Option `AUDIO_FEATURES_SOURCE=core` (environ 4,5 fois plus rapide, désactivée par défaut).
- Constat : avec le seuil de production (trustworthiness ≥ 0,90), une carte de 12 morceaux est toujours rejetée et tous les morceaux restent en `features_fallback`. Un petit catalogue n'aura donc jamais de carte CLAP tant que la calibration (phase 4) n'est pas faite.

## Phase 2 — Finaliser l'API de similarité

### Contrat proposé

`GET /api/tracks/{track_id}/similar?limit=10&min_score=0`

Chaque résultat retourne :

- `track_id`, `title`, `artist` et métadonnées d'affichage ;
- `similarity_score` cosinus fourni par Qdrant ;
- `rank` ;
- `model_name`, `model_version` et `vector_dimensions` ;
- `similarity_band` calibré (`very_close`, `close`, `related`, `weak`) ;
- `position_method` et distance 3D uniquement comme informations secondaires.

### Travaux

- Récupérer le point Qdrant de la track cible.
- Rechercher les voisins avec la métrique cosinus de la collection.
- Demander `limit + 1`, exclure explicitement la track cible et tronquer au `limit` demandé.
- Filtrer les embeddings incompatibles par modèle, version et dimension.
- Joindre les résultats aux métadonnées PostgreSQL sans requête N+1.
- Gérer les tracks, embeddings et points Qdrant absents avec des erreurs API explicites.
- Ajouter pagination bornée, validation des paramètres et temps maximal de requête.
- Proxifier la route via l'API Node et créer le service frontend associé.

### Critères d'acceptation

- La track cible n'apparaît jamais dans ses résultats.
- Les scores sont triés de manière décroissante et restent stables.
- Une incompatibilité de modèle ne produit pas un classement silencieusement invalide.
- Les cas 404, embedding absent et Qdrant indisponible sont testés.
- La latence cible est inférieure à 300 ms pour 5 000 tracks hors démarrage à froid.

## Phase 3 — Fiabiliser le positionnement 3D

### Travaux

- Exclure la track cible du calcul nearest-neighbor.
- Exclure toutes les tracks sans position CLAP valide.
- Ne conserver que les poids cosinus strictement positifs ou dépassant un seuil configuré.
- Ajouter un fallback explicite lorsque moins de voisins valides sont disponibles.
- Remplacer `pending` par des méthodes non ambiguës :
  - `clap_umap_full` ;
  - `clap_knn_approx` ;
  - `features_fallback` ;
  - `unpositioned`.
- Persister la version du modèle UMAP, ses paramètres, sa date de calcul et le catalogue source.
- Produire un recalcul atomique : calcul hors table active, validation, puis publication des nouvelles positions.
- Stabiliser les recalculs avec alignement sur des tracks ancres afin de limiter rotations et déplacements visuels.
- Calculer automatiquement le rappel des voisins et la trustworthiness après chaque recalcul complet.
- Refuser la publication d'une carte ne respectant pas les seuils de qualité.

### Critères d'acceptation

- Aucun voisin nul ou auto-voisin ne participe au calcul.
- Toutes les positions publiées possèdent une provenance et une version.
- Un recalcul interrompu ne corrompt pas la carte active.
- La qualité topologique respecte les seuils définis dans la section « accurate ».
- L'API de similarité reste la source de vérité indépendamment des positions 3D.

## Phase 4 — Construire le corpus de validation

### Corpus minimal

- Variantes ou extraits d'une même track.
- Tracks du même artiste et de productions proches.
- Tracks de genres voisins mais de timbres différents.
- Tracks de BPM similaires mais d'identité sonore différente.
- Tracks volontairement sans relation.
- Cas progressifs, ambient, techno, acoustiques et expérimentaux.

### Travaux

- Créer des fixtures audio courtes et reproductibles, sans dépendance réseau pendant les tests.
- Constituer des paires annotées `very_close`, `close`, `related`, `different`.
- Mesurer `precision@5`, `precision@10`, `recall@10`, distribution des scores et faux positifs.
- Calibrer les bandes de score à partir des percentiles et annotations humaines.
- Enregistrer le modèle, checkpoint, stratégie de segment et version du corpus pour chaque benchmark.

### Critères d'acceptation

- Le benchmark peut être reproduit localement par une commande documentée.
- Les seuils de proximité sont issus du benchmark et stockés en configuration versionnée.
- Toute modification du modèle ou de l'extraction produit un rapport comparatif avant déploiement.

## Phase 5 — UI et expérience 3D

### Architecture

- Intégrer la Sonic Map comme module maintenu de l'application React au lieu d'une expérience isolée difficile à synchroniser.
- Conserver Babylon.js pour le moteur 3D, avec une couche de données et d'état partagée avec React.
- Prévoir un mode dégradé 2D/liste lorsque WebGL ou la puissance GPU sont insuffisants.

### Expérience cible

- Carte plein écran avec chargement progressif et transition d'entrée fluide.
- Recherche instantanée d'une track, focus caméra et surbrillance de son voisinage.
- Panneau de comparaison affichant score ADN, rang, modèle, caractéristiques audio et provenance de position.
- Liens de voisinage limités aux résultats CLAP réellement proches, pas à une simple distance 3D arbitraire.
- Filtres par genre, énergie, BPM, méthode de positionnement et niveau de similarité.
- Lecture audio persistante pendant la navigation.
- Historique de navigation, favoris et partage d'une vue centrée sur une track.
- Légende claire expliquant que la carte est une projection et que le score ADN vient du 512D.
- Navigation clavier, réduction des animations, contrastes suffisants et interface mobile dédiée.

### Rendu et performance

- Utiliser instances/thin instances pour les grandes collections de sphères.
- Ajouter LOD, frustum culling et chargement différé des labels et connexions.
- Limiter les effets coûteux ; bloom, profondeur et particules doivent s'adapter au niveau GPU.
- Regrouper les mises à jour visuelles et éviter les recalculs React à chaque frame Babylon.
- Afficher les connexions uniquement pour la sélection et son voisinage immédiat.

### Critères d'acceptation

- 60 FPS cible sur desktop récent avec 5 000 tracks, 30 FPS minimum sur mobile compatible.
- Interaction disponible en moins de 3 secondes avec données déjà accessibles localement.
- Aucun blocage du thread principal supérieur à 100 ms pendant la navigation normale.
- Recherche, sélection, comparaison, lecture et filtres fonctionnent au clavier et au tactile.
- L'utilisateur peut identifier la source et la qualité de chaque rapprochement.

## Phase 6 — Tests automatisés

### Tests unitaires

- Extraction audio déterministe et bornée en mémoire.
- Similarité cosinus, exclusion de soi et filtrage des scores.
- Pondération KNN avec cas négatifs, nuls et voisins manquants.
- Normalisation UMAP et provenance des positions.
- Sérialisation des réponses API.

### Tests d'intégration

- PostgreSQL + Qdrant avec collection éphémère.
- Upsert d'embedding puis recherche de voisins.
- Recalcul complet et positionnement approximatif.
- Dégradation contrôlée lorsque Qdrant ou Redis est indisponible.

### Tests E2E

- Ingestion d'une fixture locale.
- `preview_fetch → audio_features → embedding → position`.
- Appel de `/similar` et vérification du classement.
- Chargement de la carte, recherche de la track et affichage des voisins.
- Lecture preview, filtres et navigation mobile.

### Tests visuels et performance

- Captures de référence desktop et mobile.
- Test de 100, 1 000 et 5 000 points.
- Budget FPS, mémoire, temps d'interaction et taille du bundle.
- Test WebGL indisponible et mode réduit.

## Phase 7 — Observabilité et release

### Travaux

- Journaliser les temps d'extraction, embedding, requête Qdrant et positionnement.
- Exposer les compteurs de jobs réussis, échoués, en attente et fallback.
- Ajouter un identifiant de version pour CLAP, UMAP, corpus et carte publiée.
- Ajouter une commande de healthcheck PostgreSQL, Redis, Qdrant et checkpoint CLAP.
- Documenter installation, démarrage, benchmark, backfill et rollback.
- Nettoyer et intégrer les fichiers actuellement non suivis par Git.
- Exécuter une migration et un backfill contrôlés sur une copie des données avant production.

### Portes de release

La V1 ne peut être marquée terminée que si :

- tous les tests unitaires, intégration et E2E passent dans un environnement propre ;
- le build frontend de production termine sans erreur ;
- le benchmark de similarité et les métriques 3D respectent les seuils ;
- aucune track cible ne ressort comme son propre voisin ;
- aucun fallback n'est présenté comme une position CLAP ;
- le parcours complet fonctionne sans dépendance à une recherche Internet lorsqu'une fixture locale est utilisée ;
- les procédures de migration, backfill et rollback ont été répétées ;
- une validation visuelle desktop et mobile est signée.

## Ordre d'exécution recommandé

1. Runtime et tests combinés.
2. Endpoint de similarité et contrat frontend.
3. Corrections KNN et provenance des positions.
4. Benchmark et calibration des seuils.
5. Refonte React/Babylon de la Sonic Map.
6. Tests E2E, visuels et performance.
7. Backfill, observabilité et release candidate.

## Estimation indicative

Pour une personne travaillant principalement sur ce périmètre :

- Phase 1 : 2 à 3 jours.
- Phase 2 : 3 à 4 jours.
- Phase 3 : 4 à 6 jours.
- Phase 4 : 3 à 5 jours, hors annotation humaine étendue.
- Phase 5 : 7 à 10 jours.
- Phases 6 et 7 : 5 à 7 jours.

Total indicatif : 4 à 6 semaines pour une V1 solide, mesurée et présentable, avec une release candidate intermédiaire après les phases 1 à 4.

## Hors périmètre V1

- Apprentissage d'un modèle propriétaire complet.
- Recommandation collaborative basée sur les utilisateurs.
- Génération musicale ou remix automatique.
- Support VR natif.
- Garantie que la distance euclidienne 3D reproduit exactement toutes les distances CLAP.
