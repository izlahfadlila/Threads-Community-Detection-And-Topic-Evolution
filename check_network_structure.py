
from pathlib import Path
import igraph as ig
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

GRAPH_DIR = BASE_DIR / "hasil_network" / "graph"


def inspect_network(graph_path):

    quarter = graph_path.parent.name

    graph = ig.Graph.Read_GraphML(str(graph_path))

    # Total degree: jumlah edge masuk + keluar
    total_degree = graph.degree(mode="all")

    # Weakly connected components
    components = graph.connected_components(mode="weak")

    component_sizes = sorted(
        components.sizes(),
        reverse=True
    )

    # Statistik node
    isolated = sum(d == 0 for d in total_degree)

    leaf_nodes = sum(d == 1 for d in total_degree)

    multi_connection = sum(d > 1 for d in total_degree)

    print("\n" + "=" * 55)
    print(f"NETWORK STRUCTURE: {quarter}")
    print("=" * 55)

    print(f"Jumlah node              : {graph.vcount()}")
    print(f"Jumlah directed edges    : {graph.ecount()}")
    print(f"Jumlah komponen          : {len(component_sizes)}")
    print(f"Komponen terbesar        : {component_sizes[0]}")
    print(f"Isolated nodes           : {isolated}")
    print(f"Leaf nodes               : {leaf_nodes}")
    print(f"Node dengan degree > 1   : {multi_connection}")

    print("\n10 komponen terbesar:")
    for i, size in enumerate(component_sizes[:10], start=1):
        print(f"{i}. {size} node")

    # Membuat tabel node
    df = pd.DataFrame({
        "username": graph.vs["name"],
        "in_degree": graph.degree(mode="in"),
        "out_degree": graph.degree(mode="out"),
        "total_degree": total_degree,
        "in_strength": graph.strength(
            mode="in", weights="weight"
        ),
        "out_strength": graph.strength(
            mode="out", weights="weight"
        ),
        "component_id": components.membership
    })

    # Node dengan degree paling rendah
    print("\n20 node dengan total degree terendah:")
    print(
        df.sort_values("total_degree")
        .head(20)
        .to_string(index=False)
    )

    output_path = (
        graph_path.parent /
        f"structure_{quarter}.csv"
    )

    df.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig"
    )

    print(f"\nHasil pemeriksaan: {output_path}")


def main():

    graph_files = sorted(
        GRAPH_DIR.glob("Q*/graph_Q*.graphml")
    )

    if not graph_files:
        raise FileNotFoundError("GraphML tidak ditemukan.")

    for graph_path in graph_files:
        inspect_network(graph_path)


if __name__ == "__main__":
    main()
