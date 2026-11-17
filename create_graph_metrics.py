
from pathlib import Path
import re

import pandas as pd
import igraph as ig


# ============================================================
# 1. KONFIGURASI FOLDER
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_DIR = BASE_DIR / "hasil_network"
OUTPUT_DIR = INPUT_DIR / "graph"

REQUIRED_COLUMNS = ["source", "target", "weight"]


# ============================================================
# 2. MEMBACA DAN MEMVALIDASI EDGE LIST
# ============================================================

def read_edge_list(file_path):

    print(f"\nMembaca file: {file_path.name}")

    df = pd.read_csv(
        file_path,
        dtype={"source": str, "target": str},
        encoding="utf-8-sig"
    )

    # Periksa kolom
    missing_columns = [
        col for col in REQUIRED_COLUMNS
        if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Kolom tidak ditemukan: {missing_columns}"
        )

    df = df[REQUIRED_COLUMNS].copy()

    # Bersihkan username
    df["source"] = df["source"].fillna("").str.strip()
    df["target"] = df["target"].fillna("").str.strip()

    # Konversi weight menjadi numerik
    df["weight"] = pd.to_numeric(
        df["weight"],
        errors="coerce"
    )

    # Hapus baris dengan source/target kosong
    initial_rows = len(df)

    df = df[
        (df["source"] != "") &
        (df["target"] != "")
    ].copy()

    removed_empty = initial_rows - len(df)

    # Hapus weight tidak valid atau tidak positif
    initial_rows = len(df)

    df = df[
        df["weight"].notna() &
        (df["weight"] > 0) &
        (df["weight"] % 1 == 0)
    ].copy()

    removed_invalid_weight = initial_rows - len(df)

    # Hapus self-loop
    initial_rows = len(df)

    df = df[
        df["source"] != df["target"]
    ].copy()

    removed_self_loop = initial_rows - len(df)

    # Pastikan satu edge untuk setiap pasangan terarah.
    # Jika ada pasangan yang berulang, weight dijumlahkan.
    duplicate_count = df.duplicated(
        subset=["source", "target"]
    ).sum()

    df = (
        df.groupby(
            ["source", "target"],
            as_index=False
        )["weight"]
        .sum()
    )

    df["weight"] = df["weight"].astype(int)

    if df.empty:
        raise ValueError(
            f"Tidak ada edge valid pada {file_path.name}"
        )

    print(f"Edge valid              : {len(df)}")
    print(f"Baris source/target kosong: {removed_empty}")
    print(f"Weight tidak valid       : {removed_invalid_weight}")
    print(f"Self-loop dihapus        : {removed_self_loop}")
    print(f"Duplikasi pasangan       : {duplicate_count}")

    return df


# ============================================================
# 3. MEMBANGUN DIRECTED WEIGHTED GRAPH
# ============================================================

def build_graph(df):

    # Mengumpulkan seluruh username
    vertices = sorted(
        set(df["source"]) |
        set(df["target"])
    )

    # Membuat indeks untuk setiap username
    vertex_index = {
        username: index
        for index, username in enumerate(vertices)
    }

    # Mengubah username menjadi pasangan indeks
    edges = [
        (
            vertex_index[source],
            vertex_index[target]
        )
        for source, target in zip(
            df["source"],
            df["target"]
        )
    ]

    # Membuat directed graph
    graph = ig.Graph(
        n=len(vertices),
        edges=edges,
        directed=True
    )

    # Menyimpan username sebagai identitas node
    graph.vs["name"] = vertices

    # Menyimpan jumlah interaksi sebagai edge weight
    graph.es["weight"] = df["weight"].tolist()

    # Mengubah strength menjadi distance untuk betweenness.
    # Interaksi lebih kuat = jarak lebih pendek.
    graph.es["distance"] = [
        1.0 / weight
        for weight in df["weight"]
    ]

    return graph


# ============================================================
# 4. MENGHITUNG CENTRALITY DAN METRIK JARINGAN
# ============================================================

def calculate_metrics(graph, quarter):

    print("\nMenghitung metrik jaringan...")

    n = graph.vcount()

    # --------------------------------------------------------
    # A. IN-DEGREE DAN OUT-DEGREE
    # --------------------------------------------------------

    in_degree = graph.degree(mode="in")

    out_degree = graph.degree(mode="out")

    # --------------------------------------------------------
    # B. IN-STRENGTH DAN OUT-STRENGTH
    # --------------------------------------------------------

    in_strength = graph.strength(
        mode="in",
        weights="weight"
    )

    out_strength = graph.strength(
        mode="out",
        weights="weight"
    )

    # --------------------------------------------------------
    # C. DEGREE CENTRALITY
    # --------------------------------------------------------

    if n > 1:

        in_degree_centrality = [
            value / (n - 1)
            for value in in_degree
        ]

        out_degree_centrality = [
            value / (n - 1)
            for value in out_degree
        ]

        # Normalisasi total degree ke rentang 0-1
        total_degree_centrality = [
            (in_value + out_value) / (2 * (n - 1))
            for in_value, out_value in zip(
                in_degree,
                out_degree
            )
        ]

    else:

        in_degree_centrality = [0.0] * n
        out_degree_centrality = [0.0] * n
        total_degree_centrality = [0.0] * n

    # --------------------------------------------------------
    # D. BETWEENNESS CENTRALITY
    # --------------------------------------------------------

    print("  Menghitung betweenness...")

    betweenness = graph.betweenness(
        directed=True,
        weights="distance"
    )

    # Normalisasi directed betweenness
    if n > 2:

        betweenness_normalized = [
            value / ((n - 1) * (n - 2))
            for value in betweenness
        ]

    else:

        betweenness_normalized = [0.0] * n

    # --------------------------------------------------------
    # E. PAGERANK
    # --------------------------------------------------------

    print("  Menghitung PageRank...")

    pagerank = graph.pagerank(
        directed=True,
        damping=0.85,
        weights="weight"
    )

    # --------------------------------------------------------
    # F. MEMBUAT TABEL HASIL
    # --------------------------------------------------------

    metrics_df = pd.DataFrame({

        "username": graph.vs["name"],

        "quarter": [quarter] * n,

        "in_degree": in_degree,

        "out_degree": out_degree,

        "in_strength": in_strength,

        "out_strength": out_strength,

        "in_degree_centrality": in_degree_centrality,

        "out_degree_centrality": out_degree_centrality,

        "total_degree_centrality": total_degree_centrality,

        "betweenness": betweenness,

        "betweenness_normalized": betweenness_normalized,

        "pagerank": pagerank

    })

    # --------------------------------------------------------
    # G. MENAMBAHKAN METRIK KE ATRIBUT NODE GRAPH
    # --------------------------------------------------------

    for column in metrics_df.columns:

        if column not in ["username", "quarter"]:

            graph.vs[column] = metrics_df[column].tolist()

    graph.vs["quarter"] = [quarter] * n

    graph["quarter"] = quarter
    graph["graph_type"] = "directed_weighted"

    return metrics_df


# ============================================================
# 5. MEMPROSES SATU KUARTAL
# ============================================================

def process_quarter(file_path):

    # Mengambil nama kuartal dari nama file
    match = re.search(
        r"edge_list_(Q[1-4]_\d{4})\.csv$",
        file_path.name,
        re.IGNORECASE
    )

    if not match:
        print(f"Format nama file tidak dikenali: {file_path.name}")
        return

    quarter = match.group(1).upper()

    print("\n" + "=" * 60)
    print(f"MEMPROSES {quarter}")
    print("=" * 60)

    # Membaca edge list
    df = read_edge_list(file_path)

    # Membangun graph
    graph = build_graph(df)

    # Menghitung metrik
    metrics_df = calculate_metrics(
        graph,
        quarter
    )

    # Membuat folder output per kuartal
    quarter_dir = OUTPUT_DIR / quarter

    quarter_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # Menyimpan GraphML
    graphml_path = (
        quarter_dir /
        f"graph_{quarter}.graphml"
    )

    graph.write_graphml(str(graphml_path))

    # Menyimpan hasil metrik
    metrics_path = (
        quarter_dir /
        f"metrics_{quarter}.csv"
    )

    metrics_df.to_csv(
        metrics_path,
        index=False,
        encoding="utf-8-sig"
    )

    # Ringkasan hasil
    print("\nHASIL GRAPH")
    print("-" * 40)

    print(f"Quarter       : {quarter}")
    print(f"Jumlah node   : {graph.vcount()}")
    print(f"Jumlah edge   : {graph.ecount()}")
    print(f"Directed      : {graph.is_directed()}")
    print(
        f"Total weight  : {sum(graph.es['weight'])}"
    )

    print("\nOUTPUT")
    print(f"GraphML : {graphml_path}")
    print(f"Metrics : {metrics_path}")

    print(f"\nSelesai memproses {quarter}.")


# ============================================================
# 6. MAIN PROGRAM
# ============================================================

def main():

    print("=" * 60)
    print("DIRECTED WEIGHTED GRAPH & CENTRALITY ANALYSIS")
    print("=" * 60)

    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Folder input tidak ditemukan: {INPUT_DIR}"
        )

    # Mengambil seluruh edge list per kuartal
    input_files = sorted(
        INPUT_DIR.glob("edge_list_Q*_*.csv")
    )

    if not input_files:
        raise FileNotFoundError(
            "Tidak ditemukan file edge_list_Q*_*.csv "
            f"di folder {INPUT_DIR}"
        )

    print(f"\nJumlah file ditemukan: {len(input_files)}")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    successful = 0
    failed = []

    # Memproses seluruh kuartal
    for file_path in input_files:

        try:

            process_quarter(file_path)
            successful += 1

        except Exception as error:

            print(f"\nERROR pada {file_path.name}: {error}")

            failed.append(file_path.name)

    # Ringkasan akhir
    print("\n" + "=" * 60)
    print("PROSES SELESAI")
    print("=" * 60)

    print(f"Berhasil : {successful}")
    print(f"Gagal    : {len(failed)}")

    if failed:

        print("\nFile yang gagal diproses:")

        for filename in failed:
            print(f"- {filename}")

    print(f"\nFolder output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
