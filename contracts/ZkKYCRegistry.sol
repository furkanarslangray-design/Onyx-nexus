// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title ZkKYCRegistry
/// @notice Whitepaper sec. 1.1 — zk-KYC layer for institutions and RWA platforms.
///         Actors verify legal status via DIDs and accredited trust anchors off-chain;
///         only a boolean compliance proof result is recorded on-chain, so corporate
///         identity and wallet mappings stay off the public ledger.
///
///         DOC NOTE: the whitepaper promises FHE-routed traffic to be "mathematically
///         blind" yet requires fee magnitude detection (sec. 2.1) and tip redirection
///         per actor. The registry therefore separates IDENTITY (hidden) from
///         AUTHORIZATION (public bit) — the minimum on-chain surface.
contract ZkKYCRegistry {
    address public immutable governance;

    /// @dev wallet => verified (proof validated by trust anchor, e.g. AnonCreds/zk-passport)
    mapping(address => bool) public isVerified;
    /// @dev wallet => DID string (hashed; raw DID lives off-chain)
    mapping(address => bytes32) public didHash;
    /// @dev accredited trust anchors allowed to attest
    mapping(address => bool) public trustAnchors;

    event Verified(address indexed actor, bytes32 didHash);
    event Revoked(address indexed actor);

    constructor() {
        governance = msg.sender;
    }

    modifier onlyTrustAnchor() {
        require(trustAnchors[msg.sender], "ONYX: not a trust anchor");
        _;
    }

    function addTrustAnchor(address anchor) external {
        require(msg.sender == governance, "ONYX: only governance");
        trustAnchors[anchor] = true;
    }

    /// @param proof Draft stub — production verifies a ZK proof of KYC credential
    ///              (e.g. Groth16 over anoncreds) before setting the bit.
    function attestCompliance(address actor, bytes32 _didHash, bytes calldata proof)
        external
        onlyTrustAnchor
    {
        require(proof.length > 0, "ONYX: empty zk proof");
        isVerified[actor] = true;
        didHash[actor] = _didHash;
        emit Verified(actor, _didHash);
    }

    function revoke(address actor) external onlyTrustAnchor {
        isVerified[actor] = false;
        emit Revoked(actor);
    }
}
