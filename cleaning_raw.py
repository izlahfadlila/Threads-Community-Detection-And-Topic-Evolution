
import re
import pandas as pd
from pathlib import Path
from urllib.parse import urlparse, unquote


# ============================================================
# 1. KONFIGURASI FOLDER DAN FILE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

# Folder tempat CSV mentah berada
INPUT_DIR = BASE_DIR / "output"

# Folder tempat hasil cleaning disimpan
OUTPUT_DIR = BASE_DIR / "hasil_cleaning"
OUTPUT_DIR.mkdir(exist_ok=True)

FILE_CONFIG = {
    "Q3_2025": {
        "posts": "posts_indonesia_Q3_2025.csv",
        "comments": "comments_Q3_2025.csv",
        "replies": "replies_Q3_2025.csv"
    },

    "Q4_2025": {
        "posts": "posts_indonesia_Q4_2025.csv",
        "comments": "comments_Q4_2025.csv",
        "replies": "replies_Q4_2025.csv"
    }
}


# ============================================================
# 2. EKSTRAK USERNAME DARI URL THREADS
# ============================================================

def extract_username(url):

    if not isinstance(url, str) or not url.strip():
        return ""

    try:
        path = urlparse(url.strip()).path

        match = re.search(
            r"/@([^/]+)/post/",
            path,
            flags=re.IGNORECASE
        )

        if match:
            return unquote(match.group(1))

    except Exception:
        pass

    return ""


# ============================================================
# 3. MEMBERSIHKAN METADATA LOKASI DI AKHIR TEKS
# ============================================================

def remove_location_metadata(text):
    """
    Membersihkan pola metadata lokasi di akhir teks.

    Contoh:
    Bali, Indonesia 737 101 46 71
    Jakarta, Indonesia 1

    Hanya menghapus jika lokasi diikuti angka statistik
    dan berada di akhir teks.
    """

    if not isinstance(text, str):
        return ""

    location_pattern = (
        r"\s+"
        r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ.'’\-]*"
        r"(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÿ.'’\-]*)*"
        r",\s*Indonesia"
        r"\s+\d+(?:\s+\d+)*"
        r"\s*$"
    )

    return re.sub(
        location_pattern,
        "",
        text
    ).strip()


# ============================================================
# 4. FUNGSI CLEANING TEKS UMUM
# ============================================================

def clean_common_text(
    text,
    username=None,
    remove_unavailable=False,
    remove_creator=False,
    suffix_labels=None
):

    if not isinstance(text, str):
        return ""

    # Membersihkan karakter tersembunyi
    text = text.replace("\ufeff", "")
    text = text.replace("\u200b", "")
    text = text.replace("\xa0", " ")

    # Menghapus tanggal DD/MM/YYYY atau DD-MM-YYYY
    # di mana pun posisinya dalam teks
    text = re.sub(
        r"(?<!\d)\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b(?!\d)",
        " ",
        text
    )

    # Merapikan spasi
    text = re.sub(r"\s+", " ", text).strip()

    # --------------------------------------------------------
    # A. MEMBERSIHKAN BAGIAN AWAL TEKS
    # --------------------------------------------------------

    for _ in range(5):

        old_text = text

        # Menghapus username hanya jika cocok dengan URL
        if username:

            username_pattern = (
                r"^@?"
                + re.escape(username)
                + r"(?=$|\s|[,|:·])"
            )

            text = re.sub(
                username_pattern,
                "",
                text,
                count=1,
                flags=re.IGNORECASE
            )

        # Menghapus tanggal di awal teks
        # Contoh: 08/12/2025 atau 08-12-2025
        text = re.sub(
            r"^\d{1,2}[/-]\d{1,2}[/-]\d{4}\b",
            "",
            text,
            count=1
        )

        # Menghapus Pembuat hanya di awal teks
        if remove_creator:

            text = re.sub(
                r"^Pembuat\b",
                "",
                text,
                count=1,
                flags=re.IGNORECASE
            )

        # Menghapus keterangan postingan tidak tersedia
        if remove_unavailable:

            text = re.sub(
                r"^Balasan pada postingan yang tidak tersedia\b",
                "",
                text,
                count=1,
                flags=re.IGNORECASE
            )

        # Menghapus tanda pemisah setelah metadata awal
        text = re.sub(
            r"^[\s,|:·\-–—]+",
            "",
            text
        )

        text = text.strip()

        if text == old_text:
            break

    # --------------------------------------------------------
    # B. MEMBERSIHKAN LABEL UI DI AKHIR TEKS
    # --------------------------------------------------------

    if suffix_labels:

        for label in suffix_labels:

            pattern = (
                r"\s+"
                + re.escape(label)
                + r"(?:\s+\d+|\s*/)*\s*$"
            )

            text = re.sub(
                pattern,
                "",
                text,
                flags=re.IGNORECASE
            )

    # Merapikan kembali spasi
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ============================================================
# 4A. MENGHAPUS INDIKATOR CAROUSEL
# ============================================================

def remove_carousel_indicator(text, remove_engagement=False):
    """
    Menghapus indikator carousel di akhir teks.

    Jika remove_engagement=True, angka engagement
    yang berada setelah indikator carousel juga dihapus.
    """

    if not isinstance(text, str):
        return ""

    if remove_engagement:

        pattern = r"\s+\d+\s*/\s*\d+(?:\s+\d+)*\s*$"

    else:

        pattern = r"\s+\d+\s*/\s*\d+\s*$"

    return re.sub(
        pattern,
        "",
        text
    ).strip()


# ============================================================
# 4B. MENGHAPUS SEMUA ANGKA DI AKHIR TEKS POSTS
# ============================================================

def remove_trailing_numbers(text):
    """
    Menghapus seluruh rangkaian angka di bagian akhir teks.

    Mencakup:
    - Angka biasa: 471 63 25 29
    - Satu angka: 142
    - Format ribuan: 1 rb
    - Format desimal ribuan: 1,9 rb
    - Format carousel: 1 / 2 atau 2 / 2
    - Kombinasi carousel dan engagement.

    Hanya diterapkan pada data POSTS.
    Angka di tengah kalimat tetap dipertahankan.
    """

    if not isinstance(text, str):
        return ""

    pattern = (
        r"(?:\s+"
        r"(?:"
        r"\d+\s*/\s*\d+"
        r"|"
        r"\d+(?:[.,]\d+)?(?:\s*(?:rb|ribu))?"
        r")"
        r")+\s*$"
    )

    return re.sub(
        pattern,
        "",
        text,
        flags=re.IGNORECASE
    ).strip()


# ============================================================
# 5. MENGHAPUS DUPLIKASI BERDASARKAN ID
# ============================================================

def remove_duplicates_by_id(df, id_column):

    if id_column not in df.columns:

        print(
            f"PERINGATAN: Kolom {id_column} tidak ditemukan."
        )

        return df

    before = len(df)

    # Membersihkan spasi pada ID
    df[id_column] = df[id_column].astype(str).str.strip()

    # Pisahkan baris dengan ID dan tanpa ID
    has_id = df[id_column].ne("")

    df_with_id = df[has_id].drop_duplicates(
        subset=[id_column],
        keep="first"
    )

    df_without_id = df[~has_id]

    df = pd.concat(
        [df_with_id, df_without_id]
    ).sort_index()

    after = len(df)

    print(
        f"Duplikasi {id_column} dihapus: "
        f"{before - after} baris"
    )

    return df


# ============================================================
# 6. MENGATUR POSISI KOLOM USERNAME
# ============================================================

def move_column_after(df, column_name, after_column):

    if column_name not in df.columns:
        return df

    if after_column not in df.columns:
        return df

    columns = [
        col for col in df.columns
        if col != column_name
    ]

    position = columns.index(after_column)

    columns.insert(
        position + 1,
        column_name
    )

    return df[columns]


# ============================================================
# 7. CLEANING DATA POSTS
# ============================================================

def clean_posts(df):

    print("\nMemproses cleaning POSTS...")

    # Ekstraksi username pemilik postingan
    df["author_username"] = df["url"].apply(
        extract_username
    )

    cleaned_texts = []

    for text, username in zip(
        df["text"],
        df["author_username"]
    ):

        # Tahap pertama: membersihkan metadata lokasi
        text = remove_location_metadata(text)

        # Pastikan teks berupa string
        if not isinstance(text, str):
            text = ""

        # Menghapus frasa Balasan pada postingan
        # yang tidak tersedia
        text = re.sub(
            r"Balasan pada postingan yang tidak tersedia",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus Postingan tidak tersedia
        text = re.sub(
            r"Postingan tidak tersedia",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus Membalas @username
        text = re.sub(
            r"Membalas\s+@[A-Za-z0-9._-]+",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus kata Terjemahkan di mana pun posisinya
        text = re.sub(
            r"Terjemahkan",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus kata Konten AI
        text = re.sub(
            r"Konten\s+AI",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Tahap kedua: membersihkan metadata awal dan akhir
        cleaned = clean_common_text(
            text=text,
            username=username,
            remove_unavailable=True,
            remove_creator=False,
            suffix_labels=["Terjemahkan"]
        )

        # Menghapus seluruh angka di bagian akhir teks,
        # termasuk angka engagement dan indikator carousel
        cleaned = remove_trailing_numbers(cleaned)

        # Tahap ketiga: cek kembali lokasi di akhir
        cleaned = remove_location_metadata(cleaned)

        cleaned_texts.append(cleaned)

    df["text_cleaned"] = cleaned_texts

    # Menghapus duplikasi berdasarkan post_id.
    # Jika post_id sama ditemukan pada beberapa keyword,
    # hanya satu baris yang dipertahankan.
    # Keyword dari baris pertama tetap digunakan.
    df = remove_duplicates_by_id(
        df,
        "post_id"
    )

    # Menghapus kolom teks asli yang masih kotor
    df = df.drop(
        columns=["text"],
        errors="ignore"
    )

    # Username tepat setelah URL
    df = move_column_after(
        df,
        "author_username",
        "url"
    )

    return df


# ============================================================
# 8. CLEANING DATA COMMENTS
# ============================================================

def clean_comments(df):

    print("\nMemproses cleaning COMMENTS...")

    # Username pemilik postingan utama
    df["post_author_username"] = df["post_url"].apply(
        extract_username
    )

    # Username pembuat komentar
    df["author_username"] = df["comment_url"].apply(
        extract_username
    )

    cleaned_texts = []

    for text, username in zip(
        df["text"],
        df["author_username"]
    ):

        if not isinstance(text, str):
            text = ""

        # Menghapus Disematkan
        text = re.sub(
            r"\bDisematkan\b",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus Dikutip dengan postingan
        text = re.sub(
            r"Dikutip dengan postingan",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus Konten AI
        text = re.sub(
            r"Konten\s+AI",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus Terjemahkan di mana pun posisinya
        text = re.sub(
            r"Terjemahkan",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus Tampilkan balasan di mana pun posisinya
        text = re.sub(
            r"Tampilkan\s+balasan",
            " ",
            text,
            flags=re.IGNORECASE
        )

        cleaned = clean_common_text(
            text=text,
            username=username,
            remove_unavailable=False,
            remove_creator=True,
            suffix_labels=[
                "Terjemahkan",
                "Tampilkan balasan"
            ]
        )

        # Menghapus indikator carousel di akhir teks
        cleaned = remove_carousel_indicator(
            cleaned,
            remove_engagement=False
        )

        cleaned_texts.append(cleaned)

    df["text_cleaned"] = cleaned_texts

    # Menghapus duplikasi berdasarkan comment_id
    df = remove_duplicates_by_id(
        df,
        "comment_id"
    )

    # --------------------------------------------------------
    # MENGHAPUS KOMENTAR DENGAN TEKS KOSONG
    # --------------------------------------------------------

    # Mengumpulkan comment_id yang teks bersihnya kosong.
    # ID ini akan digunakan untuk menghapus reply turunannya.
    empty_comment_mask = (
        df["text_cleaned"].str.strip().eq("")
    )

    deleted_comment_ids = set(
        df.loc[
            empty_comment_mask,
            "comment_id"
        ].astype(str).str.strip()
    )

    # Tidak memasukkan ID kosong ke dalam daftar
    deleted_comment_ids.discard("")

    # Menghitung jumlah komentar kosong
    empty_count = empty_comment_mask.sum()

    # Menghapus komentar yang teks bersihnya kosong
    df = df.loc[
        ~empty_comment_mask
    ].copy()

    print(
        f"Komentar dengan teks kosong dihapus: {empty_count} baris"
    )

    print(
        "Jumlah comment_id yang dicatat untuk "
        f"penghapusan reply: {len(deleted_comment_ids)}"
    )

    # Menghapus kolom teks asli yang masih kotor
    df = df.drop(
        columns=["text"],
        errors="ignore"
    )

    # Username pembuat postingan setelah post_url
    df = move_column_after(
        df,
        "post_author_username",
        "post_url"
    )

    # Username pembuat komentar setelah comment_url
    df = move_column_after(
        df,
        "author_username",
        "comment_url"
    )

    return df, deleted_comment_ids


# ============================================================
# 9. CLEANING DATA REPLIES
# ============================================================

def clean_replies(df, deleted_comment_ids=None):

    print("\nMemproses cleaning REPLIES...")

    if deleted_comment_ids is None:
        deleted_comment_ids = set()

    # Username pemilik postingan utama
    df["post_author_username"] = df["post_url"].apply(
        extract_username
    )

    # Username pembuat komentar yang dibalas
    df["comment_author_username"] = df["comment_url"].apply(
        extract_username
    )

    # Username pembuat reply
    df["author_username"] = df["reply_url"].apply(
        extract_username
    )

    cleaned_texts = []

    for text, username in zip(
        df["text"],
        df["author_username"]
    ):

        if not isinstance(text, str):
            text = ""

        # Menghapus Dikutip dengan postingan
        text = re.sub(
            r"Dikutip dengan postingan",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus Disematkan
        text = re.sub(
            r"\bDisematkan\b",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus Konten AI
        text = re.sub(
            r"Konten\s+AI",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus Terjemahkan di mana pun posisinya
        text = re.sub(
            r"Terjemahkan",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Menghapus Tampilkan balasan di mana pun posisinya
        text = re.sub(
            r"Tampilkan\s+balasan",
            " ",
            text,
            flags=re.IGNORECASE
        )

        cleaned = clean_common_text(
            text=text,
            username=username,
            remove_unavailable=False,
            remove_creator=True,
            suffix_labels=[
                "Terjemahkan",
                "Tampilkan balasan"
            ]
        )

        # Menghapus indikator carousel di akhir teks
        cleaned = remove_carousel_indicator(
            cleaned,
            remove_engagement=False
        )

        cleaned_texts.append(cleaned)

    df["text_cleaned"] = cleaned_texts

    # Menghapus duplikasi berdasarkan reply_id
    df = remove_duplicates_by_id(
        df,
        "reply_id"
    )

    # --------------------------------------------------------
    # MENGHAPUS REPLY DENGAN TEKS KOSONG
    # --------------------------------------------------------

    empty_reply_mask = (
        df["text_cleaned"].str.strip().eq("")
    )

    empty_reply_count = empty_reply_mask.sum()

    df = df.loc[
        ~empty_reply_mask
    ].copy()

    print(
        f"Reply dengan teks kosong dihapus: "
        f"{empty_reply_count} baris"
    )

    # --------------------------------------------------------
    # MENGHAPUS REPLY DARI KOMENTAR YANG DIHAPUS
    # --------------------------------------------------------

    if deleted_comment_ids and "comment_id" in df.columns:

        # Membersihkan format comment_id
        df["comment_id"] = (
            df["comment_id"]
            .astype(str)
            .str.strip()
        )

        # Membersihkan format ID dalam daftar
        deleted_comment_ids = {
            str(comment_id).strip()
            for comment_id in deleted_comment_ids
        }

        # Mencari reply yang comment_id-nya termasuk
        # dalam daftar komentar kosong yang sudah dihapus
        reply_mask = df["comment_id"].isin(
            deleted_comment_ids
        )

        deleted_reply_count = reply_mask.sum()

        # Menghapus seluruh reply yang merujuk
        # pada komentar kosong tersebut
        df = df.loc[
            ~reply_mask
        ].copy()

        print(
            "Reply yang dihapus karena komentar induknya "
            f"kosong: {deleted_reply_count} baris"
        )

    else:

        print(
            "Tidak ada reply yang perlu dihapus "
            "berdasarkan comment_id."
        )

    # Menghapus kolom teks asli yang masih kotor
    df = df.drop(
        columns=["text"],
        errors="ignore"
    )

    # Username pemilik postingan setelah post_url
    df = move_column_after(
        df,
        "post_author_username",
        "post_url"
    )

    # Username pembuat komentar setelah comment_url
    df = move_column_after(
        df,
        "comment_author_username",
        "comment_url"
    )

    # Username pembuat reply setelah reply_url
    df = move_column_after(
        df,
        "author_username",
        "reply_url"
    )

    return df


# ============================================================
# 10. MEMBACA, MEMBERSIHKAN, DAN MENYIMPAN CSV
# ============================================================

def process_file(
    file_path,
    output_path,
    data_type,
    quarter,
    deleted_comment_ids=None
):

    if not file_path.exists():

        print(
            f"\nFILE TIDAK DITEMUKAN: {file_path.name}"
        )

        return None

    print(f"\nMembaca file: {file_path.name}")

    # Membaca seluruh kolom sebagai string
    df = pd.read_csv(
        file_path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig"
    )

    before = len(df)

    # Kolom wajib tiap jenis dataset
    required_columns = {

        "posts": [
            "post_id",
            "url",
            "timestamp",
            "text"
        ],

        "comments": [
            "post_url",
            "post_id",
            "comment_url",
            "comment_id",
            "timestamp",
            "text"
        ],

        "replies": [
            "post_url",
            "post_id",
            "comment_url",
            "comment_id",
            "reply_url",
            "reply_id",
            "timestamp",
            "text"
        ]
    }

    missing_columns = [
        col
        for col in required_columns[data_type]
        if col not in df.columns
    ]

    if missing_columns:

        print(
            "ERROR: Kolom wajib tidak ditemukan: "
            f"{missing_columns}"
        )

        return None

    # Jalankan cleaning sesuai jenis data
    if data_type == "posts":

        df = clean_posts(df)

    elif data_type == "comments":

        df, deleted_comment_ids = clean_comments(df)

    elif data_type == "replies":

        df = clean_replies(
            df,
            deleted_comment_ids=deleted_comment_ids
        )

    # Menambahkan informasi kuartal
    df["quarter"] = quarter

    # Statistik hasil cleaning
    empty_text = df["text_cleaned"].eq("").sum()

    # Menyimpan hasil cleaning
    df.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig"
    )

    print("\nHASIL CLEANING:")
    print(f"Jumlah baris sebelum cleaning : {before}")
    print(f"Jumlah baris setelah cleaning : {len(df)}")
    print(f"Teks kosong setelah cleaning  : {empty_text}")

    print(f"\nFile tersimpan: {output_path}")

    return deleted_comment_ids


# ============================================================
# 11. PROGRAM UTAMA
# ============================================================

def main():

    print("=" * 60)
    print("             PROGRAM CLEANING DATA THREADS")
    print("=" * 60)

    print("\nPilih kuartal yang ingin dibersihkan:")
    print("1. Q3_2025")
    print("2. Q4_2025")
    print("3. ALL (seluruh enam file)")

    choice = input(
        "\nMasukkan pilihan: "
    ).strip().upper()

    if choice == "1":

        selected_quarters = ["Q3_2025"]

    elif choice == "2":

        selected_quarters = ["Q4_2025"]

    elif choice in ["3", "ALL"]:

        selected_quarters = [
            "Q3_2025",
            "Q4_2025"
        ]

    elif choice in FILE_CONFIG:

        selected_quarters = [choice]

    else:

        print("\nPilihan tidak valid. Program dihentikan.")

        return

    print(
        "\nFolder hasil cleaning:",
        OUTPUT_DIR
    )

    # Menyimpan ID komentar kosong dari setiap quarter
    deleted_comment_ids_by_quarter = {}

    # --------------------------------------------------------
    # TAHAP 1: CLEANING POSTS DAN COMMENTS
    # --------------------------------------------------------

    # Posts dan comments diproses terlebih dahulu
    # agar seluruh comment_id kosong dapat dikumpulkan
    # sebelum file replies diproses.

    for quarter in selected_quarters:

        print("\n" + "=" * 60)
        print(f"MEMPROSES DATA {quarter}")
        print("=" * 60)

        files = FILE_CONFIG[quarter]

        # ---------------- POSTS ----------------

        posts_filename = files["posts"]

        posts_input_path = INPUT_DIR / posts_filename

        posts_output_filename = (
            Path(posts_filename).stem + "_cleaned.csv"
        )

        posts_output_path = (
            OUTPUT_DIR / posts_output_filename
        )

        process_file(
            file_path=posts_input_path,
            output_path=posts_output_path,
            data_type="posts",
            quarter=quarter
        )

        # ---------------- COMMENTS ----------------

        comments_filename = files["comments"]

        comments_input_path = INPUT_DIR / comments_filename

        comments_output_filename = (
            Path(comments_filename).stem + "_cleaned.csv"
        )

        comments_output_path = (
            OUTPUT_DIR / comments_output_filename
        )

        deleted_ids = process_file(
            file_path=comments_input_path,
            output_path=comments_output_path,
            data_type="comments",
            quarter=quarter
        )

        if deleted_ids is None:
            deleted_ids = set()

        deleted_comment_ids_by_quarter[quarter] = deleted_ids

    # --------------------------------------------------------
    # TAHAP 2: CLEANING REPLIES
    # --------------------------------------------------------

    # Setelah seluruh comments selesai dibersihkan,
    # baru replies diproses.
    #
    # Dengan demikian, replies yang memiliki comment_id
    # dari komentar kosong dapat ikut dihapus.

    for quarter in selected_quarters:

        print("\n" + "=" * 60)
        print(f"MEMPROSES REPLIES {quarter}")
        print("=" * 60)

        replies_filename = FILE_CONFIG[quarter]["replies"]

        replies_input_path = INPUT_DIR / replies_filename

        replies_output_filename = (
            Path(replies_filename).stem + "_cleaned.csv"
        )

        replies_output_path = (
            OUTPUT_DIR / replies_output_filename
        )

        deleted_ids = deleted_comment_ids_by_quarter.get(
            quarter,
            set()
        )

        process_file(
            file_path=replies_input_path,
            output_path=replies_output_path,
            data_type="replies",
            quarter=quarter,
            deleted_comment_ids=deleted_ids
        )

    print("\n" + "=" * 60)
    print("             PROSES CLEANING SELESAI")
    print("=" * 60)

    print(
        "\nSilakan periksa folder hasil_cleaning."
    )


# ============================================================
# 12. EKSEKUSI PROGRAM
# ============================================================

if __name__ == "__main__":

    main()
