
from pathlib import Path
from itertools import combinations

import igraph as ig
import leidenalg as la
import pandas as pd

from sklearn.metrics import adjusted_rand_score


# ============================================================
# KONFIGURASI
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
GRAPH_DIR = BASE_DIR / "hasil_network" / "graph"

OUTPUT_DIR = GRAPH_DIR / "leiden_parameter_testing"

# Rentang eksplorasi resolution
RESOLUTION_RANGE = (0.1, 5.0)

# Seed untuk pengujian kestabilan
SEEDS = [42, 100, 123, 2026, 2027]

# Jumlah iterasi Leiden
N_ITERATIONS = -1


# ============================================================
# 1. RESOLUTION PROFILE
# ============================================================

def explore_resolution(graph, quarter):

    print("\n" + "=" * 65)
    print(f"RESOLUTION PROFILE: {quarter}")
    print("=" * 65)

    optimiser = la.Optimiser()

    # Mengatur seed untuk proses resolution profile
    optimiser.set_rng_seed(42)

    profile = optimiser.resolution_profile(
        graph,
        la.RBConfigurationVertexPartition,
        resolution_range=RESOLUTION_RANGE,
        weights="weight",
        number_iterations=N_ITERATIONS
    )

    results = []

    for index, partition in enumerate(profile):

        membership = partition.membership

        sizes = pd.Series(membership).value_counts()

        results.append({
            "quarter": quarter,
            "resolution": partition.resolution_parameter,
            "number_communities": len(sizes),
            "largest_community": sizes.max(),
            "smallest_community": sizes.min(),
            "mean_community_size": sizes.mean(),
            "quality": partition.quality()
        })

    df_profile = pd.DataFrame(results)

    print("\nHasil Resolution Profile:")
    print(df_profile.to_string(index=False))

    return df_profile


# ============================================================
# 2. MENGUJI BEBERAPA RANDOM SEED
# ============================================================

def test_seed_stability(graph, quarter, resolution):

    print(
        f"\nMenguji {quarter} | "
        f"Resolution: {resolution:.6f}"
    )

    memberships = {}

    for seed in SEEDS:

        partition = la.find_partition(
            graph,
            la.RBConfigurationVertexPartition,
            weights="weight",
            resolution_parameter=resolution,
            n_iterations=N_ITERATIONS,
            seed=seed
        )

        memberships[seed] = partition.membership

    # Membandingkan semua pasangan seed
    ari_results = []

    for seed_a, seed_b in combinations(SEEDS, 2):

        ari = adjusted_rand_score(
            memberships[seed_a],
            memberships[seed_b]
        )

        ari_results.append({
            "quarter": quarter,
            "resolution": resolution,
            "seed_a": seed_a,
            "seed_b": seed_b,
            "ARI": ari
        })

    df_ari = pd.DataFrame(ari_results)

    mean_ari = df_ari["ARI"].mean()
    min_ari = df_ari["ARI"].min()

    print(f"Mean ARI : {mean_ari:.6f}")
    print(f"Min ARI  : {min_ari:.6f}")

    return df_ari


# ============================================================
# 3. MAIN PROGRAM
# ============================================================

def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    graph_files = sorted(
        GRAPH_DIR.glob("Q*/graph_Q*.graphml")
    )

    if not graph_files:
        raise FileNotFoundError(
            "GraphML tidak ditemukan."
        )

    all_profiles = []
    all_ari = []

    for graph_path in graph_files:

        quarter = graph_path.parent.name

        graph = ig.Graph.Read_GraphML(
            str(graph_path)
        )

        if not graph.is_directed():
            raise ValueError(
                f"{quarter} bukan directed graph."
            )

        if "weight" not in graph.es.attributes():
            raise ValueError(
                f"{quarter} tidak memiliki atribut weight."
            )

        # Eksplorasi resolution
        df_profile = explore_resolution(
            graph,
            quarter
        )

        all_profiles.append(df_profile)

        # Kandidat resolution dari profile
        candidate_resolutions = (
            df_profile["resolution"].tolist()
        )

        # Pengujian ARI untuk setiap kandidat
        for resolution in candidate_resolutions:

            df_ari = test_seed_stability(
                graph,
                quarter,
                resolution
            )

            all_ari.append(df_ari)

    # Menggabungkan hasil seluruh kuartal
    profile_output = (
        OUTPUT_DIR / "resolution_profile.csv"
    )

    ari_output = (
        OUTPUT_DIR / "seed_stability_ari.csv"
    )

    pd.concat(
        all_profiles,
        ignore_index=True
    ).to_csv(
        profile_output,
        index=False,
        encoding="utf-8-sig"
    )

    pd.concat(
        all_ari,
        ignore_index=True
    ).to_csv(
        ari_output,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n" + "=" * 65)
    print("SELESAI")
    print("=" * 65)

    print(f"Resolution profile: {profile_output}")
    print(f"ARI stability     : {ari_output}")


if __name__ == "__main__":
    main()
