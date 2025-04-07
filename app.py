import os
import sqlite3
import logging
import requests
import time
import threading
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import random

# Inicialização do app Flask
app = Flask(__name__)
app.secret_key = 'zyone_bot_secret_key'

# Caminho absoluto para o diretório onde o script está sendo executado
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configurações de upload
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Limite de 5MB para uploads

# Garantir que a pasta de uploads exista
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configurações do bot
BOT_TOKEN = '7195597174:AAGYwsFXmSrj_xIyJrVvmzEU50JFaSoue0E'
GROUP_ID = -1002541164460
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Logger
logging.basicConfig(
    filename=os.path.join(BASE_DIR, 'app.log'),
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuração do scheduler para posts automáticos
SCHEDULER_ACTIVE = False
POST_INTERVAL = 5  # minutos
scheduler_thread = None
stop_scheduler = threading.Event()

# Funções de banco de dados
def get_db_connection():
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'database.db'))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()

    # Criar tabelas se não existirem
    conn.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            image_path TEXT,
            external_link TEXT,
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS raffles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            command TEXT NOT NULL,
            end_date TEXT,
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raffle_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            joined_at TEXT NOT NULL,
            FOREIGN KEY (raffle_id) REFERENCES raffles (id)
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL
        )
    ''')

    # Inserir configurações padrão
    settings = [
        ('welcome_message', 'Olá {name}! Bem-vindo(a) ao grupo da Zyone Cosméticos. 💄✨'),
        ('welcome_active', 'on'),
        ('link_filter', 'on'),
        ('post_interval', '5'),
        ('scheduler_active', 'off')
    ]

    for key, value in settings:
        conn.execute(
            'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
            (key, value)
        )

    conn.commit()
    conn.close()
    logger.info("Banco de dados inicializado com sucesso")

# Funções de validação e segurança
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_logged_in():
    return session.get('logged_in', False)

def login_required(f):
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Funções de upload
def save_uploaded_image(file):
    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            # Adicionar timestamp para evitar nomes duplicados
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"{timestamp}_{filename}"

            # Caminho absoluto para salvar o arquivo
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Retornar caminho relativo para o banco de dados
            return f"static/uploads/{filename}"
        except Exception as e:
            logger.error(f"Erro ao salvar imagem: {str(e)}")
            return None
    return None

# Funções do banco de dados
def get_posts():
    conn = get_db_connection()
    posts = conn.execute('SELECT * FROM posts ORDER BY created_at DESC').fetchall()
    conn.close()
    return [dict(post) for post in posts]

def get_post(post_id):
    conn = get_db_connection()
    post = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    conn.close()
    return dict(post) if post else None

def add_post(content, image_path=None, external_link=None):
    try:
        conn = get_db_connection()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn.execute(
            'INSERT INTO posts (content, image_path, external_link, created_at) VALUES (?, ?, ?, ?)',
            (content, image_path, external_link, now)
        )

        conn.commit()
        post_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.close()

        logger.info(f"Post adicionado com sucesso, ID: {post_id}")
        return post_id
    except Exception as e:
        logger.error(f"Erro ao adicionar post: {str(e)}")
        raise e

def update_post_status(post_id, status):
    conn = get_db_connection()
    conn.execute('UPDATE posts SET status = ? WHERE id = ?', (status, post_id))
    conn.commit()
    conn.close()

def delete_post(post_id):
    try:
        conn = get_db_connection()

        # Obter caminho da imagem para excluir arquivo
        post = conn.execute('SELECT image_path FROM posts WHERE id = ?', (post_id,)).fetchone()

        conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
        conn.commit()
        conn.close()

        # Excluir imagem se existir
        if post and post['image_path']:
            image_path = os.path.join(BASE_DIR, post['image_path'])
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.info(f"Imagem excluída: {image_path}")
                except Exception as e:
                    logger.error(f"Erro ao excluir imagem: {str(e)}")
    except Exception as e:
        logger.error(f"Erro ao excluir post: {str(e)}")
        raise e

def count_posts(status=None):
    conn = get_db_connection()
    if status:
        count = conn.execute('SELECT COUNT(*) as count FROM posts WHERE status = ?', (status,)).fetchone()['count']
    else:
        count = conn.execute('SELECT COUNT(*) as count FROM posts').fetchone()['count']
    conn.close()
    return count

def get_setting(key, default=None):
    conn = get_db_connection()
    setting = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return setting['value'] if setting else default

def update_setting(key, value):
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def get_raffles():
    conn = get_db_connection()
    raffles = conn.execute('SELECT * FROM raffles ORDER BY created_at DESC').fetchall()
    conn.close()
    return [dict(raffle) for raffle in raffles]

def get_raffle(raffle_id):
    conn = get_db_connection()
    raffle = conn.execute('SELECT * FROM raffles WHERE id = ?', (raffle_id,)).fetchone()
    conn.close()
    return dict(raffle) if raffle else None

def add_raffle(name, description, command, end_date=None):
    conn = get_db_connection()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn.execute(
        'INSERT INTO raffles (name, description, command, end_date, created_at) VALUES (?, ?, ?, ?, ?)',
        (name, description, command, end_date, now)
    )

    conn.commit()
    raffle_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()

    return raffle_id

def delete_raffle(raffle_id):
    conn = get_db_connection()

    # Excluir participantes primeiro
    conn.execute('DELETE FROM participants WHERE raffle_id = ?', (raffle_id,))

    # Excluir o sorteio
    conn.execute('DELETE FROM raffles WHERE id = ?', (raffle_id,))

    conn.commit()
    conn.close()

def get_raffle_participants(raffle_id):
    conn = get_db_connection()
    participants = conn.execute('SELECT * FROM participants WHERE raffle_id = ? ORDER BY joined_at', (raffle_id,)).fetchall()
    conn.close()
    return [dict(p) for p in participants]

def count_raffle_participants(raffle_id):
    conn = get_db_connection()
    count = conn.execute('SELECT COUNT(*) as count FROM participants WHERE raffle_id = ?', (raffle_id,)).fetchone()['count']
    conn.close()
    return count

def draw_winners(raffle_id, num_winners=1):
    conn = get_db_connection()
    participants = conn.execute('SELECT * FROM participants WHERE raffle_id = ?', (raffle_id,)).fetchall()
    participants = [dict(p) for p in participants]

    if len(participants) < num_winners:
        conn.close()
        return []

    # Escolher vencedores aleatoriamente
    winners = random.sample(participants, num_winners)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Atualizar status do sorteio
    conn.execute('UPDATE raffles SET status = ? WHERE id = ?', ('completed', raffle_id))

    conn.commit()
    conn.close()

    return winners

# Funções do bot Telegram
def send_telegram_message(text, parse_mode=None):
    data = {
        'chat_id': GROUP_ID,
        'text': text
    }

    if parse_mode:
        data['parse_mode'] = parse_mode

    try:
        response = requests.post(f"{API_BASE}/sendMessage", json=data)
        logger.info(f"Mensagem enviada para {GROUP_ID}: {response.status_code}")
        return response.json()
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {str(e)}")
        return {'ok': False, 'description': str(e)}

def send_telegram_photo(photo_path, caption=None, parse_mode=None):
    try:
        # Caminho absoluto para a imagem
        abs_photo_path = os.path.join(BASE_DIR, photo_path)

        # Verificar se é um caminho de arquivo válido
        if not os.path.exists(abs_photo_path):
            logger.error(f"Arquivo não encontrado: {abs_photo_path}")
            return {'ok': False, 'description': 'Arquivo não encontrado'}

        # Abrir e ler o arquivo de imagem
        with open(abs_photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': GROUP_ID}

            if caption:
                data['caption'] = caption

            if parse_mode:
                data['parse_mode'] = parse_mode

            response = requests.post(f"{API_BASE}/sendPhoto", data=data, files=files)
            logger.info(f"Foto enviada para {GROUP_ID}: {response.status_code}")
            return response.json()
    except Exception as e:
        logger.error(f"Erro ao enviar foto: {str(e)}")
        return {'ok': False, 'description': str(e)}

# Funções do scheduler
def scheduler_function():
    global stop_scheduler

    while not stop_scheduler.is_set():
        try:
            # Verificar se há posts pendentes
            posts = get_posts()
            pending_posts = [p for p in posts if p['status'] == 'pending']

            if pending_posts:
                # Pegar o post mais antigo
                post = pending_posts[-1]  # O último da lista (mais antigo na ordem desc)

                # Enviar para o Telegram
                if post['image_path']:
                    caption = post['content']
                    if post['external_link']:
                        caption += f"\n\n{post['external_link']}"

                    result = send_telegram_photo(post['image_path'], caption=caption, parse_mode='Markdown')
                else:
                    message = post['content']
                    if post['external_link']:
                        message += f"\n\n{post['external_link']}"

                    result = send_telegram_message(message, parse_mode='Markdown')

                if result.get('ok', False):
                    # Atualizar status do post para enviado
                    update_post_status(post['id'], 'sent')
                    logger.info(f"Post {post['id']} enviado com sucesso pelo scheduler")
                else:
                    logger.error(f"Erro ao enviar post {post['id']}: {result.get('description')}")

            # Esperar o intervalo configurado
            interval = int(get_setting('post_interval', '5'))
            for _ in range(interval * 60):  # Converter minutos para segundos
                if stop_scheduler.is_set():
                    break
                time.sleep(1)

        except Exception as e:
            logger.error(f"Erro no scheduler: {str(e)}")
            time.sleep(60)  # Em caso de erro, esperar 1 minuto antes de tentar novamente

def start_scheduler():
    global SCHEDULER_ACTIVE, scheduler_thread, stop_scheduler

    if not SCHEDULER_ACTIVE:
        SCHEDULER_ACTIVE = True
        stop_scheduler.clear()
        scheduler_thread = threading.Thread(target=scheduler_function)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        logger.info("Scheduler iniciado")
        update_setting('scheduler_active', 'on')

def stop_scheduler():
    global SCHEDULER_ACTIVE, stop_scheduler

    if SCHEDULER_ACTIVE:
        SCHEDULER_ACTIVE = False
        stop_scheduler.set()
        logger.info("Scheduler parado")
        update_setting('scheduler_active', 'off')

def is_scheduler_active():
    return SCHEDULER_ACTIVE

def set_post_interval(minutes):
    if minutes < 1:
        minutes = 1
    update_setting('post_interval', str(minutes))
    return minutes

def get_post_interval():
    return int(get_setting('post_interval', '5'))

# Rotas da aplicação
@app.route('/')
def index():
    if not is_logged_in():
        return redirect(url_for('login'))
    return redirect(url_for('posts'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == 'admin@exemplo.com' and password == 'senha123':
            session['logged_in'] = True
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('posts'))
        else:
            flash('Credenciais inválidas. Tente novamente.', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

@app.route('/posts', methods=['GET', 'POST'])
@login_required
def posts():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            try:
                content = request.form.get('content')
                external_link = request.form.get('external_link', '').strip()

                # Processar upload de imagem
                image_path = None
                if 'image' in request.files and request.files['image'].filename:
                    image_path = save_uploaded_image(request.files['image'])

                # Adicionar post
                if content:
                    add_post(content, image_path, external_link)
                    flash('Post adicionado com sucesso!', 'success')
                else:
                    flash('O conteúdo do post não pode estar vazio.', 'danger')
            except Exception as e:
                logger.error(f"Erro ao adicionar post: {str(e)}")
                flash(f'Erro ao adicionar post: {str(e)}', 'danger')

        elif action == 'delete':
            post_id = request.form.get('post_id')
            try:
                delete_post(post_id)
                flash('Post excluído com sucesso!', 'success')
            except Exception as e:
                flash(f'Erro ao excluir post: {str(e)}', 'danger')

        elif action == 'send':
            post_id = request.form.get('post_id')
            post = get_post(post_id)

            if post:
                try:
                    # Enviar o post para o Telegram
                    if post['image_path']:
                        caption = post['content']
                        if post['external_link']:
                            caption += f"\n\n{post['external_link']}"

                        result = send_telegram_photo(post['image_path'], caption=caption, parse_mode='Markdown')
                    else:
                        message = post['content']
                        if post['external_link']:
                            message += f"\n\n{post['external_link']}"

                        result = send_telegram_message(message, parse_mode='Markdown')

                    if result.get('ok', False):
                        update_post_status(post_id, 'sent')
                        flash('Post enviado com sucesso!', 'success')
                    else:
                        flash(f'Erro ao enviar post: {result.get("description")}', 'danger')
                except Exception as e:
                    flash(f'Erro ao enviar post: {str(e)}', 'danger')
            else:
                flash('Post não encontrado.', 'danger')

        elif action == 'update_interval':
            interval = request.form.get('post_interval')
            try:
                interval = int(interval)
                set_post_interval(interval)
                flash(f'Intervalo atualizado para {interval} minutos.', 'success')
            except ValueError:
                flash('O intervalo deve ser um número inteiro.', 'danger')

        elif action == 'toggle_scheduler':
            if is_scheduler_active():
                stop_scheduler()
                flash('Publicação automática desativada.', 'info')
            else:
                start_scheduler()
                flash('Publicação automática ativada.', 'success')

    posts_list = get_posts()

    stats = {
        'post_interval': get_post_interval(),
        'scheduler_active': is_scheduler_active(),
        'pending_posts': count_posts(status='pending'),
        'total_posts': count_posts()
    }

    return render_template('promo.html', posts=posts_list, stats=stats)

@app.route('/raffles', methods=['GET', 'POST'])
@login_required
def raffles():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            name = request.form.get('name')
            description = request.form.get('description', '')
            command = request.form.get('command')
            end_date = request.form.get('end_date')

            if name and command:
                try:
                    add_raffle(name, description, command, end_date)
                    flash('Sorteio adicionado com sucesso!', 'success')
                except Exception as e:
                    flash(f'Erro ao adicionar sorteio: {str(e)}', 'danger')
            else:
                flash('Nome e comando são obrigatórios.', 'danger')

        elif action == 'delete':
            raffle_id = request.form.get('raffle_id')
            try:
                delete_raffle(raffle_id)
                flash('Sorteio excluído com sucesso!', 'success')
            except Exception as e:
                flash(f'Erro ao excluir sorteio: {str(e)}', 'danger')

        elif action == 'draw':
            raffle_id = request.form.get('raffle_id')
            num_winners = int(request.form.get('num_winners', 1))

            try:
                winners = draw_winners(raffle_id, num_winners)

                if winners:
                    winners_text = "\n".join([f"- {w['first_name']} (@{w['username']})" for w in winners if w['username']])
                    raffle = get_raffle(raffle_id)

                    message = f"🎉 *RESULTADO DO SORTEIO* 🎉\n\n*{raffle['name']}*\n\n"
                    message += f"Participantes: *{count_raffle_participants(raffle_id)}*\n"
                    message += f"Vencedores:\n{winners_text}\n\n"
                    message += "Parabéns aos ganhadores! 🏆"

                    result = send_telegram_message(message, parse_mode='Markdown')

                    if result.get('ok', False):
                        flash('Sorteio realizado com sucesso! Os vencedores foram anunciados no grupo.', 'success')
                    else:
                        flash(f'Erro ao enviar resultados: {result.get("description")}', 'danger')
                else:
                    flash('Não foi possível realizar o sorteio. Verifique se há participantes suficientes.', 'danger')
            except Exception as e:
                flash(f'Erro ao realizar sorteio: {str(e)}', 'danger')

    raffles_list = get_raffles()

    # Adicionar contagem de participantes para cada sorteio
    for raffle in raffles_list:
        raffle['participant_count'] = count_raffle_participants(raffle['id'])

    return render_template('raffles.html', raffles=raffles_list)

@app.route('/raffle/<int:raffle_id>/participants')
@login_required
def raffle_participants(raffle_id):
    raffle = get_raffle(raffle_id)

    if not raffle:
        flash('Sorteio não encontrado.', 'danger')
        return redirect(url_for('raffles'))

    participants = get_raffle_participants(raffle_id)

    return render_template('participants.html', raffle=raffle, participants=participants)

@app.route('/bot_config', methods=['GET', 'POST'])
@login_required
def bot_config():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_welcome':
            welcome_message = request.form.get('welcome_message')
            update_setting('welcome_message', welcome_message)
            flash('Mensagem de boas-vindas atualizada com sucesso!', 'success')

        elif action == 'toggle_link_filter':
            current_status = get_setting('link_filter', 'off')
            new_status = 'off' if current_status == 'on' else 'on'
            update_setting('link_filter', new_status)
            flash(f'Filtro de links {new_status=="on" and "ativado" or "desativado"} com sucesso!', 'success')

        elif action == 'toggle_welcome':
            current_status = get_setting('welcome_active', 'off')
            new_status = 'off' if current_status == 'on' else 'on'
            update_setting('welcome_active', new_status)
            flash(f'Mensagem de boas-vindas {new_status=="on" and "ativada" or "desativada"} com sucesso!', 'success')

    settings = {
        'welcome_message': get_setting('welcome_message', 'Bem-vindo(a) ao grupo!'),
        'link_filter': get_setting('link_filter', 'off'),
        'welcome_active': get_setting('welcome_active', 'off')
    }

    return render_template('bot_config.html', settings=settings)

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()

    if not update:
        return "OK"

    try:
        logger.info(f"Webhook received: {update}")

        # Processar novos membros
        if 'message' in update and 'new_chat_members' in update['message']:
            chat_id = update['message']['chat']['id']

            # Verificar se é o nosso grupo
            if str(chat_id) == str(GROUP_ID):
                for new_member in update['message']['new_chat_members']:
                    # Enviar mensagem de boas-vindas se estiver ativo
                    if get_setting('welcome_active', 'off') == 'on':
                        first_name = new_member.get('first_name', 'Novo membro')
                        welcome_message = get_setting('welcome_message', 'Bem-vindo(a) ao grupo!')
                        welcome_message = welcome_message.replace('{name}', first_name)

                        send_telegram_message(welcome_message)

        # Processar mensagens para comandos de sorteio e filtro de links
        if 'message' in update and 'text' in update['message']:
            message = update['message']
            chat_id = message['chat']['id']

            # Verificar se é o nosso grupo
            if str(chat_id) == str(GROUP_ID):
                text = message['text']

                # Filtrar links se o filtro estiver ativo
                if get_setting('link_filter', 'off') == 'on':
                    if any(link in text.lower() for link in ['http', 't.me/', '.com', '.net', '.org']):
                        # Tentar deletar a mensagem
                        try:
                            requests.post(
                                f"{API_BASE}/deleteMessage",
                                json={'chat_id': chat_id, 'message_id': message['message_id']}
                            )
                            logger.info(f"Mensagem com link deletada: {message['message_id']}")
                        except Exception as e:
                            logger.error(f"Erro ao deletar mensagem com link: {str(e)}")

                # Verificar comandos de sorteio
                if text.startswith('/'):
                    command = text.split(' ')[0][1:]  # Remover a barra e pegar apenas o comando
                    conn = get_db_connection()
                    raffle = conn.execute('SELECT * FROM raffles WHERE command = ? AND status = "pending"', (command,)).fetchone()
                    conn.close()

                    if raffle:
                        # Adicionar participante ao sorteio
                        user_id = message['from']['id']
                        first_name = message['from'].get('first_name', '')
                        last_name = message['from'].get('last_name', '')
                        username = message['from'].get('username', '')

                        conn = get_db_connection()
                        # Verificar se já está participando
                        existing = conn.execute(
                            'SELECT id FROM participants WHERE raffle_id = ? AND user_id = ?',
                            (raffle['id'], user_id)
                        ).fetchone()

                        if not existing:
                            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            conn.execute(
                                'INSERT INTO participants (raffle_id, user_id, first_name, last_name, username, joined_at) VALUES (?, ?, ?, ?, ?, ?)',
                                (raffle['id'], user_id, first_name, last_name, username, now)
                            )
                            conn.commit()

                            # Confirmar participação
                            send_telegram_message(f"✅ {first_name}, você está participando do sorteio *{raffle['name']}*!", parse_mode='Markdown')
                        else:
                            # Já está participando
                            send_telegram_message(f"ℹ️ {first_name}, você já está participando do sorteio *{raffle['name']}*!", parse_mode='Markdown')

                        conn.close()
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {str(e)}")

    return "OK"

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

# Inicialização
with app.app_context():
    # Inicializar banco de dados
    init_db()

    # Verificar se o scheduler deve ser iniciado
    if get_setting('scheduler_active', 'on') == 'on':
        start_scheduler()

if __name__ == '__main__':
    # Configurar webhook
    webhook_url = 'https://jaxonfinxx.pythonanywhere.com/webhook'
    try:
        response = requests.get(f"{API_BASE}/setWebhook?url={webhook_url}")
        logger.info(f"Configuração de webhook: {response.json()}")
    except Exception as e:
        logger.error(f"Erro ao configurar webhook: {str(e)}")

    app.run(debug=True)