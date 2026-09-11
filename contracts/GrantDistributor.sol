// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IMasterVault {
    /// @dev Draws strictly from the vault's yield bucket; principal is protected.
    function releaseYield(address to, uint256 amount) external;
}

/// @title GrantDistributor
/// @notice Whitepaper sec. 3.3 — Hack Club grant pipeline, funded ONLY by
///         arbitrage yield (lambda*V), never by vault principal:
///           Tier 1 Onboarding : $1,000  automated micro-grants
///           Tier 2 Hardware   : $2,000  smart prepaid cards (tech-POS restricted)
///           Tier 3 Milestone  : $10,000 .. $500,000, on-chain multisig after
///                               "Spend Detective" audit
///
///         DOC NOTE (logic error): whitepaper calls Tier 3 "limitless scaling"
///         while pitching "$10,000 to $500,000" — a bound and "limitless"
///         contradict each other. Enforced here as a hard on-chain cap.
///
///         REVIEW FIX vs. v1 draft: payouts no longer use
///         safeTransferFrom(masterVault, ...) — the vault never granted an
///         allowance, so v1 grants would always revert. Payouts now go through
///         MasterVault.releaseYield, which enforces the yield-only invariant.
contract GrantDistributor {
    enum Tier { Onboarding, Hardware, Milestone }

    uint256 public constant TIER1_AMOUNT = 1_000e6;
    uint256 public constant TIER2_AMOUNT = 2_000e6;
    uint256 public constant TIER3_MIN    = 10_000e6;
    uint256 public constant TIER3_MAX    = 500_000e6; // whitepaper bound, enforced

    address public immutable grantAsset;
    address public immutable masterVault;
    address public immutable multisig;        // Hack Club multisig for Tier 3
    mapping(uint256 => bool) public spendDetectiveAudited;
    mapping(uint256 => bool) public grantPaid;

    event GrantReleased(uint256 indexed grantId, Tier tier, address indexed recipient, uint256 amount);

    constructor(address _grantAsset, address _masterVault, address _multisig) {
        grantAsset = _grantAsset;
        masterVault = _masterVault;
        multisig = _multisig;
    }

    modifier onlyMultisig() {
        require(msg.sender == multisig, "ONYX: only grant multisig");
        _;
    }

    /// @notice Tiers 1-2: automated micro-grants (keeper-triggered).
    function releaseMicroGrant(uint256 grantId, Tier tier, address recipient) external {
        require(!grantPaid[grantId], "ONYX: already paid");
        require(tier == Tier.Onboarding || tier == Tier.Hardware, "ONYX: use multisig for Tier 3");
        grantPaid[grantId] = true;
        uint256 amount = tier == Tier.Onboarding ? TIER1_AMOUNT : TIER2_AMOUNT;
        _payout(recipient, amount);
        emit GrantReleased(grantId, tier, recipient, amount);
    }

    /// @notice Tier 3: milestone scaling grants require multisig + Spend Detective audit.
    function releaseMilestoneGrant(uint256 grantId, address recipient, uint256 amount)
        external
        onlyMultisig
    {
        require(!grantPaid[grantId], "ONYX: already paid");
        require(spendDetectiveAudited[grantId], "ONYX: Spend Detective audit missing");
        require(amount >= TIER3_MIN && amount <= TIER3_MAX, "ONYX: outside Tier 3 bounds");
        grantPaid[grantId] = true;
        _payout(recipient, amount);
        emit GrantReleased(grantId, Tier.Milestone, recipient, amount);
    }

    function markAudited(uint256 grantId) external onlyMultisig {
        spendDetectiveAudited[grantId] = true;
    }

    function _payout(address recipient, uint256 amount) internal {
        // Yield-only draw, enforced by MasterVault's yield bucket.
        IMasterVault(masterVault).releaseYield(recipient, amount);
    }
}
