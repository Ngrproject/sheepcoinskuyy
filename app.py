import hashlib
import json
import os
import psycopg2
from time import time
from datetime import datetime
from flask import Flask, jsonify, request, render_template

# ==========================================
# KONFIGURASI DAN DATABASE
# ==========================================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key')
DATABASE_URL = os.environ.get('DATABASE_URL') 

# Konfigurasi Game Mining
MINING_DIFFICULTY = 4 
BASE_REWARD = 1.0 

def get_db():
    # Membuka koneksi ke PostgreSQL (Neon Tech)
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    """Fungsi untuk membuat tabel database jika belum ada"""
    conn = get_db()
    c = conn.cursor()
    
    # 1. Tabel User
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        wallet TEXT PRIMARY KEY,
        username TEXT
    )
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
    )
    """)
    
    # 3. Tabel Transactions
    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY,
        block_idx INTEGER,
        sender TEXT,
        recipient TEXT,
        amount REAL
    )
    """)
    
    # 4. Cek Genesis Block (Block Pertama)
    c.execute("SELECT COUNT(*) FROM blocks")
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO blocks (idx, timestamp, proof, previous_hash, miner) VALUES (1, %s, 100, '1', 'System')",
            (time(),)
        )
    
    conn.commit()
    conn.close()

# ==========================================
# FUNGSI BANTUAN (HELPER)
# ==========================================

def hash_block(block):
    """Membuat hash SHA-256 dari sebuah block"""
    block_string = json.dumps(block, sort_keys=True).encode()
    return hashlib.sha256(block_string).hexdigest()

def verify_proof(last_proof, proof):
    """Memverifikasi apakah hasil mining valid"""
    guess = f'{last_proof}{proof}'.encode()
    guess_hash = hashlib.sha256(guess).hexdigest()
    return guess_hash.startswith("0" * MINING_DIFFICULTY)

def last_block():
    """Mengambil data block terakhir dari database"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT idx, timestamp, proof, previous_hash FROM blocks ORDER BY idx DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return {
        'index': row[0],
        'timestamp': row[1],
        'proof': row[2],
        'previous_hash': row[3]
    }

# ==========================================
# ROUTES (JALUR WEB)
# ==========================================

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/init_db_manual')
def init_db_manual():
    """Jalur darurat untuk membuat tabel jika server error"""
    try:
        init_db()
        return "Database berhasil diinisialisasi! Tabel siap."
    except Exception as e:
        return f"Error inisialisasi: {str(e)}"

@app.route('/wallet_info', methods=['POST'])
def wallet_info():
    """Mengambil saldo user"""
    data = request.get_json()
    wallet_id = data.get('address')
    
    conn = get_db()
    c = conn.cursor()
    
    # Daftar user baru jika belum ada
    c.execute("INSERT INTO users (wallet, username) VALUES (%s, 'Miner') ON CONFLICT (wallet) DO NOTHING", (wallet_id,))
    conn.commit()

    # Hitung Saldo (Total Masuk - Total Keluar)
    c.execute("""
        SELECT 
        COALESCE(SUM(CASE WHEN recipient=%s THEN amount ELSE 0 END), 0) -
        COALESCE(SUM(CASE WHEN sender=%s THEN amount ELSE 0 END), 0)
        FROM transactions
    """, (wallet_id, wallet_id))
    balance = c.fetchone()[0]
    
    conn.close()
    return jsonify({'balance': balance, 'node_id': wallet_id})

@app.route('/get_mining_job')
def get_mining_job():
    """Memberikan data block terakhir agar client bisa mining"""
    last = last_block()
    return jsonify({
        'last_proof': last['proof'],
        'last_hash': hash_block(last), 
        'index': last['index'] + 1,
        'difficulty': MINING_DIFFICULTY
    })

@app.route('/submit_block', methods=['POST'])
def submit_block():
    """Menerima hasil mining dari user"""
    data = request.get_json()
    proof = data.get('proof')
    miner_address = data.get('miner')
    
    last = last_block()
    
    # 1. Verifikasi Proof
    if not verify_proof(last['proof'], proof):
        return jsonify({'message': 'Proof Salah/Ditolak!', 'success': False}), 400
        
    # 2. Simpan Block Baru
    conn = get_db()
    c = conn.cursor()
    
    new_index = last['index'] + 1
    
    c.execute(
        "INSERT INTO blocks (idx, timestamp, proof, previous_hash, miner) VALUES (%s, %s, %s, %s, %s)",
        (new_index, time(), proof, hash_block(last), miner_address)
    )
    
    # 3. Beri Reward Mining
    c.execute(
        "INSERT INTO transactions (block_idx, sender, recipient, amount) VALUES (%s, '0', %s, %s)",
        (new_index, miner_address, BASE_REWARD)
    )
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Block Diterima! Reward dikirim.', 'success': True, 'reward': BASE_REWARD})

@app.route('/chain')
def chain():
    """Melihat 10 block terakhir (Global)"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT idx, timestamp, proof, previous_hash, miner FROM blocks ORDER BY idx DESC LIMIT 10")
    rows = c.fetchall()
    blocks = []
    for r in rows:
        blocks.append({
            'index': r[0],
            'timestamp': datetime.fromtimestamp(r[1]).strftime('%Y-%m-%d %H:%M:%S'),
            'proof': r[2],
            'hash': r[3],
            'miner': r[4]
        })
    conn.close()
    return jsonify({'chain': blocks})

@app.route('/transact', methods=['POST'])
def transact():
    """Memproses transfer koin"""
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    
    # Tempel transaksi ke block terakhir yang ada
    c.execute("SELECT idx FROM blocks ORDER BY idx DESC LIMIT 1")
    last_idx = c.fetchone()[0]
    
    c.execute(
        "INSERT INTO transactions (block_idx, sender, recipient, amount) VALUES (%s, %s, %s, %s)",
        (last_idx, data['sender'], data['recipient'], data['amount'])
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Transaksi sukses'})

@app.route('/my_transactions', methods=['POST'])
def my_transactions():
    """Mengambil riwayat transaksi KHUSUS user yang login"""
    data = request.get_json()
    wallet = data.get('address')
    
    conn = get_db()
    c = conn.cursor()
    
    # Ambil 10 transaksi terakhir dimana user terlibat (sender ATAU recipient)
    c.execute("""
        SELECT sender, recipient, amount, block_idx 
        FROM transactions 
        WHERE sender = %s OR recipient = %s
        ORDER BY id DESC LIMIT 10
    """, (wallet, wallet))
    
    rows = c.fetchall()
    txs = []
    for r in rows:
        # Tentukan tipe transaksi
        tx_type = 'IN' if r[1] == wallet else 'OUT'
        if r[0] == '0': tx_type = 'MINING' # 0 adalah kode sistem (Reward Mining)
        
        txs.append({
            'sender': r[0],
            'recipient': r[1],
            'amount': r[2],
            'block': r[3],
            'type': tx_type
        })
        
    conn.close()
    return jsonify({'transactions': txs})

if __name__ == '__main__':
    # init_db() # Bisa diaktifkan untuk test lokal
    app.run(debug=True)