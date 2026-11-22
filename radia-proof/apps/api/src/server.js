import 'dotenv/config';
import { config } from './config.js';
import { createApp } from './app.js';
import { loadSigner, SolanaProofClient } from './services/solana.js';
import { ProofStore } from './store/proofStore.js';

const signer = loadSigner(config);
const solanaClient = new SolanaProofClient({
  rpcUrl: config.rpcUrl,
  programId: config.programId,
  signer
});
const store = new ProofStore(config.proofStorePath);
await store.initialize();

const app = createApp({ config, store, solanaClient });
app.listen(config.port, () => {
  console.log(`Radia Proof API listening on http://localhost:${config.port}`);
  console.log(`Solana network: ${config.network}`);
  console.log(`Signer: ${solanaClient.signerPublicKey || 'not configured'}`);
});
