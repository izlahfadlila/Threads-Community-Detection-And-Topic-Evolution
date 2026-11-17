
import pandas as pd
from pathlib import Path
import re


# ============================================================
# 1. KONFIGURASI FOLDER
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_DIR = BASE_DIR / "hasil_cleaning"
OUTPUT_DIR = BASE_DIR / "hasil_network"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. MEMBACA FILE CSV
# ============================================================

def read_csv_file(file_path):
    """
    Membaca file CSV hasil cleaning.
    Seluruh kolom dibaca sebagai string agar ID dan username
    tidak berubah format.
    """

    try:
        df = pd.read_csv(
            file_path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig"
        )

        return df

    except Exception as e:
        raise RuntimeError(
            f"Gagal membaca file {file_path.name}: {e}"
        )


# ============================================================
# 3. MENGIDENTIFIKASI QUARTER DARI NAMA FILE
# ============================================================

def extract_quarter(file_path):
    """
    Mengambil informasi quarter dari nama file.

    Contoh:
    comments_Q3_2025_cleaned.csv
    -> Q3_2025
    """

    match = re.search(
        r"_(Q[1-4]_\d{4})_cleaned\.csv$",
        file_path.name,
        flags=re.IGNORECASE
    )

    if match:
        return match.group(1).upper()

    return None


# ============================================================
# 4. MENGAMBIL HUBUNGAN DARI COMMENTS
# ============================================================

def extract_comment_edges(df):
    """
    Mengambil hubungan antar-user dari dataset comments.

    Source = author_username
    Target = post_author_username
    """

    required_columns = [
        "author_username",
        "post_author_username"
    ]

    for column in required_columns:
        if column not in df.columns:
            raise ValueError(
                f"Kolom '{column}' tidak ditemukan pada dataset comments."
            )

    edges = df[
        ["author_username", "post_author_username"]
    ].copy()

    edges.columns = ["source", "target"]

    return edges


# ============================================================
# 5. MENGAMBIL HUBUNGAN DARI REPLIES
# ============================================================

def extract_reply_edges(df):
    """
    Mengambil hubungan antar-user dari dataset replies.

    Source = author_username
    Target = comment_author_username
    """

    required_columns = [
        "author_username",
        "comment_author_username"
    ]

    for column in required_columns:
        if column not in df.columns:
            raise ValueError(
                f"Kolom '{column}' tidak ditemukan pada dataset replies."
            )

    edges = df[
        ["author_username", "comment_author_username"]
    ].copy()

    edges.columns = ["source", "target"]

    return edges


# ============================================================
# 6. MEMBERSIHKAN DAN MENGGABUNGKAN EDGE
# ============================================================

def prepare_edges(comment_edges, reply_edges):
    """
    Menggabungkan hubungan dari comments dan replies.

    Kemudian:
    - Menghapus username kosong.
    - Menghapus self-loop.
    - Menghitung Weight berdasarkan pasangan Source-Target.
    """

    # Menggabungkan seluruh interaksi
    edges = pd.concat(
        [comment_edges, reply_edges],
        ignore_index=True
    )

    total_interactions = len(edges)

    # Menghapus spasi di awal dan akhir username
    edges["source"] = edges["source"].str.strip()
    edges["target"] = edges["target"].str.strip()

    # Menghapus interaksi dengan username kosong
    empty_mask = (
        edges["source"].eq("")
        | edges["target"].eq("")
    )

    empty_count = int(empty_mask.sum())

    edges = edges.loc[~empty_mask].copy()

    # Menghapus self-loop
    self_loop_mask = (
        edges["source"] == edges["target"]
    )

    self_loop_count = int(self_loop_mask.sum())

    edges = edges.loc[~self_loop_mask].copy()

    # Menghitung Weight untuk setiap pasangan Source-Target
    edge_list = (
        edges
        .groupby(
            ["source", "target"],
            as_index=False
        )
        .size()
        .rename(columns={"size": "weight"})
    )

    # Mengurutkan hasil berdasarkan Source dan Target
    edge_list = edge_list.sort_values(
        by=["source", "target"]
    ).reset_index(drop=True)

    # Memastikan Weight berupa integer
    edge_list["weight"] = edge_list["weight"].astype(int)

    statistics = {
        "total_interactions": total_interactions,
        "empty_removed": empty_count,
        "self_loop_removed": self_loop_count,
        "valid_interactions": len(edges),
        "unique_edges": len(edge_list)
    }

    return edge_list, statistics


# ============================================================
# 7. MEMPROSES SATU QUARTER
# ============================================================

def process_quarter(quarter, comment_file, reply_file):
    """
    Memproses comments dan replies pada satu quarter,
    kemudian menghasilkan Weighted Edge List.
    """

    print("\n" + "=" * 60)
    print(f"MEMPROSES QUARTER: {quarter}")
    print("=" * 60)

    # Membaca dataset comments
    print(f"Membaca: {comment_file.name}")

    comments_df = read_csv_file(comment_file)

    # Membaca dataset replies
    print(f"Membaca: {reply_file.name}")

    replies_df = read_csv_file(reply_file)

    # Ekstraksi hubungan antar-user
    comment_edges = extract_comment_edges(comments_df)
    reply_edges = extract_reply_edges(replies_df)

    print("\nJumlah interaksi awal:")
    print(f"Comments : {len(comment_edges)}")
    print(f"Replies  : {len(reply_edges)}")

    # Menggabungkan dan menghitung Weight
    edge_list, stats = prepare_edges(
        comment_edges,
        reply_edges
    )

    # Menyimpan hasil
    output_file = OUTPUT_DIR / f"edge_list_{quarter}.csv"

    edge_list.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig"
    )

    # Menampilkan ringkasan
    print("\nHasil pemrosesan:")
    print(f"Total interaksi awal       : {stats['total_interactions']}")
    print(f"Username kosong dihapus    : {stats['empty_removed']}")
    print(f"Self-loop dihapus          : {stats['self_loop_removed']}")
    print(f"Interaksi valid            : {stats['valid_interactions']}")
    print(f"Jumlah edge unik           : {stats['unique_edges']}")

    print(f"\nFile berhasil disimpan:")
    print(output_file)

    return stats


# ============================================================
# 8. PROGRAM UTAMA
# ============================================================

def main():

    print("=" * 60)
    print("PEMBENTUKAN WEIGHTED EDGE LIST")
    print("PROJECT ANALISIS MEDIA SOSIAL")
    print("=" * 60)

    # Memastikan folder input tersedia
    if not INPUT_DIR.exists():
        print(
            f"\nERROR: Folder input tidak ditemukan: {INPUT_DIR}"
        )
        return

    # Mencari seluruh file comments dan replies
    comment_files = sorted(
        INPUT_DIR.glob("comments_*_cleaned.csv")
    )

    reply_files = sorted(
        INPUT_DIR.glob("replies_*_cleaned.csv")
    )

    # Membuat pemetaan file berdasarkan quarter
    comments_by_quarter = {}
    replies_by_quarter = {}

    for file in comment_files:
        quarter = extract_quarter(file)

        if quarter:
            if quarter in comments_by_quarter:
                raise ValueError(
                    f"Lebih dari satu file comments ditemukan "
                    f"untuk {quarter}."
                )

            comments_by_quarter[quarter] = file

    for file in reply_files:
        quarter = extract_quarter(file)

        if quarter:
            if quarter in replies_by_quarter:
                raise ValueError(
                    f"Lebih dari satu file replies ditemukan "
                    f"untuk {quarter}."
                )

            replies_by_quarter[quarter] = file

    # Mengidentifikasi quarter yang tersedia
    all_quarters = sorted(
        set(comments_by_quarter)
        | set(replies_by_quarter)
    )

    if not all_quarters:
        print(
            "\nERROR: Tidak ditemukan file comments atau replies "
            "hasil cleaning."
        )
        return

    print("\nQuarter yang ditemukan:")

    for quarter in all_quarters:
        print(f"- {quarter}")

    # Memastikan setiap quarter memiliki comments dan replies
    missing_files = []

    for quarter in all_quarters:

        if quarter not in comments_by_quarter:
            missing_files.append(
                f"comments_{quarter}_cleaned.csv"
            )

        if quarter not in replies_by_quarter:
            missing_files.append(
                f"replies_{quarter}_cleaned.csv"
            )

    if missing_files:
        print("\nERROR: Ada file yang belum ditemukan:")

        for filename in missing_files:
            print(f"- {filename}")

        print(
            "\nPastikan file comments dan replies "
            "untuk setiap quarter tersedia."
        )

        return

    # Memproses setiap quarter
    all_statistics = {}

    for quarter in all_quarters:

        stats = process_quarter(
            quarter,
            comments_by_quarter[quarter],
            replies_by_quarter[quarter]
        )

        all_statistics[quarter] = stats

    # Ringkasan akhir
    print("\n" + "=" * 60)
    print("SELESAI MEMPROSES SELURUH QUARTER")
    print("=" * 60)

    print("\nRingkasan hasil:")

    for quarter, stats in all_statistics.items():

        print(
            f"{quarter}: "
            f"{stats['unique_edges']} edge unik, "
            f"{stats['valid_interactions']} interaksi valid"
        )

    print(f"\nSeluruh file tersimpan di: {OUTPUT_DIR}")


# ============================================================
# 9. MENJALANKAN PROGRAM
# ============================================================

if __name__ == "__main__":
    main()
