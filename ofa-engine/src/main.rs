//! ONYX Nexus — Order Flow Auction (OFA) matching engine draft.
//! Whitepaper sec. 3.1: whitelisted HFT bots bid (in microseconds, off-chain)
//! for the right to execute cross-exchange arbitrage with MasterVault liquidity.
//! The winning bot receives a signed bid that MasterVault.flashLoan verifies.
//!
//! DOC NOTE (logic gap): the whitepaper never specifies the auction clearing
//! rule. This draft makes it explicit: FIRST-PRICE sealed-bid, highest premium
//! wins, losers pay nothing. Ties broken by lower latency (earlier arrival).
//!
//! Run: cargo run --release --example  (draft; std-only, no external deps)

use std::collections::BinaryHeap;
use std::time::{Duration, Instant};

/// One sealed bid from a zk-KYC-verified HFT bot.
#[derive(Debug, Clone, PartialEq)]
struct Bid {
    bot: [u8; 20],
    draw_amount: u128,     // principal requested from MasterVault
    premium: u128,         // OFA winning bid = yield offered back to the vault
    encrypted_payload: Vec<u8>, // FHE-encrypted route/slippage (TFHE ciphertext)
    nonce: u64,                 // replay protection: signed in payload, verified on-chain
    received_at: Instant,
}

// BinaryHeap is a max-heap -> Ord ranks by premium DESC, then arrival ASC.
impl Eq for Bid {}
impl PartialOrd for Bid {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}
impl Ord for Bid {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.premium
            .cmp(&other.premium)
            .then_with(|| other.received_at.cmp(&self.received_at)) // earlier = better
    }
}

/// Auction batch: collect bids for a fixed window, then clear.
struct OfaAuction {
    auction_window: Duration, // microsecond-scale batching
    min_premium_bps: u128,    // vault won't lend below this premium (20 bps base)
}

struct AuctionOutcome {
    winner: Bid,
    losers: Vec<Bid>,
}

impl OfaAuction {
    fn new(auction_window: Duration, min_premium_bps: u128) -> Self {
        Self { auction_window, min_premium_bps }
    }

    /// Collect sealed bids for `auction_window`, then clear first-price.
    fn run(&self, incoming: Vec<Bid>) -> Option<AuctionOutcome> {
        let deadline = Instant::now() + self.auction_window;
        let mut heap = BinaryHeap::new();
        for bid in incoming {
            if Instant::now() > deadline { break; }
            if bid.premium * 10_000 >= bid.draw_amount * self.min_premium_bps {
                heap.push(bid); // ignore sub-floor bids
            }
        }
        let winner = heap.pop()?;
        Some(AuctionOutcome { winner, losers: heap.into_vec() })
    }

    /// Produce the payload MasterVault._verifyBid checks on-chain.
    /// Draft: production signs EIP-712 digest with the OFA engine key.
    fn winning_bid_payload(&self, outcome: &AuctionOutcome) -> Vec<u8> {
        let w = &outcome.winner;
        format!(
            "ONYX_OFA_WINNER|bot={:?}|draw={}|premium={}|nonce={}|deadline_ms=250",
            w.bot, w.draw_amount, w.premium, w.nonce
        )
        .into_bytes()
    }
}

fn main() {
    let engine = OfaAuction::new(Duration::from_micros(250), 20); // 0.2% base premium
    let now = Instant::now();
    let bids = vec![
        Bid { bot: [0x11; 20], draw_amount: 2_000_000, premium: 5_200, encrypted_payload: vec![0u8; 256], received_at: now },
        Bid { bot: [0x22; 20], draw_amount: 2_000_000, premium: 7_900, encrypted_payload: vec![1u8; 256], received_at: now + Duration::from_micros(40) },
        Bid { bot: [0x33; 20], draw_amount: 2_000_000, premium: 7_900, encrypted_payload: vec![2u8; 256], received_at: now + Duration::from_micros(10) }, // tie -> earlier wins
        Bid { bot: [0x44; 20], draw_amount: 2_000_000, premium: 300,  encrypted_payload: vec![3u8; 256], received_at: now + Duration::from_micros(5)  }, // below floor
    ];
    match engine.run(bids) {
        Some(outcome) => println!(
            "winner bot {:?} premium={} (losers={})",
            outcome.winner.bot, outcome.winner.premium, outcome.losers.len()
        ),
        None => println!("no clearing bid"),
    }
}
