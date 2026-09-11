"""
ONYX Nexus — Master Vault growth simulation + conservation audit.

Compares:
  (A) Whitepaper model, eq. (1)/(2):
        dV/dt = 0.98*P0 + lambda*V          <- 2% haircut ONLY on fee inflow P
        dPhi/dt = 0.02*(P0 + lambda*V)      <- eq. (3): 2% of BOTH P and lambda*V
      => total claimed growth d(V+Phi)/dt = P0 + 1.02*lambda*V
      => claims 102% of arbitrage yield. CONSERVATION VIOLATION (double-counts 2% of lambda*V).

  (B) Corrected model (applied in the Solidity drafts):
        dV/dt = 0.98*(P0 + lambda*V)
        dPhi/dt = 0.02*(P0 + lambda*V)
      => d(V+Phi)/dt = P0 + lambda*V  == actual yield. CONSERVED.
      Analytic: V(t) = (V0 + P0/lambda) * e^(0.98*lambda*t) - P0/lambda

Units: USD (6-decimal stablecoin), t in days.
"""

import numpy as np
import matplotlib.pyplot as plt

V0 = 10_000_000.0   # initial Master Vault liquidity ($10M)
P0 = 50_000.0       # baseline daily protocol service-fee inflow ($50k/day)
LAMBDA = 0.001      # aggregate continuous arbitrage return rate (0.1%/day, aggressive)
T_DAYS = 365
DT = 0.01           # Euler step (days)

def simulate(model: str) -> dict:
    steps = int(T_DAYS / DT)
    V, phi, claimed_total, actual_yield = V0, 0.0, V0, V0
    V_path, phi_path, err_path, t_path = [], [], [], []
    for i in range(steps):
        t = i * DT
        if model == "whitepaper":
            dV = 0.98 * P0 + LAMBDA * V
            dphi = 0.02 * (P0 + LAMBDA * V)
        else:  # corrected
            dV = 0.98 * (P0 + LAMBDA * V)
            dphi = 0.02 * (P0 + LAMBDA * V)
        V += dV * DT
        phi += dphi * DT
        claimed_total += (dV + dphi) * DT
        actual_yield += (P0 + LAMBDA * V) * DT
        if i % int(1 / DT) == 0:
            t_path.append(t)
            V_path.append(V)
            phi_path.append(phi)
            err_path.append(claimed_total - actual_yield)
    return dict(t=np.array(t_path), V=np.array(V_path), phi=np.array(phi_path),
                err=np.array(err_path))

wp = simulate("whitepaper")
fx = simulate("corrected")

# --- Audit output -----------------------------------------------------------
t_end = wp["t"][-1]
print(f"Parameters: V0=${V0:,.0f}  P0=${P0:,.0f}/day  lambda={LAMBDA}/day  T={T_DAYS} days\n")
print(f"[A] Whitepaper model:")
print(f"    V(365)        = ${wp['V'][-1]:,.0f}")
print(f"    Phi_SaaS(365) = ${wp['phi'][-1]:,.0f}")
print(f"    Conservation error (claimed - actually generated) = ${wp['err'][-1]:,.0f}")
print(f"    => eq.(1) and eq.(3) are mutually inconsistent; 2% of lambda*V is claimed twice.\n")

V_ana = (V0 + P0 / LAMBDA) * np.exp(0.98 * LAMBDA * t_end) - P0 / LAMBDA
print(f"[B] Corrected model:")
print(f"    V(365)        = ${fx['V'][-1]:,.0f}   (analytic check: ${V_ana:,.0f})")
print(f"    Phi_SaaS(365) = ${fx['phi'][-1]:,.0f}")
print(f"    Conservation error = ${fx['err'][-1]:,.2f}  (numerical zero => CONSERVED)")
print(f"    Vault growth multiple over 1y: {fx['V'][-1]/V0:.2f}x")

# --- Plot --------------------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
axes[0].plot(wp["t"], wp["V"] / 1e6, label="Whitepaper eq.(1)  [V]")
axes[0].plot(fx["t"], fx["V"] / 1e6, "--", label="Corrected 0.98(P+lambda*V)")
axes[0].plot(fx["t"], fx["phi"] / 1e6, label="SaaS Phi(t) [2%]", alpha=0.7)
axes[0].set_title("Master Vault growth models")
axes[0].set_xlabel("days"); axes[0].set_ylabel("USD millions"); axes[0].legend()

axes[1].plot(wp["t"], wp["err"] / 1e3, label="Whitepaper model over-claim")
axes[1].plot(fx["t"], fx["err"], "--", label="Corrected model")
axes[1].set_title("Conservation error: (V+Phi) - actual yield")
axes[1].set_xlabel("days"); axes[1].set_ylabel("USD thousands"); axes[1].legend()

plt.tight_layout()
out = "/mnt/agents/output/onyx-nexus/simulation/vault_growth.png"
plt.savefig(out, dpi=120)
print(f"\nPlot saved: {out}")
