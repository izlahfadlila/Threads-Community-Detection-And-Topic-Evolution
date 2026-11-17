
from pathlib import Path
import re

import igraph as ig
import leidenalg as la
import pandas as pd


# ============================================================
# KONFIGURASI
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

GRAPH_DIR = BASE_DIR / "hasil_network" / "graph"

# Parameter Leiden
RESOLUTION_PARAMETER = 1.0
RANDOM_SEED = 42
N_ITERATIONS = -1


# ============================================================
# MEMBACA GRAPH DAN MENJALANKAN LEIDEN
# ============================================================

def detect_communities(graph_path):

    quarter = graph_path.parent.name

    print("\n" + "=" * 65)
    print(f"COMMUNITY DETECTION: {quarter}")
    print("=" * 65)

    # --------------------------------------------------------
    # 1. Membaca GraphML
    # --------------------------------------------------------

    graph = ig.Graph.Read_GraphML(str(graph_path))

    if not graph.is_directed():
        raise ValueError(
            f"Graph {quarter} bukan directed graph."
        )

    if graph.vcount() == 0:
        raise ValueError(
            f"Graph {quarter} tidak memiliki node."
        )

    if graph.ecount() == 0:
        raise ValueError(
            f"Graph {quarter} tidak memiliki edge."
        )

    if "name" not in graph.vs.attributes():
        raise ValueError(
            f"Graph {quarter} tidak memiliki atribut node 'name'."
        )

    if "weight" not in graph.es.attributes():
        raise ValueError(
            f"Graph {quarter} tidak memiliki atribut edge 'weight'."
        )

    # Memastikan seluruh weight berupa angka positif
    weights = [float(w) for w in graph.es["weight"]]

    if any(w <= 0 for w in weights):
        raise ValueError(
            f"Graph {quarter} memiliki weight nol atau negatif."
        )

    graph.es["weight"] = weights

    print(f"Jumlah node           : {graph.vcount()}")
    print(f"Jumlah directed edges : {graph.ecount()}")
    print(f"Directed graph        : {graph.is_directed()}")
    print(f"Resolution parameter  : {RESOLUTION_PARAMETER}")

    # --------------------------------------------------------
    # 2. Menjalankan Algoritma Leiden
    # --------------------------------------------------------

    print("\nMenjalankan Leiden...")

    partition = la.find_partition(
        graph,
        la.RBConfigurationVertexPartition,
        weights="weight",
        resolution_parameter=RESOLUTION_PARAMETER,
        n_iterations=N_ITERATIONS,
        seed=RANDOM_SEED
    )

    # Community membership setiap node
    membership = partition.membership

    # Menambahkan Community ID ke atribut node
    graph.vs["community_id"] = membership

    # --------------------------------------------------------
    # 3. Membuat Tabel Keanggotaan Komunitas
    # --------------------------------------------------------

    df_nodes = pd.DataFrame({
        attribute: graph.vs[attribute]
        for attribute in graph.vs.attributes()
    })

    # Mengganti nama atribut name menjadi username
    df_nodes = df_nodes.rename(
        columns={"name": "username"}
    )

    # Menghitung jumlah anggota setiap komunitas
    community_sizes = (
        df_nodes["community_id"]
        .value_counts()
        .to_dict()
    )

    df_nodes["community_size"] = (
        df_nodes["community_id"]
        .map(community_sizes)
    )

    # Mengurutkan berdasarkan Community ID
    df_nodes = df_nodes.sort_values(
        ["community_id", "username"]
    ).reset_index(drop=True)

    # --------------------------------------------------------
    # 4. Membuat Ringkasan Setiap Komunitas
    # --------------------------------------------------------

    community_stats = {}

    for community_id in sorted(set(membership)):

        community_stats[community_id] = {
            "community_id": community_id,
            "community_size": 0,
            "internal_edges": 0,
            "internal_weight": 0.0,
            "external_edges": 0,
            "external_weight": 0.0
        }

    # Menghitung ukuran komunitas
    for community_id, size in community_sizes.items():

        community_stats[community_id][
            "community_size"
        ] = size

    # Menghitung edge internal dan eksternal
    for edge in graph.es:

        source = edge.source
        target = edge.target

        source_community = membership[source]
        target_community = membership[target]

        weight = float(edge["weight"])

        if source_community == target_community:

            community_stats[source_community][
                "internal_edges"
            ] += 1

            community_stats[source_community][
                "internal_weight"
            ] += weight

        else:

            community_stats[source_community][
                "external_edges"
            ] += 1

            community_stats[source_community][
                "external_weight"
            ] += weight

    df_summary = pd.DataFrame(
        list(community_stats.values())
    )

    df_summary = df_summary.sort_values(
        "community_size",
        ascending=False
    ).reset_index(drop=True)

    # Persentase anggota terhadap keseluruhan node
    df_summary["percentage"] = (
        df_summary["community_size"]
        / graph.vcount()
        * 100
    )

    # --------------------------------------------------------
    # 5. Menyimpan Hasil
    # --------------------------------------------------------

    output_dir = graph_path.parent

    # File keanggotaan setiap node
    node_output = (
        output_dir /
        f"community_{quarter}.csv"
    )

    df_nodes.to_csv(
        node_output,
        index=False,
        encoding="utf-8-sig"
    )

    # File ringkasan setiap komunitas
    summary_output = (
        output_dir /
        f"community_summary_{quarter}.csv"
    )

    df_summary.to_csv(
        summary_output,
        index=False,
        encoding="utf-8-sig"
    )

    # GraphML dengan atribut Community ID
    graph_output = (
        output_dir /
        f"graph_{quarter}_leiden.graphml"
    )

    graph.write_graphml(str(graph_output))

    # --------------------------------------------------------
    # 6. Menampilkan Ringkasan Hasil
    # --------------------------------------------------------

    print("\n" + "-" * 65)
    print("HASIL COMMUNITY DETECTION")
    print("-" * 65)

    print(f"Jumlah komunitas      : {len(community_sizes)}")
    print(f"Modularity/Quality    : {partition.quality():.6f}")
    print(f"Resolution            : {RESOLUTION_PARAMETER}")

    print("\n10 komunitas terbesar:")

    print(
        df_summary[
            [
                "community_id",
                "community_size",
                "percentage",
                "internal_edges",
                "internal_weight"
            ]
        ]
        .head(10)
        .to_string(index=False)
    )

    print("\nFile berhasil disimpan:")
    print(f"1. {node_output}")
    print(f"2. {summary_output}")
    print(f"3. {graph_output}")

    return df_summary


# ============================================================
# MAIN PROGRAM
# ============================================================

def main():

    if not GRAPH_DIR.exists():
        raise FileNotFoundError(
            f"Folder graph tidak ditemukan: {GRAPH_DIR}"
        )

    # Hanya membaca GraphML asli, bukan hasil Leiden
    graph_files = sorted(
        path
        for path in GRAPH_DIR.glob("Q*/graph_Q*.graphml")
        if re.fullmatch(
            r"graph_Q[1-4]_\d{4}\.graphml",
            path.name
        )
    )

    if not graph_files:
        raise FileNotFoundError(
            "GraphML asli tidak ditemukan."
        )

    print("=" * 65)
    print("LEIDEN COMMUNITY DETECTION")
    print("=" * 65)

    print(f"Jumlah graph ditemukan: {len(graph_files)}")

    all_summaries = []

    for graph_path in graph_files:

        df_summary = detect_communities(graph_path)

        all_summaries.append(df_summary)

    print("\n" + "=" * 65)
    print("SELESAI MEMPROSES SELURUH KUARTAL")
    print("=" * 65)


if __name__ == "__main__":
    main()
