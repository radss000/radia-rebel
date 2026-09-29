import test from 'node:test';
import assert from 'node:assert/strict';
import { hashBuffer, hashToBytes } from '../src/services/hash.js';

test('hashBuffer returns a deterministic SHA-256 hash', () => {
  assert.equal(
    hashBuffer(Buffer.from('radia-proof')),
    'b01d550e6f514d9da73cf8f925c93319005f5b7f621cc7775ad2744958d39533'
  );
});

test('hashToBytes rejects malformed hashes', () => {
  assert.throws(() => hashToBytes('abc'), /64 hexadecimal/);
});
