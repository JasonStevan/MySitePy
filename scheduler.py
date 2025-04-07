import sqlite3
import time
import threading
import logging
import os
import requests
from datetime import datetime

# Configurar logging
logging.basicConfig(
    filename='/home/jaxonfinxx/mysite/scheduler.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações
DATABASE_PATH = '/home/jaxonfinxx/mysite/instance/database.db'
BOT_TOKEN = '7195597174:AAGYwsFXmSrj_xIyJrVvmzEU50JFaSoue0E'
GROUP_ID = -1002541164460
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
UPLOAD_FOLDER = '/home/jaxonfinxx/mysite/static/uploads'

# Intervalo padrão (em segundos)
DEFAULT_INTERVAL = 600  # 10 minutos

class PostScheduler:
    def __init__(self):
        self.running = False
        self.thread = None
        self.interval = DEFAULT_INTERVAL
        logger.info("Inicializando scheduler de posts")

    def get_db_connection(self):
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def get_settings(self):
        try:
            conn = self.get_db_connection()
            # Obter intervalo das configurações
            setting = conn.execute('SELECT value FROM settings WHERE key = ?', ('post_interval',)).fetchone()
            if setting:
                self.interval = int(setting['value'])

            # Obter status do scheduler
            status = conn.execute('SELECT value FROM settings WHERE key = ?', ('scheduler_active',)).fetchone()
            self.running = status and status['value'] == 'true'

            conn.close()
            logger.info(f"Configurações carregadas: intervalo={self.interval}s, ativo={self.running}")
        except Exception as e:
            logger.error(f"Erro ao carregar configurações: {str(e)}")

    def get_next_post(self):
        try:
            conn = self.get_db_connection()
            # Obter o próximo post pendente mais antigo
            post = conn.execute('''
                SELECT * FROM posts
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
            ''').fetchone()
            conn.close()

            if post:
                return dict(post)
            return None
        except Exception as e:
            logger.error(f"Erro ao obter próximo post: {str(e)}")
            return None

    def mark_post_as_sent(self, post_id):
        try:
            conn = self.get_db_connection()
            conn.execute("UPDATE posts SET status = 'sent' WHERE id = ?", (post_id,))
            conn.commit()
            conn.close()
            logger.info(f"Post {post_id} marcado como enviado")
        except Exception as e:
            logger.error(f"Erro ao marcar post como enviado: {str(e)}")

    def send_post_to_group(self, post):
        try:
            if post['image_path']:
                # Enviar post com imagem
                image_path = os.path.join(UPLOAD_FOLDER, os.path.basename(post['image_path']))

                with open(image_path, 'rb') as photo:
                    files = {'photo': photo}
                    data = {
                        'chat_id': GROUP_ID,
                        'caption': post['content'],
                        'parse_mode': 'Markdown'
                    }

                    response = requests.post(f"{API_BASE}/sendPhoto", data=data, files=files)
                    logger.info(f"Imagem enviada: {response.status_code} - {response.text}")
                    return response.json()
            else:
                # Enviar post apenas com texto
                data = {
                    'chat_id': GROUP_ID,
                    'text': post['content'],
                    'parse_mode': 'Markdown'
                }

                response = requests.post(f"{API_BASE}/sendMessage", json=data)
                logger.info(f"Mensagem enviada: {response.status_code} - {response.text}")
                return response.json()
        except Exception as e:
            logger.error(f"Erro ao enviar post: {str(e)}")
            return {'ok': False, 'description': str(e)}

    def create_settings_if_not_exists(self):
        try:
            conn = self.get_db_connection()

            # Verificar se tabela settings existe
            table_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'").fetchone()
            if not table_check:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key TEXT NOT NULL UNIQUE,
                        value TEXT NOT NULL
                    )
                ''')

            # Inserir configurações padrão se não existirem
            settings = [
                ('post_interval', str(DEFAULT_INTERVAL)),
                ('scheduler_active', 'true')
            ]

            for key, value in settings:
                conn.execute(
                    'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                    (key, value)
                )

            conn.commit()
            conn.close()
            logger.info("Configurações padrão criadas se necessário")
        except Exception as e:
            logger.error(f"Erro ao criar configurações: {str(e)}")

    def scheduler_loop(self):
        logger.info("Iniciando loop do scheduler")
        last_run = 0

        while self.running:
            try:
                # Recarregar configurações a cada ciclo
                self.get_settings()

                # Verificar se o scheduler está ativo
                if not self.running:
                    logger.info("Scheduler desativado nas configurações, encerrando loop")
                    break

                current_time = time.time()

                # Verificar se é hora de enviar um post
                if current_time - last_run >= self.interval:
                    logger.info("Verificando posts pendentes")
                    post = self.get_next_post()

                    if post:
                        logger.info(f"Enviando post {post['id']}")
                        result = self.send_post_to_group(post)

                        if result.get('ok'):
                            self.mark_post_as_sent(post['id'])
                            logger.info(f"Post {post['id']} enviado com sucesso")
                        else:
                            logger.error(f"Erro ao enviar post {post['id']}: {result.get('description')}")
                    else:
                        logger.info("Nenhum post pendente encontrado")

                    last_run = current_time

                # Dormir por um tempo para não sobrecarregar a CPU
                time.sleep(min(10, self.interval / 2))
            except Exception as e:
                logger.error(f"Erro no loop do scheduler: {str(e)}")
                time.sleep(30)  # Em caso de erro, esperar 30 segundos

    def start(self):
        self.create_settings_if_not_exists()
        self.get_settings()

        if not self.running or self.thread and self.thread.is_alive():
            return

        self.running = True
        self.thread = threading.Thread(target=self.scheduler_loop, daemon=True)
        self.thread.start()
        logger.info("Scheduler iniciado")

    def stop(self):
        self.running = False
        logger.info("Scheduler parado")

        if self.thread:
            self.thread.join(timeout=5)

# Instância global do scheduler
scheduler = PostScheduler()

# Iniciar o scheduler se for executado diretamente
if __name__ == "__main__":
    try:
        scheduler.start()
        # Manter o script executando
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.stop()
        logger.info("Scheduler encerrado por interrupção do teclado")