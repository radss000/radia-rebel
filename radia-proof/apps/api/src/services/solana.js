import crypto from 'node:crypto';
import fs from 'node:fs';
import bs58 from 'bs58';
import {
  Connection,
  Keypair,
  PublicKey,
  SystemProgram,
  Transaction,
  TransactionInstruction
} from '@solana/web3.js';
import { hashToBytes } from './hash.js';

const PROOF_SEED = Buffer.from('proof-of-creation');
const MINT_DISCRIMINATOR = crypto
  .createHash('sha256')
  .update('global:mint_proof_of_creation')
  .digest()
  .subarray(0, 8);
const ACCOUNT_DISCRIMINATOR = crypto
  .createHash('sha256')
  .update('account:ProofOfCreation')
  .digest()
  .subarray(0, 8);

export function loadSigner({ privateKey, keypairPath }) {
  if (privateKey) {
    const decoded = bs58.decode(privateKey.trim());
    return Keypair.fromSecretKey(decoded);
  }

  if (!fs.existsSync(keypairPath)) {
    return null;
  }

  const secret = JSON.parse(fs.readFileSync(keypairPath, 'utf8'));
  return Keypair.fromSecretKey(Uint8Array.from(secret));
}

export function decodeProofAccount(data) {
  if (data.length < 80) {
    throw new Error('Proof account data is too short.');
  }

  if (!data.subarray(0, 8).equals(ACCOUNT_DISCRIMINATOR)) {
    throw new Error('Unexpected proof account discriminator.');
  }

  const artist = new PublicKey(data.subarray(8, 40));
  const contentHash = data.subarray(40, 72).toString('hex');
  const timestamp = Number(data.readBigInt64LE(72));

  return {
    artistPublicKey: artist.toBase58(),
    contentHash,
    timestamp,
    timestampIso: new Date(timestamp * 1000).toISOString()
  };
}

export class SolanaProofClient {
  constructor({ rpcUrl, programId, signer }) {
    this.connection = new Connection(rpcUrl, 'confirmed');
    this.programId = new PublicKey(programId);
    this.signer = signer;
  }

  get signerPublicKey() {
    return this.signer?.publicKey.toBase58() || null;
  }

  deriveProofAddress(artistPublicKey, contentHash) {
    return PublicKey.findProgramAddressSync(
      [
        PROOF_SEED,
        new PublicKey(artistPublicKey).toBuffer(),
        hashToBytes(contentHash)
      ],
      this.programId
    );
  }

  async getProgramStatus() {
    const account = await this.connection.getAccountInfo(this.programId);
    return {
      available: Boolean(account),
      executable: Boolean(account?.executable),
      programId: this.programId.toBase58()
    };
  }

  async getProof(artistPublicKey, contentHash) {
    const [proofAddress] = this.deriveProofAddress(artistPublicKey, contentHash);
    const account = await this.connection.getAccountInfo(proofAddress, 'confirmed');

    if (!account) {
      return null;
    }

    if (!account.owner.equals(this.programId)) {
      throw new Error('The proof account is not owned by the configured program.');
    }

    return {
      pdaAddress: proofAddress.toBase58(),
      ...decodeProofAccount(account.data)
    };
  }

  async mintProof(contentHash) {
    if (!this.signer) {
      throw new Error('No Solana signer configured. Generate a devnet keypair first.');
    }

    const artistPublicKey = this.signer.publicKey.toBase58();
    const existing = await this.getProof(artistPublicKey, contentHash);
    if (existing) {
      return {
        created: false,
        transactionId: null,
        ...existing
      };
    }

    const hashBytes = hashToBytes(contentHash);
    const [proofAddress] = this.deriveProofAddress(artistPublicKey, contentHash);
    const instruction = new TransactionInstruction({
      programId: this.programId,
      keys: [
        { pubkey: this.signer.publicKey, isSigner: true, isWritable: true },
        { pubkey: this.signer.publicKey, isSigner: true, isWritable: true },
        { pubkey: proofAddress, isSigner: false, isWritable: true },
        { pubkey: SystemProgram.programId, isSigner: false, isWritable: false }
      ],
      data: Buffer.concat([MINT_DISCRIMINATOR, hashBytes])
    });
    const latestBlockhash = await this.connection.getLatestBlockhash('confirmed');
    const transaction = new Transaction({
      feePayer: this.signer.publicKey,
      blockhash: latestBlockhash.blockhash,
      lastValidBlockHeight: latestBlockhash.lastValidBlockHeight
    }).add(instruction);
    transaction.sign(this.signer);

    const transactionId = await this.connection.sendRawTransaction(transaction.serialize(), {
      skipPreflight: false,
      maxRetries: 3
    });
    const confirmation = await this.connection.confirmTransaction(
      { signature: transactionId, ...latestBlockhash },
      'confirmed'
    );

    if (confirmation.value.err) {
      throw new Error(`Solana transaction failed: ${JSON.stringify(confirmation.value.err)}`);
    }

    const proof = await this.getProof(artistPublicKey, contentHash);
    if (!proof) {
      throw new Error('Transaction confirmed but proof account could not be loaded.');
    }

    return {
      created: true,
      transactionId,
      ...proof
    };
  }
}
