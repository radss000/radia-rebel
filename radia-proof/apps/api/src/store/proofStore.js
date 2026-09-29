import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

export class ProofStore {
  constructor(filePath) {
    this.filePath = filePath;
    this.writeQueue = Promise.resolve();
  }

  async initialize() {
    await fs.mkdir(path.dirname(this.filePath), { recursive: true });
    try {
      await fs.access(this.filePath);
    } catch {
      await fs.writeFile(this.filePath, '[]\n');
    }
  }

  async list() {
    const records = await this.#read();
    return records.sort((left, right) => right.createdAt.localeCompare(left.createdAt));
  }

  async findById(id) {
    const records = await this.#read();
    return records.find((record) => record.id === id) || null;
  }

  async findByIdentity(artistPublicKey, contentHash) {
    const records = await this.#read();
    return records.find(
      (record) => record.artistPublicKey === artistPublicKey && record.contentHash === contentHash
    ) || null;
  }

  async upsert(record) {
    this.writeQueue = this.writeQueue.then(async () => {
      const records = await this.#read();
      const index = records.findIndex((candidate) => candidate.id === record.id);

      if (index === -1) {
        records.push(record);
      } else {
        records[index] = record;
      }

      await this.#write(records);
    });

    await this.writeQueue;
    return record;
  }

  createRecord(input) {
    const now = new Date().toISOString();
    return {
      id: crypto.randomUUID(),
      createdAt: now,
      updatedAt: now,
      ...input
    };
  }

  async #read() {
    const contents = await fs.readFile(this.filePath, 'utf8');
    return JSON.parse(contents);
  }

  async #write(records) {
    const temporaryPath = `${this.filePath}.tmp`;
    await fs.writeFile(temporaryPath, `${JSON.stringify(records, null, 2)}\n`);
    await fs.rename(temporaryPath, this.filePath);
  }
}
