import path from 'node:path';

const projectRoot = path.resolve(import.meta.dirname, '../../..');

export const config = {
  nodeEnv: process.env.NODE_ENV || 'development',
  port: Number(process.env.PORT || 5001),
  corsOrigin: process.env.CORS_ORIGIN || 'http://localhost:5173',
  rpcUrl: process.env.SOLANA_RPC_URL || 'https://api.devnet.solana.com',
  network: process.env.SOLANA_NETWORK || 'devnet',
  programId: process.env.SOLANA_PROGRAM_ID || '8Hh439HNMKGRTD1gmnifrJ2RrP6y8PsKwHRRQyponubt',
  privateKey: process.env.SOLANA_PRIVATE_KEY || '',
  keypairPath: process.env.SOLANA_KEYPAIR_PATH
    ? path.resolve(projectRoot, process.env.SOLANA_KEYPAIR_PATH)
    : path.join(projectRoot, 'devnet-keypair.json'),
  proofStorePath: process.env.PROOF_STORE_PATH
    ? path.resolve(projectRoot, process.env.PROOF_STORE_PATH)
    : path.join(projectRoot, 'data/proofs.json'),
  maxAudioSizeBytes: Number(process.env.MAX_AUDIO_SIZE_MB || 50) * 1024 * 1024
};

if (config.network !== 'devnet') {
  throw new Error('This project is intentionally restricted to Solana devnet.');
}
