"""
Run all 5 terrain generators in parallel and report results.
"""

import time
import concurrent.futures
from pathlib import Path

from robot_environment.terr_gen import gen_primitive, gen_fbm_noise, gen_random_walk, gen_spline, gen_wfc


GENERATORS = [
    gen_primitive,
    gen_fbm_noise,
    gen_random_walk,
    gen_spline,
    gen_wfc,
]


def run_generator(mod):
    t0 = time.time()
    mod.main()
    return mod.METHOD, time.time() - t0


def main():
    print("=" * 60)
    print("Terrain dataset generation — all methods")
    print("=" * 60)
    t_start = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(run_generator, m): m.METHOD for m in GENERATORS}
        for fut in concurrent.futures.as_completed(futures):
            method, elapsed = fut.result()
            print(f"  ✓ {method:<20} {elapsed:.1f}s")

    total = time.time() - t_start
    print("=" * 60)
    print(f"All done in {total:.1f}s")

    # Report output paths
    base = Path(__file__).parent / "outputs"
    for method in ["primitive", "fbm_noise", "random_walk", "spline", "wfc"]:
        d = base / method
        pngs = sorted(d.glob("*.png"))
        print(f"  {method}: {len(pngs)} PNGs → {d}")


if __name__ == "__main__":
    main()
