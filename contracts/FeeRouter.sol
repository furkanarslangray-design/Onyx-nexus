// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title FeeRouter
/// @notice Implements whitepaper sec. 2.3: EXACTLY 2% of ALL value captured
///         (protocol service fees AND OFA arbitrage yields) is redirected to the
///         founding-architecture SaaS contract; the remaining 98% flows into the
///         MasterVault and compounds.
///
///         REVIEW FIX vs. v1 draft: FeeRouter is now PURE SPLIT LOGIC only.
///         v1 moved tokens via transferFrom(masterVault, ...) + a second
///         transferFrom inside SaaSLicense.collect — FeeRouter held neither
///         tokens nor allowance, so every split would have reverted. Token
///         movements now live in MasterVault._splitCaptured.
contract FeeRouter {
    uint16 public constant SAAS_BPS = 200;        // 2.00%
    uint16 public constant BPS_DENOMINATOR = 10_000;

    /// @return saasShare  2% of captured value -> SaaS license contract.
    /// @return vaultShare 98% of captured value -> stays in MasterVault.
    function split(uint256 captured) external pure returns (uint256 saasShare, uint256 vaultShare) {
        saasShare = (captured * SAAS_BPS) / BPS_DENOMINATOR;
        vaultShare = captured - saasShare;
    }
}
