import os
import sqlite3
from datetime import datetime

def get_db_connection(db_path):
    """Estabelece conexão com o banco de dados"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    """Inicializa o banco de dados"""
    # Verificar se o diretório existe
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = get_db_connection(db_path)

    # Criar tabelas se não existirem
    conn.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            schedule_time TEXT,
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS raffles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            limit_participants INTEGER NOT NULL,
            winners INTEGER NOT NULL,
            prize TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raffle_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            FOREIGN KEY (raffle_id) REFERENCES raffles (id)
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            clicks INTEGER DEFAULT 0,
            members INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()

    return True

def add_post(db_path, content, schedule_time=None):
    """Adiciona um novo post"""
    conn = get_db_connection(db_path)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn.execute(
        'INSERT INTO posts (content, schedule_time, created_at) VALUES (?, ?, ?)',
        (content, schedule_time, now)
    )

    conn.commit()
    post_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()

    return post_id

def get_posts(db_path):
    """Obtém todos os posts"""
    conn = get_db_connection(db_path)
    posts = conn.execute('SELECT * FROM posts ORDER BY created_at DESC').fetchall()
    conn.close()
    return posts

def delete_post(db_path, post_id):
    """Exclui um post"""
    conn = get_db_connection(db_path)
    conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    conn.commit()
    conn.close()
    return True

def add_raffle(db_path, name, date, time, limit, winners, prize):
    """Adiciona um novo sorteio"""
    conn = get_db_connection(db_path)

    conn.execute(
        'INSERT INTO raffles (name, date, time, limit_participants, winners, prize) VALUES (?, ?, ?, ?, ?, ?)',
        (name, date, time, limit, winners, prize)
    )

    conn.commit()
    raffle_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()

    return raffle_id

def get_raffles(db_path):
    """Obtém todos os sorteios"""
    conn = get_db_connection(db_path)
    raffles = conn.execute('SELECT * FROM raffles ORDER BY date, time').fetchall()

    # Adicionar contagem de participantes
    result = []
    for raffle in raffles:
        raffle_dict = dict(raffle)
        count = conn.execute(
            'SELECT COUNT(*) as count FROM participants WHERE raffle_id = ?',
            (raffle['id'],)
        ).fetchone()['count']

        raffle_dict['participants_count'] = count
        result.append(raffle_dict)

    conn.close()
    return result

def delete_raffle(db_path, raffle_id):
    """Exclui um sorteio"""
    conn = get_db_connection(db_path)

    # Excluir participantes primeiro (integridade referencial)
    conn.execute('DELETE FROM participants WHERE raffle_id = ?', (raffle_id,))

    # Depois excluir o sorteio
    conn.execute('DELETE FROM raffles WHERE id = ?', (raffle_id,))

    conn.commit()
    conn.close()
    return True

def get_stats(db_path):
    """Obtém estatísticas do sistema"""
    conn = get_db_connection(db_path)

    # Contar posts
    total_posts = conn.execute('SELECT COUNT(*) as count FROM posts').fetchone()['count']

    # Contar sorteios
    total_raffles = conn.execute('SELECT COUNT(*) as count FROM raffles').fetchone()['count']
    active_raffles = conn.execute('SELECT COUNT(*) as count FROM raffles WHERE status = "pending"').fetchone()['count']

    # Número aproximado de membros (exemplo)
    group_members = 120  # Valor fixo para exemplo

    conn.close()

    return {
        'total_posts': total_posts,
        'total_raffles': total_raffles,
        'group_members': group_members,
        'active_raffles': active_raffles
    }