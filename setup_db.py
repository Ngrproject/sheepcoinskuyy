import psycopg2

# --- GANTI BAGIAN INI DENGAN LINK NEON ANDA ---
# (Pastikan pakai link 'postgresql://...' yang benar, TANPA 'psql' di depan)
DATABASE_URL = "postgresql://neondb_owner:npg_19NzQJniZclP@ep-still-recipe-aext9xrx-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require" 

def update_table():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        
        print("Sedang menambahkan kolom 'auto_mine_expires' ke tabel users...")
        
        # Perintah SQL untuk menambah kolom baru
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_mine_expires REAL DEFAULT 0")
        
        conn.commit()
        conn.close()
        print("✅ SUKSES! Kolom berhasil ditambahkan.")
        
    except Exception as e:
        print(f"❌ Error atau Kolom Sudah Ada: {e}")

if __name__ == "__main__":
    update_table()