## 2025-11-02 · Audio previews & link enrichment

- Ajout d’un enrichissement multimédia dans `music-pipeline/scrapers/musicbrainz_crawler.py` : récupération Discogs (vidéos YouTube, Bandcamp), recherche Deezer (preview MP3 + lien), fallback YouTube Music via Piped, mise en cache et upsert atomique pour éviter les doublons.
- Exposition des nouvelles données via `music-pipeline/api/main.py` : chaque piste du Sonic Map renvoie désormais `preview_url` et un objet `links` (Bandcamp, YouTube, Deezer, Discogs).
- Lecture intelligente côté front (`public/sonic-map/index-new.html`) : priorisation des previews directs, intégration d’iframes YouTube/Deezer, fallback externe Bandcamp/Discogs, gestion des états play/pause et barre de progression, notifications cohérentes.
- Extension CSP dans `src/app.js` pour autoriser les embeddings audio (YouTube nocookie, widget Deezer) tout en conservant la sandbox REBEL.
- UI enrichie (`public/sonic-map/sonic-map-costar-styles.css`) : conteneur d’embed, badges de liens externes, styles désactivés quand aucun flux n’est disponible.

## 2025-11-02 · Refonte Sonic Map (agent design immersif)

- Implémentation d'une nouvelle charte sombre inspirée Co–Star pour `public/sonic-map/sonic-map-costar-styles.css` : dégradés galactiques, grille cosmique, typographies EB Garamond + IBM Plex Sans, capsules en verre dépoli et barres audio lumineuses.
- Harmonisation de l'univers 3D dans `public/sonic-map/index-new.html` : tone mapping, glow layer Babylon.js, éclairages atmosphériques, sphères réactives avec halos et outlines dynamiques.
- Amélioration de l'expérience utilisateur : cartes « Now Playing », HUD et notifications translucides, animations de focus et réinitialisation des états au close.
- Prise de rôle : gardien de l'esthétique REBEL (respect des visuels existants, immersion élégante, simplicité au service des artistes et des fans).
## 2025-11-02 · Sonic Map preview resilience

- Simplification du lecteur dans `public/sonic-map/index-new.html` : uniquement l’audio direct est lu en ligne, les sources YouTube/Deezer/Bandcamp ouvrent désormais un onglet externe avec message contextuel pour éviter les erreurs de permissions/auto-play.
- Ajout d’un placeholder UX (`preview-placeholder`) dans `public/sonic-map/sonic-map-costar-styles.css` pour informer l’utilisateur du statut du preview.
- Nettoyage des états du bouton Play/Pause et notifications afin d’éviter les iframes cassées et les warnings navigateur.
