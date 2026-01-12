import hashlib
import json
import os
import psycopg2
from time import time
from datetime import datetime
from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key')

# Gunakan URL Database dari Environment Variable (untuk Render/Neon)
# Jika tes lokal, ganti string di bawah dengan koneksi Neon Anda
DATABASE_URL = os.environ.get('DATABASE_URL') 

# KONFIGURASI GAME
MINING_DIFFICULTY = 4 
BASE_REWARD = 1.0 # Reward

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Buat Tabel Users
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        wallet TEXT PRIMARY KEY,
        username TEXT
    )
    """)
    
    # Buat Tabel Blocks
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
    
    # Buat Tabel Transactions
    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY,
        block_idx INTEGER,
        sender TEXT,
        recipient TEXT,
        amount REAL
    )
    """)
    
    # Cek Genesis Block
    c.execute("SELECT COUNT(*) FROM blocks")
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO blocks (idx, timestamp, proof, previous_hash, miner) VALUES (1, %s, 100, '1', 'System')",
            (time(),)
        )
    
    conn.commit()
    conn.close()

# --- HELPER ---
def hash_block(block):
    # Kita buat hash sederhana dari properti blok
    block_string = json.dumps(block, sort_keys=True).encode()
    return hashlib.sha256(block_string).hexdigest()

def verify_proof(last_proof, proof):
    # Verifikasi apakah hash dimulai dengan 0000 (sesuai difficulty)
    guess = f'{last_proof}{proof}'.encode()
    guess_hash = hashlib.sha256(guess).hexdigest()
    return guess_hash.startswith("0" * MINING_DIFFICULTY)

def last_block():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT idx, timestamp, proof, previous_hash FROM blocks ORDER BY idx DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return {'index': row[0], 'timestamp': row[1], 'proof': row[2], 'previous_hash': row[3]}

# --- ROUTES ---

@app.route('/')
def dashboard():
    return render_template('index.html') # Logic login dipindah ke frontend (MetaMask)

@app.route('/wallet_info', methods=['POST'])
def wallet_info():
    data = request.get_json()
    wallet_id = data.get('address')
    
    conn = get_db()
    c = conn.cursor()
    
    # Simpan user jika belum ada
    c.execute("INSERT INTO users (wallet, username) VALUES (%s, 'Miner') ON CONFLICT (wallet) DO NOTHING", (wallet_id,))
    conn.commit()

    # Hitung Saldo
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
    # Endpoint bagi Client untuk meminta data blok terakhir agar bisa mulai mining
    last = last_block()
    return jsonify({
        'last_proof': last['proof'],
        'last_hash': hash_block(last), # Hash blok terakhir untuk rantai
        'index': last['index'] + 1,
        'difficulty': MINING_DIFFICULTY
    })

@app.route('/submit_block', methods=['POST'])
def submit_block():
    data = request.get_json()
    proof = data.get('proof')
    miner_address = data.get('miner')
    
    last = last_block()
    
    # 1. Verifikasi Proof of Work (Dilakukan Server)
    if not verify_proof(last['proof'], proof):
        return jsonify({'message': 'Proof Salah/Ditolak!', 'success': False}), 400
        
    # 2. Jika Benar, Masukkan ke DB
    conn = get_db()
    c = conn.cursor()
    
    new_index = last['index'] + 1
    
    # Catat Block
    c.execute(
        "INSERT INTO blocks (idx, timestamp, proof, previous_hash, miner) VALUES (%s, %s, %s, %s, %s)",
        (new_index, time(), proof, hash_block(last), miner_address)
    )
    
    # Beri Reward
    c.execute(
        "INSERT INTO transactions (block_idx, sender, recipient, amount) VALUES (%s, '0', %s, %s)",
        (new_index, miner_address, BASE_REWARD)
    )
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Block Diterima! Reward dikirim.', 'success': True, 'reward': BASE_REWARD})

@app.route('/chain')
def chain():
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
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    
    # Ambil index block terakhir utk menempelkan transaksi
    c.execute("SELECT idx FROM blocks ORDER BY idx DESC LIMIT 1")
    last_idx = c.fetchone()[0]
    
    c.execute(
        "INSERT INTO transactions (block_idx, sender, recipient, amount) VALUES (%s, %s, %s, %s)",
        (last_idx, data['sender'], data['recipient'], data['amount'])
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Transaksi sukses'})

if __name__ == '__main__':
    # Init DB hanya perlu sekali, bisa di-comment setelah deploy pertama
    # init_db() 
    app.run(debug=True)