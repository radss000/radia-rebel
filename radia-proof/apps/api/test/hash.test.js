import test from 'node:test';
import assert from 'node:assert/strict';
import { hashBuffer, hashToBytes } from '../src/services/hash.js';

test('hashBuffer returns a deterministic SHA-256 hash', () => {
  assert.equal(
    hashBuffer(Buffer.from('radia-proof')),
    '72c231e463154314a1bb7000045272e8f980614ec138b31bbce6d32389b93a78'
  );
});

test('hashToBytes rejects malformed hashes', () => {
  assert.throws(() => hashToBytes('abc'), /64 hexadecimal/);
});
