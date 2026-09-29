use anchor_lang::prelude::*;
use anchor_lang::system_program;

declare_id!("8Hh439HNMKGRTD1gmnifrJ2RrP6y8PsKwHRRQyponubt");

#[program]
pub mod timestamp_proof {
    use super::*;

    pub fn initialize(_ctx: Context<Initialize>) -> Result<()> {
        Ok(())
    }

    pub fn mint_proof_of_creation(
        ctx: Context<MintProof>,
        track_hash: [u8; 32],
    ) -> Result<()> {
        let proof = &mut ctx.accounts.proof_of_creation;
        proof.artist = ctx.accounts.artist.key();
        proof.track_hash = track_hash;
        proof.timestamp = Clock::get()?.unix_timestamp;
        Ok(())
    }

    pub fn get_proof_of_creation(
        _ctx: Context<GetProof>,
        _track_hash: [u8; 32],
    ) -> Result<()> {
        Ok(())
    }
}

#[derive(Accounts)]
pub struct Initialize {}

#[derive(Accounts)]
#[instruction(track_hash: [u8; 32])]
pub struct MintProof<'info> {
    #[account(mut)]
    pub artist: Signer<'info>,
    #[account(mut)]
    pub payer: Signer<'info>,
    #[account(
        init,
        payer = payer,
        space = ProofOfCreation::LEN,
        seeds = [b"proof-of-creation", artist.key().as_ref(), &track_hash],
        bump,
    )]
    pub proof_of_creation: Account<'info, ProofOfCreation>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(track_hash: [u8; 32])]
pub struct GetProof<'info> {
    pub artist: SystemAccount<'info>,
    #[account(
        seeds = [b"proof-of-creation", artist.key().as_ref(), &track_hash],
        bump,
    )]
    pub proof_of_creation: Account<'info, ProofOfCreation>,
}

#[account]
pub struct ProofOfCreation {
    pub artist: Pubkey,
    pub track_hash: [u8; 32],
    pub timestamp: i64,
}

impl ProofOfCreation {
    pub const LEN: usize = 8 + 32 + 32 + 8;
}
