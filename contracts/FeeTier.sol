// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title FeeTier
/// @notice Whitepaper sec. 2.1: baseline 0.2% (20 bps) protocol service fee,
///         scaled DOWN logarithmically for high-volume actors (whales) and RWA
///         settlements.
///
///         DOC NOTE (logic gap): the whitepaper says "logarithmically" but defines
///         NO parameters. A logarithmic discount without a floor and a slope is
///         under-specified (and can go negative). This draft makes the model
///         explicit and safe:
///
///             feeBps(v) = max(FLOOR_BPS, BASE_BPS - k * ln(v / REF_VOLUME))
///
///         In production the fee is computed on the FHE ciphertext of the volume
///         (TFHE) so validators cannot sniff magnitudes; here it is plain uint256.
contract FeeTier {
    uint16 public constant BASE_BPS = 20;                 // 0.20%
    uint16 public constant FLOOR_BPS = 2;                 // 0.02% hard floor
    uint256 public constant REF_VOLUME = 1_000_000e6;     // $1M reference volume (6-decimal USD)
    uint128 public constant K_NUM = 3;                    // slope k = 3 / ln(10)
    uint128 public constant K_DEN = 1;

    /// @notice ln() approximation (Babl / PRB-math style) — replace with the
    ///         protocol's audited math library in production.
    function ln(uint256 x) internal pure returns (int256) {
        require(x > 0, "ln(0)");
        // Draft stub: actual implementation belongs to an audited fixed-point math lib.
        return int256(_log2(x)) * 693147180559945309 / 1e18; // ln(2) approx
    }

    function _log2(uint256 x) internal pure returns (uint256) {
        uint256 n = 0;
        while (x >= 2) { x >>= 1; n++; }
        return n;
    }

    /// @param volume Transaction notional (plaintext equivalent of the FHE ciphertext).
    function feeBps(uint256 volume) public pure returns (uint16) {
        if (volume <= REF_VOLUME) return BASE_BPS;
        int256 discount = (int256(uint256(K_NUM)) * ln(volume / REF_VOLUME)) / int256(uint256(K_DEN));
        int256 fee = int256(uint256(BASE_BPS)) - discount;
        if (fee < int256(uint256(FLOOR_BPS))) fee = int256(uint256(FLOOR_BPS));
        return uint16(uint256(fee));
    }

    function protocolFee(uint256 volume) public pure returns (uint256) {
        return (volume * feeBps(volume)) / 10_000;
    }
}
