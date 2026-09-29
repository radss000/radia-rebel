import crypto from 'node:crypto';

export function hashBuffer(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

export function hashToBytes(hash) {
  if (!/^[a-f0-9]{64}$/i.test(hash)) {
    throw new Error('A SHA-256 hash must contain exactly 64 hexadecimal characters.');
  }

  return Buffer.from(hash, 'hex');
}
