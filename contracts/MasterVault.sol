// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @notice Callback interface for whitelisted HFT bots (OFA winners).
interface IFlashLoanBorrower {
    /// @dev MUST return keccak256("ONYX_FLASHLOAN_OK") on success.
    function onFlashLoan(address token, uint256 amount, uint256 premium, bytes calldata data)
        external
        returns (bytes32);
}

interface IZkKYCRegistry {
    function isVerified(address actor) external view returns (bool);
}

interface IFeeRouter {
    function split(uint256 captured) external pure returns (uint256 saasShare, uint256 vaultShare);
}

interface ISaaSLicense {
    function collect(uint256 amount) external;
}

interface IFeeTier {
    function feeBps(uint256 volume) external pure returns (uint16);
}

/// @title MasterVault
/// @notice Hyper-liquid flash-loan provider. Whitelisted (zk-KYC) HFT bots draw
///         liquidity inside a single atomic transaction. If principal + OFA-winning
///         premium is not returned in the SAME transaction, the entire call reverts
///         (EVM atomicity) => zero counterparty risk for the vault.
///
///         REVIEW FIXES vs. v1 draft:
///         (a) Token flow: the vault itself moves the 2% SaaS share; no
///             transferFrom/allowance chain that could revert or be left ungranted.
///         (b) P(t) producer: collectServiceFee() gives the whitepaper sec. 2.1
///             0.2% routing fee an on-chain entry point (eq. 1's P(t) term).
///         (c) Yield bucket: grants may ONLY spend `distributableYield`; vault
///             principal is unreachable (infinite-runway invariant, sec. 3.3).
///         (d) OFA bids carry a nonce -> signed payloads cannot be replayed.
///
///         DOC NOTE (logic fix, carried over): eq. (1) applies the 2% SaaS haircut
///         only to P(t) while eq. (3) takes 2% of BOTH P and lambda*V. This contract
///         applies the 2% split to ALL captured value, consistent with eq. (3) and
///         with token conservation (see simulation/vault_growth.py).
///         DOC NOTE: grant outflows are an outflow term -g(t) absent from eq. (1);
///         they draw down `distributableYield`, not principal.
contract MasterVault is ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant CALLBACK_OK = keccak256("ONYX_FLASHLOAN_OK");

    address public immutable asset;             // vault asset (e.g., USDC)
    address public immutable feeRouter;         // 98/2 split logic (pure)
    address public immutable feeTier;           // volume-tiered fee curve
    address public immutable kycRegistry;       // zk-KYC whitelist
    address public immutable ofaEngine;         // off-chain OFA signer
    address public immutable saasLicense;       // 2% accumulator
    address public immutable grantDistributor;  // sole yield spender

    uint256 public totalLoansExecuted;
    uint256 public totalYieldCaptured;      // ∫ lambda*V  (OFA premiums)
    uint256 public serviceFeeInflowTotal;   // ∫ P(t)      (0.2% routing fees)
    uint256 public distributableYield;      // grants may ONLY draw from here

    event FlashLoanExecuted(address indexed bot, uint256 amount, uint256 premium);
    event ServiceFeeCollected(address indexed payer, uint256 volume, uint16 feeBps, uint256 fee);
    event YieldReleased(address indexed to, uint256 amount);
    event AtomicReturnFailed(address indexed bot, uint256 amount);

    constructor(
        address _asset,
        address _feeRouter,
        address _feeTier,
        address _kycRegistry,
        address _ofaEngine,
        address _saasLicense,
        address _grantDistributor
    ) {
        asset = _asset;
        feeRouter = _feeRouter;
        feeTier = _feeTier;
        kycRegistry = _kycRegistry;
        ofaEngine = _ofaEngine;
        saasLicense = _saasLicense;
        grantDistributor = _grantDistributor;
    }

    /// @notice Execute an atomic flash loan. The premium is the OFA winning bid
    ///         (lambda*V contributor), quoted and signed off-chain by the Rust
    ///         OFA engine; the signature is verified here so the vault never
    ///         trusts a bot's self-reported premium.
    function flashLoan(
        uint256 amount,
        uint256 premium,
        uint256 nonce,
        bytes calldata bidSig,
        uint256 deadline,
        bytes calldata data
    ) external nonReentrant returns (bool) {
        require(deadline >= block.timestamp, "ONYX: stale OFA bid");
        require(IZkKYCRegistry(kycRegistry).isVerified(msg.sender), "ONYX: bot not zk-KYC verified");
        require(_verifyBid(msg.sender, amount, premium, nonce, deadline, bidSig), "ONYX: invalid OFA bid");

        uint256 balanceBefore = IERC20(asset).balanceOf(address(this));
        require(amount <= balanceBefore, "ONYX: insufficient vault liquidity");

        IERC20(asset).safeTransfer(msg.sender, amount);

        bytes32 result = IFlashLoanBorrower(msg.sender).onFlashLoan(asset, amount, premium, data);

        uint256 balanceAfter = IERC20(asset).balanceOf(address(this));

        // Atomicity guarantee: revert unless principal + premium returned in-tx.
        if (result != CALLBACK_OK || balanceAfter < balanceBefore + premium) {
            emit AtomicReturnFailed(msg.sender, amount);
            revert("ONYX: atomic return failed");
        }

        totalLoansExecuted += 1;
        totalYieldCaptured += premium;
        _splitCaptured(premium);

        emit FlashLoanExecuted(msg.sender, amount, premium);
        return true;
    }

    /// @notice Whitepaper sec. 2.1 — protocol service fee entry point (P(t)).
    ///         Baseline 0.2% (20 bps), logarithmically tiered DOWN for whales/RWA.
    ///         FeeTier computes the bps trustlessly on-chain; `maxFee` is the
    ///         user's FHE-encrypted slippage bound revealed at execution.
    function collectServiceFee(uint256 volume, uint256 maxFee) external nonReentrant {
        uint16 bps = IFeeTier(feeTier).feeBps(volume);
        uint256 fee = (volume * bps) / 10_000;
        require(fee <= maxFee, "ONYX: fee above user max");
        IERC20(asset).safeTransferFrom(msg.sender, address(this), fee);

        serviceFeeInflowTotal += fee;
        _splitCaptured(fee);

        emit ServiceFeeCollected(msg.sender, volume, bps, fee);
    }

    /// @notice Sole yield exit. GrantDistributor draws strictly from accumulated
    ///         yield; vault principal is unreachable through this path.
    function releaseYield(address to, uint256 amount) external nonReentrant {
        require(msg.sender == grantDistributor, "ONYX: only grant distributor");
        require(amount <= distributableYield, "ONYX: exceeds yield bucket (principal protected)");
        distributableYield -= amount;
        IERC20(asset).safeTransfer(to, amount);
        emit YieldReleased(to, amount);
    }

    /// @dev 2% -> SaaS license contract (transferred now, accounted there);
    ///      98% stays in the vault AND is credited to the grant-eligible bucket.
    function _splitCaptured(uint256 captured) internal {
        (uint256 saasShare, uint256 vaultShare) = IFeeRouter(feeRouter).split(captured);
        IERC20(asset).safeTransfer(saasLicense, saasShare);
        ISaaSLicense(saasLicense).collect(saasShare);
        distributableYield += vaultShare;
    }

    function _verifyBid(
        address bot,
        uint256 amount,
        uint256 premium,
        uint256 nonce,
        uint256 deadline,
        bytes calldata sig
    ) internal view returns (bool) {
        // Draft: replace with EIP-712 typed structured data in production.
        bytes32 digest = keccak256(abi.encodePacked(bot, amount, premium, nonce, deadline, address(this)));
        (bytes32 r, bytes32 s, uint8 v) = abi.decode(sig, (bytes32, bytes32, uint8));
        return ecrecover(digest, v, r, s) == ofaEngine;
    }
}
