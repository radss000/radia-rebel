# Radia Proof

Application autonome de preuve d’antériorité audio sur **Solana devnet**. Le projet contient l’interface web, le backend, le programme Anchor, les tests et un scénario E2E réel.

## Ce que fait le projet

1. L’utilisateur sélectionne un fichier audio dans l’interface.
2. Le backend calcule son empreinte SHA-256 en mémoire. Le fichier audio n’est pas conservé.
3. Le backend signe une transaction devnet avec un portefeuille de service.
4. Le programme Anchor crée une PDA déterministe à partir de :
   - `proof-of-creation` ;
   - la clé publique du signataire ;
   - l’empreinte SHA-256 de 32 octets.
5. Le compte on-chain stocke la clé publique, l’empreinte et le timestamp Solana.
6. L’interface permet de recharger un fichier et de vérifier simultanément son hash et le compte on-chain.

## Architecture

```text
apps/web/                  React + Vite UI
apps/api/                  Express API, Solana client, JSON persistence
programs/timestamp_proof/  Anchor program
tests/                     Anchor local-validator test
scripts/                   Keypair and real devnet E2E scripts
data/                      Local proof metadata registry
```

Le contenu audio ne part sur Solana et n’est pas écrit sur disque. Seuls le hash, la clé publique et le timestamp sont on-chain. Le registre JSON local garde les informations d’affichage et les identifiants de transaction.

## Prérequis

- Node.js 20 ou 22 ;
- npm 10+ ;
- Solana CLI pour financer le portefeuille devnet ;
- Anchor CLI 0.31.1 uniquement pour compiler ou redéployer le programme ;
- environ 0,1 SOL devnet pour les transactions de test.

## Démarrage local

```bash
npm install
cp .env.example .env
npm run keypair:generate
solana airdrop 1 "$(solana-keygen pubkey devnet-keypair.json)" --url devnet
npm run dev
```

- UI : `http://localhost:5173`
- API : `http://localhost:5001`
- Santé devnet : `http://localhost:5001/api/health`

Si le faucet public refuse l’airdrop, financez la clé affichée par `npm run keypair:generate` depuis un autre portefeuille devnet.

## Configuration

Copiez `.env.example` vers `.env`.

| Variable | Utilité |
| --- | --- |
| `SOLANA_RPC_URL` | RPC Solana devnet |
| `SOLANA_PROGRAM_ID` | Programme de preuve déployé |
| `SOLANA_KEYPAIR_PATH` | Fichier JSON du signataire de service |
| `SOLANA_PRIVATE_KEY` | Alternative base58 au fichier keypair |
| `PROOF_STORE_PATH` | Registre JSON local |
| `CORS_ORIGIN` | Origine autorisée de l’UI |
| `MAX_AUDIO_SIZE_MB` | Limite d’upload en mémoire |

Ne commitez jamais `.env`, `devnet-keypair.json` ou une clé privée. Une clé présente dans un ancien dépôt doit être considérée compromise et remplacée.

## API

### Créer une preuve

```bash
curl -X POST http://localhost:5001/api/proofs \
  -F 'title=My track' \
  -F 'artistName=My artist' \
  -F 'audioFile=@./track.wav'
```

### Lister les preuves

```bash
curl http://localhost:5001/api/proofs
```

### Vérifier un fichier

```bash
curl -X POST http://localhost:5001/api/proofs/PROOF_ID/verify \
  -F 'audioFile=@./track.wav'
```

La réponse expose séparément `hashMatches` et `chainMatches`. `verified` n’est vrai que si les deux contrôles réussissent.

## Tests

Tests unitaires du backend et build UI :

```bash
npm test
npm run build
```

Parcours réel sur devnet, API démarrée et portefeuille financé :

```bash
npm run test:e2e
```

Le script génère un WAV de test, crée une preuve sur devnet, relit la PDA et vérifie le même fichier via l’API.

Test du programme avec validateur local :

```bash
npm run anchor:build
npm run anchor:test
```

## Déploiement du programme

Le programme configuré par défaut est :

```text
8Hh439HNMKGRTD1gmnifrJ2RrP6y8PsKwHRRQyponubt
```

Pour déployer votre propre programme, créez un nouveau program keypair, synchronisez `declare_id!`, `Anchor.toml` et `SOLANA_PROGRAM_ID`, puis lancez :

```bash
solana config set --url devnet
anchor build
anchor deploy --provider.cluster devnet
```

Changer uniquement `SOLANA_PROGRAM_ID` sans reconstruire le programme produit un client incompatible.

## Docker

Après création et financement de `devnet-keypair.json` :

```bash
cp .env.example .env
docker compose up --build
```

Le volume `data/` conserve le registre du backend. Le keypair est monté en lecture seule.

## Limites et production

- Devnet uniquement : aucune valeur financière réelle.
- Le portefeuille de service est dépositaire. Pour une version non-custodiale, la transaction doit être construite par l’API puis signée par un wallet utilisateur dans l’UI.
- Le registre JSON convient à une instance unique. En production multi-instance, remplacez `ProofStore` par PostgreSQL.
- Ajoutez authentification, rate limiting, observabilité et stockage de secrets managé avant exposition publique.
