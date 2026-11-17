
from pathlib import Path
import math

import igraph as ig
import matplotlib.pyplot as plt


# ============================================================
# 1. KONFIGURASI
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

GRAPH_DIR = BASE_DIR / "hasil_network" / "graph"

OUTPUT_DIR = BASE_DIR / "hasil_network" / "visualisasi"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Gunakan backend Matplotlib
ig.config["plotting.backend"] = "matplotlib"


# ============================================================
# 2. FUNGSI MEMBUAT UKURAN NODE
# ============================================================

def calculate_vertex_sizes(graph):

    if "pagerank" in graph.vs.attributes():

        values = graph.vs["pagerank"]

    else:

        values = graph.degree(mode="all")

    max_value = max(values) if values else 0

    if max_value == 0:
        return [5] * graph.vcount()

    sizes = [
        5 + (15 * value / max_value)
        for value in values
    ]

    return sizes


# ============================================================
# 3. FUNGSI MENGATUR KETEBALAN EDGE
# ============================================================

def calculate_edge_widths(graph):

    weights = graph.es["weight"]

    max_weight = max(weights) if weights else 1

    max_log = math.log1p(max_weight)

    if max_log == 0:
        return [0.5] * graph.ecount()

    widths = [
        0.4 + 2.0 * math.log1p(weight) / max_log
        for weight in weights
    ]

    return widths


# ============================================================
# 4. VISUALISASI GRAPH
# ============================================================

def visualize_graph(graphml_path):

    quarter = graphml_path.parent.name

    print("\n" + "=" * 55)
    print(f"VISUALISASI NETWORK {quarter}")
    print("=" * 55)

    # Membaca graph
    graph = ig.Graph.Read_GraphML(str(graphml_path))

    print(f"Jumlah node : {graph.vcount()}")
    print(f"Jumlah edge : {graph.ecount()}")
    print(f"Directed    : {graph.is_directed()}")

    # Pastikan graph berarah
    if not graph.is_directed():

        raise ValueError(
            "Graph yang dibaca bukan directed graph."
        )

    # --------------------------------------------------------
    # A. MENGHITUNG LAYOUT
    # --------------------------------------------------------

    print("\nMenghitung layout jaringan...")

    # DrL cocok untuk visualisasi jaringan berukuran besar
    layout = graph.layout_drl()

    # --------------------------------------------------------
    # B. MENGATUR UKURAN NODE
    # --------------------------------------------------------

    vertex_sizes = calculate_vertex_sizes(graph)

    # --------------------------------------------------------
    # C. MENGATUR KETEBALAN EDGE
    # --------------------------------------------------------

    edge_widths = calculate_edge_widths(graph)

    # --------------------------------------------------------
    # D. MEMBUAT VISUALISASI
    # --------------------------------------------------------

    print("Membuat visualisasi...")

    fig, ax = plt.subplots(figsize=(18, 16))

    ig.plot(
        graph,

        target=ax,

        layout=layout,

        vertex_size=vertex_sizes,

        vertex_color="steelblue",

        vertex_frame_color="white",

        vertex_frame_width=0.3,

        vertex_label=None,

        edge_width=edge_widths,

        edge_color="gray",

        edge_arrow_size=0.25,

        edge_arrow_width=0.8,

        edge_curved=0.15
    )

    ax.set_title(
        f"Directed Weighted Network - {quarter}",
        fontsize=16
    )

    ax.set_axis_off()

    plt.tight_layout()

    # --------------------------------------------------------
    # E. MENYIMPAN GAMBAR
    # --------------------------------------------------------

    output_path = (
        OUTPUT_DIR /
        f"network_{quarter}.png"
    )

    fig.savefig(
        output_path,
        dpi=250,
        bbox_inches="tight"
    )

    plt.close(fig)

    print(f"\nVisualisasi berhasil disimpan:")
    print(output_path)


# ============================================================
# 5. MAIN PROGRAM
# ============================================================

def main():

    print("=" * 55)
    print("NETWORK VISUALIZATION")
    print("=" * 55)

    if not GRAPH_DIR.exists():

        raise FileNotFoundError(
            f"Folder graph tidak ditemukan: {GRAPH_DIR}"
        )

    graph_files = sorted(
        GRAPH_DIR.glob("Q*/graph_Q*.graphml")
    )

    if not graph_files:

        raise FileNotFoundError(
            "Tidak ditemukan file GraphML."
        )

    successful = 0

    failed = []

    for graphml_path in graph_files:

        try:

            visualize_graph(graphml_path)

            successful += 1

        except Exception as error:

            print(
                f"\nGagal memvisualisasikan "
                f"{graphml_path.name}: {error}"
            )

            failed.append(graphml_path.name)

    print("\n" + "=" * 55)
    print("VISUALISASI SELESAI")
    print("=" * 55)

    print(f"Berhasil : {successful}")
    print(f"Gagal    : {len(failed)}")

    print(f"\nFolder output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
