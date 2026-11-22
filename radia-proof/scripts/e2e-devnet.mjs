import fs from 'node:fs';
import path from 'node:path';

const baseUrl = process.env.API_URL || 'http://localhost:5001';
const samplePath = path.resolve(process.env.E2E_AUDIO_FILE || 'scripts/e2e-sample.wav');

function createWaveFile() {
  const sampleRate = 8000;
  const seconds = 1;
  const dataLength = sampleRate * seconds * 2;
  const buffer = Buffer.alloc(44 + dataLength);
  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(36 + dataLength, 4);
  buffer.write('WAVEfmt ', 8);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write('data', 36);
  buffer.writeUInt32LE(dataLength, 40);
  for (let index = 0; index < sampleRate; index += 1) {
    const sample = Math.sin((index / sampleRate) * Math.PI * 2 * 440) * 8000;
    buffer.writeInt16LE(sample, 44 + index * 2);
  }
  fs.writeFileSync(samplePath, buffer);
}

createWaveFile();
const healthResponse = await fetch(`${baseUrl}/api/health`);
const health = await healthResponse.json();
if (!healthResponse.ok || health.status !== 'ok' || !health.signerPublicKey) {
  throw new Error(`API is not ready for devnet E2E: ${JSON.stringify(health)}`);
}

const bytes = fs.readFileSync(samplePath);
const createBody = new FormData();
createBody.append('title', `E2E proof ${new Date().toISOString()}`);
createBody.append('artistName', 'Radia E2E');
createBody.append('audioFile', new Blob([bytes], { type: 'audio/wav' }), 'e2e-sample.wav');
const createResponse = await fetch(`${baseUrl}/api/proofs`, { method: 'POST', body: createBody });
const proof = await createResponse.json();
if (!createResponse.ok) throw new Error(`Mint failed: ${JSON.stringify(proof)}`);
console.log(`Proof: ${proof.id}`);
console.log(`PDA: ${proof.pdaAddress}`);
console.log(`Transaction: ${proof.transactionId || 'existing proof reused'}`);

const verifyBody = new FormData();
verifyBody.append('audioFile', new Blob([bytes], { type: 'audio/wav' }), 'e2e-sample.wav');
const verifyResponse = await fetch(`${baseUrl}/api/proofs/${proof.id}/verify`, {
  method: 'POST',
  body: verifyBody
});
const verification = await verifyResponse.json();
if (!verifyResponse.ok || !verification.verified) {
  throw new Error(`Verification failed: ${JSON.stringify(verification)}`);
}
console.log('E2E devnet proof verified successfully.');
