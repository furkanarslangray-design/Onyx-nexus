#!/usr/bin/env python3
"""Session rotator for 3-tier keyless proxy pool.

Rotates TLS/JA3 fingerprints and session tokens to bypass rate limits.
"""

import os
import time
import json
import random
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class ProxySession:
    tier: int
    endpoint: str
    fingerprint: str
    session_token: str
    created_at: datetime
    expires_at: datetime
    request_count: int = 0

    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

    def rotate_token(self) -> None:
        """Generate new session token with jitter."""
        entropy = f"{self.endpoint}{time.time()}{random.random()}"
        self.session_token = hashlib.sha256(entropy.encode()).hexdigest()[:32]
        self.created_at = datetime.now()
        self.expires_at = datetime.now() + timedelta(
            seconds=int(os.getenv("ROTATION_INTERVAL", "300"))
        )
        self.request_count = 0


class ProxyPoolManager:
    """Manages 3-tier proxy pool with automatic rotation."""

    FINGERPRINTS = [
        "chrome120", "firefox121", "safari17", "edge120",
        "chrome119", "firefox120", "safari16_5"
    ]

    def __init__(self):
        self.sessions: Dict[int, List[ProxySession]] = {1: [], 2: [], 3: []}
        self.active_tier = 1
        self._init_pool()

    def _init_pool(self) -> None:
        """Initialize proxy sessions for all tiers."""
        tier_endpoints = {
            1: ["localhost:8001", "localhost:8002"],
            2: ["localhost:8003", "localhost:8004"],
            3: ["localhost:8005", "localhost:8006"]
        }

        for tier, endpoints in tier_endpoints.items():
            for endpoint in endpoints:
                session = ProxySession(
                    tier=tier,
                    endpoint=endpoint,
                    fingerprint=random.choice(self.FINGERPRINTS),
                    session_token="",
                    created_at=datetime.now(),
                    expires_at=datetime.now()
                )
                session.rotate_token()
                self.sessions[tier].append(session)

    def get_session(self, tier: Optional[int] = None) -> ProxySession:
        """Get active session for tier, with fallback."""
        target_tier = tier or self.active_tier
        available = [s for s in self.sessions[target_tier] if not s.is_expired()]

        if not available:
            # Rotate all expired sessions in tier
            for s in self.sessions[target_tier]:
                if s.is_expired():
                    s.rotate_token()
            available = self.sessions[target_tier]

        session = random.choice(available)
        session.request_count += 1

        # Tier escalation on high request count
        if session.request_count > 100 and target_tier < 3:
            self.active_tier = target_tier + 1

        return session

    def health_check(self) -> Dict:
        """Return pool health status."""
        status = {}
        for tier, sessions in self.sessions.items():
            active = sum(1 for s in sessions if not s.is_expired())
            status[f"tier{tier}"] = {
                "total": len(sessions),
                "active": active,
                "total_requests": sum(s.request_count for s in sessions)
            }
        return status


def main():
    """Main rotation loop."""
    manager = ProxyPoolManager()

    print(f"[{datetime.now().isoformat()}] Proxy pool initialized")
    print(f"Health: {json.dumps(manager.health_check(), indent=2)}")

    while True:
        try:
            # Periodic rotation check
            for tier_sessions in manager.sessions.values():
                for session in tier_sessions:
                    if session.is_expired():
                        old_fp = session.fingerprint
                        session.rotate_token()
                        session.fingerprint = random.choice(manager.FINGERPRINTS)
                        print(
                            f"[{datetime.now().isoformat()}] "
                            f"Rotated {session.endpoint}: {old_fp} -> {session.fingerprint}"
                        )

            time.sleep(30)

        except KeyboardInterrupt:
            print("Shutting down rotator...")
            break
        except Exception as e:
            print(f"Error in rotation loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
