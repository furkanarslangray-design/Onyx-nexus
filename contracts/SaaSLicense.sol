// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title SaaSLicense
/// @notice Accumulates the Autonomous SaaS License Fee, Phi_SaaS(t), defined by
///         whitepaper eq. (3):  Phi(t) = ∫ 0.02 * [P(tau) + lambda*V(tau)] dtau.
///         Phi is mathematically bound to total system success. Only the
///         founding-architecture contract may withdraw.
///
///         REVIEW FIX vs. v1 draft: collect() no longer attempts a second
///         transferFrom — MasterVault already transferred the tokens before
///         calling collect, so v1's double-move would always revert. collect()
///         is now accounting-only.
contract SaaSLicense {
    using SafeERC20 for IERC20;

    address public immutable founderContract;   // founding architecture contract
    address public immutable masterVault;

    uint256 public accumulatedPhi;              // Φ_SaaS(t) accumulator

    event SaaSFeeAccrued(uint256 amount, uint256 totalPhi);
    event SaaSWithdrawn(address indexed to, uint256 amount);

    constructor(address _founderContract, address _masterVault) {
        founderContract = _founderContract;
        masterVault = _masterVault;
    }

    /// @dev Accounting-only: tokens arrive via MasterVault._splitCaptured.
    function collect(uint256 amount) external {
        require(msg.sender == masterVault, "ONYX: only master vault");
        accumulatedPhi += amount;
        emit SaaSFeeAccrued(amount, accumulatedPhi);
    }

    function withdraw(address token, uint256 amount) external {
        require(msg.sender == founderContract, "ONYX: only founder contract");
        IERC20(token).safeTransfer(founderContract, amount);
        emit SaaSWithdrawn(founderContract, amount);
    }
}
