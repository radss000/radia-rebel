import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { Keypair } from '@solana/web3.js';
import { decodeProofAccount } from '../src/services/solana.js';

test('decodeProofAccount reads the Anchor account layout', () => {
  const artist = Keypair.generate().publicKey;
  const hash = crypto.createHash('sha256').update('audio').digest();
  const discriminator = crypto
    .createHash('sha256')
    .update('account:ProofOfCreation')
    .digest()
    .subarray(0, 8);
  const timestamp = 1_700_000_000n;
  const timestampBuffer = Buffer.alloc(8);
  timestampBuffer.writeBigInt64LE(timestamp);
  const data = Buffer.concat([discriminator, artist.toBuffer(), hash, timestampBuffer]);

  assert.deepEqual(decodeProofAccount(data), {
    artistPublicKey: artist.toBase58(),
    contentHash: hash.toString('hex'),
    timestamp: Number(timestamp),
    timestampIso: '2023-11-14T22:13:20.000Z'
  });
});
