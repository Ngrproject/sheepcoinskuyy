import hashlib
import json
import os
import psycopg2
import random  # Import Random
from time import time
from datetime import datetime
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key')
DATABASE_URL = os.environ.get('DATABASE_URL') 

MINING_DIFFICULTY = 4 

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Update Tabel Users: Tambah kolom auto_mine_expires jika belum ada
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        wallet TEXT PRIMARY KEY,
        username TEXT
    )
    """)
    # Migrasi manual untuk user lama agar punya kolom expired
    try:
        c.execute("ALTER TABLE users ADD COLUMN auto_mine_expires REAL DEFAULT 0")
        conn.commit()
    except:
        conn.rollback() # Kolom sudah ada

    c.execute("CREATE TABLE IF NOT EXISTS blocks (id SERIAL PRIMARY KEY, idx INTEGER, timestamp REAL, proof INTEGER, previous_hash TEXT, miner TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, block_idx INTEGER, sender TEXT, recipient TEXT, amount REAL)")
    
    c.execute("SELECT COUNT(*) FROM blocks")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO blocks (idx, timestamp, proof, previous_hash, miner) VALUES (1, %s, 100, '1', 'System')", (time(),))
    
    conn.commit()
    conn.close()

# --- HELPER ---
def hash_block(block):
    block_string = json.dumps(block, sort_keys=True).encode()
    return hashlib.sha256(block_string).hexdigest()

def verify_proof(last_proof, proof):
    guess = f'{last_proof}{proof}'.encode()
    return hashlib.sha256(guess).hexdigest().startswith("0" * MINING_DIFFICULTY)

def last_block():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT idx, timestamp, proof, previous_hash FROM blocks ORDER BY idx DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return {'index': row[0], 'timestamp': row[1], 'proof': row[2], 'previous_hash': row[3]}

def get_balance(wallet_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(CASE WHEN recipient=%s THEN amount ELSE 0 END), 0) -
        COALESCE(SUM(CASE WHEN sender=%s THEN amount ELSE 0 END), 0)
        FROM transactions
    """, (wallet_id, wallet_id))
    bal = c.fetchone()[0]
    conn.close()
    return bal

# --- ROUTES ---

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/init_db_manual')
def init_db_manual():
    try:
        init_db()
        return "Database & Kolom Auto Mine berhasil diinisialisasi!"
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/wallet_info', methods=['POST'])
def wallet_info():
    data = request.get_json()
    wallet_id = data.get('address')
    
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO users (wallet, username) VALUES (%s, 'Miner') ON CONFLICT (wallet) DO NOTHING", (wallet_id,))
    
    # Ambil info expired auto mine
    c.execute("SELECT auto_mine_expires FROM users WHERE wallet=%s", (wallet_id,))
    row = c.fetchone()
    expires = row[0] if row else 0
    
    conn.commit()
    conn.close()
    
    balance = get_balance(wallet_id)
    
    return jsonify({
        'balance': balance, 
        'node_id': wallet_id,
        'auto_mine_expires': expires,
        'server_time': time()
    })

@app.route('/buy_auto_mine', methods=['POST'])
def buy_auto_mine():
    data = request.get_json()
    wallet = data.get('address')
    duration_minutes = data.get('minutes') # 10, 30, atau 60
    cost = 0
    
    if duration_minutes == 10: cost = 0.5
    elif duration_minutes == 30: cost = 1.0
    elif duration_minutes == 60: cost = 2.0
    else: return jsonify({'success': False, 'message': 'Paket tidak valid'}), 400
    
    current_balance = get_balance(wallet)
    if current_balance < cost:
        return jsonify({'success': False, 'message': 'Saldo tidak cukup!'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # 1. Potong Saldo (Buat Transaksi ke System '0')
    c.execute("SELECT idx FROM blocks ORDER BY idx DESC LIMIT 1")
    last_idx = c.fetchone()[0]
    c.execute("INSERT INTO transactions (block_idx, sender, recipient, amount) VALUES (%s, %s, '0', %s)", 
              (last_idx, wallet, cost))
    
    # 2. Update Waktu Expired
    # Jika masih aktif, tambah waktunya. Jika mati, mulai dari sekarang.
    c.execute("SELECT auto_mine_expires FROM users WHERE wallet=%s", (wallet,))
    current_expire = c.fetchone()[0] or 0
    now = time()
    
    new_expire = max(now, current_expire) + (duration_minutes * 60)
    
    c.execute("UPDATE users SET auto_mine_expires = %s WHERE wallet=%s", (new_expire, wallet))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': f'Auto Mine {duration_minutes} Menit Aktif!'})

@app.route('/get_mining_job')
def get_mining_job():
    last = last_block()
    return jsonify({
        'last_proof': last['proof'],
        'last_hash': hash_block(last), 
        'index': last['index'] + 1,
        'difficulty': MINING_DIFFICULTY
    })

@app.route('/submit_block', methods=['POST'])
def submit_block():
    data = request.get_json()
    proof = data.get('proof')
    miner_address = data.get('miner')
    last = last_block()
    
    if not verify_proof(last['proof'], proof):
        return jsonify({'message': 'Proof Salah!', 'success': False}), 400
        
    # --- FITUR RANDOM REWARD ---
    # Reward acak 0.001 - 1.0
    reward = round(random.uniform(0.001, 1.0), 4)
    
    conn = get_db()
    c = conn.cursor()
    new_index = last['index'] + 1
    
    c.execute("INSERT INTO blocks (idx, timestamp, proof, previous_hash, miner) VALUES (%s, %s, %s, %s, %s)",
              (new_index, time(), proof, hash_block(last), miner_address))
    c.execute("INSERT INTO transactions (block_idx, sender, recipient, amount) VALUES (%s, '0', %s, %s)",
              (new_index, miner_address, reward))
    
    conn.commit()
    conn.close()
    return jsonify({'message': 'Block Diterima!', 'success': True, 'reward': reward})

@app.route('/transact', methods=['POST'])
def transact():
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT idx FROM blocks ORDER BY idx DESC LIMIT 1")
    last_idx = c.fetchone()[0]
    c.execute("INSERT INTO transactions (block_idx, sender, recipient, amount) VALUES (%s, %s, %s, %s)",
              (last_idx, data['sender'], data['recipient'], data['amount']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Transaksi sukses'})

@app.route('/chain')
def chain():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT idx, timestamp, proof, previous_hash, miner FROM blocks ORDER BY idx DESC LIMIT 10")
    rows = c.fetchall()
    blocks = []
    for r in rows:
        blocks.append({
            'index': r[0], 'timestamp': datetime.fromtimestamp(r[1]).strftime('%Y-%m-%d %H:%M:%S'), 
            'proof': r[2], 'hash': r[3], 'miner': r[4]
        })
    conn.close()
    return jsonify({'chain': blocks})

@app.route('/my_transactions', methods=['POST'])
def my_transactions():
    data = request.get_json()
    wallet = data.get('address')
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT sender, recipient, amount, block_idx 
        FROM transactions 
        WHERE sender = %s OR recipient = %s
        ORDER BY id DESC LIMIT 10
    """, (wallet, wallet))
    rows = c.fetchall()
    txs = []
    for r in rows:
        tx_type = 'IN' if r[1] == wallet else 'OUT'
        if r[0] == '0': tx_type = 'MINING' 
        txs.append({'sender': r[0], 'recipient': r[1], 'amount': r[2], 'block': r[3], 'type': tx_type})
    conn.close()
    return jsonify({'transactions': txs})

if __name__ == '__main__':
    app.run(debug=True)