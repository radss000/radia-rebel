import fs from 'node:fs';
import path from 'node:path';
import { Keypair } from '@solana/web3.js';

const outputPath = path.resolve('devnet-keypair.json');
if (fs.existsSync(outputPath)) {
  console.error(`Refusing to overwrite existing keypair: ${outputPath}`);
  process.exit(1);
}

const keypair = Keypair.generate();
fs.writeFileSync(outputPath, `${JSON.stringify(Array.from(keypair.secretKey))}\n`, { mode: 0o600 });
console.log(`Created ${outputPath}`);
console.log(`Public key: ${keypair.publicKey.toBase58()}`);
console.log(`Fund it with: solana airdrop 1 ${keypair.publicKey.toBase58()} --url devnet`);
