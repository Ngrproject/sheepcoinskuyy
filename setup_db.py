import psycopg2

# --- GANTI BAGIAN INI DENGAN LINK NEON ANDA ---
# (Pastikan pakai link 'postgresql://...' yang benar, TANPA 'psql' di depan)
DATABASE_URL = "postgresql://neondb_owner:npg_19NzQJniZclP@ep-still-recipe-aext9xrx-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require" 

def create_tables():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        
        print("Sedang membuat tabel...")

        # 1. Tabel Users
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                wallet TEXT PRIMARY KEY,
                username TEXT
            );
        """)

        # 2. Tabel Blocks
        c.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                id SERIAL PRIMARY KEY,
                idx INTEGER,
                timestamp REAL,
                proof INTEGER,
                previous_hash TEXT,
                miner TEXT
            );
        """)

        # 3. Tabel Transactions
        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                block_idx INTEGER,
                sender TEXT,
                recipient TEXT,
                amount REAL
            );
        """)

        # 4. Buat Genesis Block (Block Pertama)
        c.execute("SELECT COUNT(*) FROM blocks")
        if c.fetchone()[0] == 0:
            print("Membuat Genesis Block...")
            import time
            c.execute(
                "INSERT INTO blocks (idx, timestamp, proof, previous_hash, miner) VALUES (1, %s, 100, '1', 'System')",
                (time.time(),)
            )

        conn.commit()
        conn.close()
        print("✅ SUKSES! Database sudah siap. Silakan refresh website Anda.")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    create_tables()