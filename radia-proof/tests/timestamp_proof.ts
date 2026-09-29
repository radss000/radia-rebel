import * as anchor from '@coral-xyz/anchor';
import { expect } from 'chai';

describe('timestamp_proof', () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.TimestampProof;
  const artist = anchor.web3.Keypair.generate();
  const trackHash = Array.from(Buffer.alloc(32, 7));

  before(async () => {
    const signature = await provider.connection.requestAirdrop(
      artist.publicKey,
      anchor.web3.LAMPORTS_PER_SOL
    );
    const blockhash = await provider.connection.getLatestBlockhash();
    await provider.connection.confirmTransaction({ signature, ...blockhash });
  });

  it('creates and reads a content proof', async () => {
    const [proofAddress] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from('proof-of-creation'), artist.publicKey.toBuffer(), Buffer.from(trackHash)],
      program.programId
    );

    await program.methods
      .mintProofOfCreation(trackHash)
      .accounts({
        artist: artist.publicKey,
        payer: artist.publicKey,
        proofOfCreation: proofAddress,
        systemProgram: anchor.web3.SystemProgram.programId
      })
      .signers([artist])
      .rpc();

    const proof = await program.account.proofOfCreation.fetch(proofAddress);
    expect(proof.artist.toBase58()).to.equal(artist.publicKey.toBase58());
    expect(Buffer.from(proof.trackHash)).to.deep.equal(Buffer.from(trackHash));
    expect(proof.timestamp.toNumber()).to.be.greaterThan(0);
  });
});
