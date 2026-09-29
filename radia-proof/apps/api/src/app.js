import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import multer from 'multer';
import { hashBuffer } from './services/hash.js';

function proofResponse(record) {
  return {
    ...record,
    explorerTransactionUrl: record.transactionId
      ? `https://explorer.solana.com/tx/${record.transactionId}?cluster=devnet`
      : null,
    explorerAccountUrl: record.pdaAddress
      ? `https://explorer.solana.com/address/${record.pdaAddress}?cluster=devnet`
      : null
  };
}

export function createApp({ config, store, solanaClient }) {
  const app = express();
  const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: config.maxAudioSizeBytes },
    fileFilter: (_request, file, callback) => {
      const accepted = file.mimetype.startsWith('audio/') || file.mimetype === 'application/octet-stream';
      callback(accepted ? null : new Error('Only audio files are accepted.'), accepted);
    }
  });

  app.use(helmet());
  app.use(cors({ origin: config.corsOrigin }));
  app.use(express.json());

  app.get('/api/health', async (_request, response, next) => {
    try {
      const program = await solanaClient.getProgramStatus();
      response.json({
        status: program.available && program.executable ? 'ok' : 'degraded',
        network: config.network,
        rpcUrl: config.rpcUrl,
        signerPublicKey: solanaClient.signerPublicKey,
        program
      });
    } catch (error) {
      next(error);
    }
  });

  app.get('/api/config', (_request, response) => {
    response.json({
      network: config.network,
      programId: config.programId,
      signerPublicKey: solanaClient.signerPublicKey,
      maxAudioSizeMb: config.maxAudioSizeBytes / 1024 / 1024
    });
  });

  app.get('/api/proofs', async (_request, response, next) => {
    try {
      const records = await store.list();
      response.json(records.map(proofResponse));
    } catch (error) {
      next(error);
    }
  });

  app.get('/api/proofs/:id', async (request, response, next) => {
    try {
      const record = await store.findById(request.params.id);
      if (!record) {
        return response.status(404).json({ error: 'Proof not found.' });
      }

      response.json(proofResponse(record));
    } catch (error) {
      next(error);
    }
  });

  app.post('/api/proofs', upload.single('audioFile'), async (request, response, next) => {
    try {
      if (!request.file) {
        return response.status(400).json({ error: 'audioFile is required.' });
      }

      const title = String(request.body.title || request.file.originalname).trim();
      const artistName = String(request.body.artistName || 'Anonymous artist').trim();
      const contentHash = hashBuffer(request.file.buffer);
      const artistPublicKey = solanaClient.signerPublicKey;

      if (!artistPublicKey) {
        return response.status(503).json({
          error: 'No devnet signer configured. Run npm run keypair:generate and fund it before minting.'
        });
      }

      const existingRecord = await store.findByIdentity(artistPublicKey, contentHash);
      if (existingRecord) {
        return response.status(200).json({ ...proofResponse(existingRecord), duplicate: true });
      }

      const chainProof = await solanaClient.mintProof(contentHash);
      const record = store.createRecord({
        title,
        artistName,
        originalFilename: request.file.originalname,
        mimeType: request.file.mimetype,
        size: request.file.size,
        contentHash,
        artistPublicKey: chainProof.artistPublicKey,
        pdaAddress: chainProof.pdaAddress,
        transactionId: chainProof.transactionId,
        onChainTimestamp: chainProof.timestamp,
        onChainTimestampIso: chainProof.timestampIso,
        network: config.network,
        programId: config.programId,
        status: 'CONFIRMED'
      });
      await store.upsert(record);

      response.status(chainProof.created ? 201 : 200).json(proofResponse(record));
    } catch (error) {
      next(error);
    }
  });

  app.post('/api/proofs/:id/verify', upload.single('audioFile'), async (request, response, next) => {
    try {
      if (!request.file) {
        return response.status(400).json({ error: 'audioFile is required.' });
      }

      const record = await store.findById(request.params.id);
      if (!record) {
        return response.status(404).json({ error: 'Proof not found.' });
      }

      const uploadedHash = hashBuffer(request.file.buffer);
      const chainProof = await solanaClient.getProof(record.artistPublicKey, record.contentHash);
      const hashMatches = uploadedHash === record.contentHash;
      const chainMatches = Boolean(
        chainProof &&
        chainProof.contentHash === record.contentHash &&
        chainProof.artistPublicKey === record.artistPublicKey &&
        chainProof.pdaAddress === record.pdaAddress
      );

      response.json({
        verified: hashMatches && chainMatches,
        hashMatches,
        chainMatches,
        uploadedHash,
        expectedHash: record.contentHash,
        onChainProof: chainProof,
        proof: proofResponse(record)
      });
    } catch (error) {
      next(error);
    }
  });

  app.use((error, _request, response, _next) => {
    console.error(error);
    if (error instanceof multer.MulterError) {
      return response.status(400).json({ error: error.message });
    }

    response.status(500).json({ error: error.message || 'Unexpected server error.' });
  });

  return app;
}
