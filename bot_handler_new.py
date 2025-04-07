import os
import logging
import random
import time
import sqlite3
import threading
import requests
from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import data_manager

# Configuração do log
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='/home/jaxonfinxx/mysite/bot.log'
)
logger = logging.getLogger(__name__)

# Configurações do bot
TOKEN = '7195597174:AAGYwsFXmSrj_xIyJrVvmzEU50JFaSoue0E'
GROUP_ID = -4649239012

# Estado do bot
active = True
group_open = True

def start(update: Update, context: CallbackContext) -> None:
    """Mensagem de boas-vindas ao iniciar o bot"""
    user = update.effective_user
    update.message.reply_text(f'Olá, {user.first_name}! Sou o bot de vendas e sorteios.')

def sorteios(update: Update, context: CallbackContext) -> None:
    """Lista os sorteios disponíveis"""
    if not active:
        return

    # Verificar se a mensagem é do grupo
    chat_id = update.effective_chat.id
    if chat_id != GROUP_ID and chat_id > 0:  # mensagem privada ou outro grupo
        update.message.reply_text('Este comando só funciona no grupo principal.')
        return

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'database.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Obter sorteios ativos
    raffles = conn.execute(
        "SELECT * FROM raffles WHERE status = 'pending' ORDER BY date, time"
    ).fetchall()

    conn.close()

    if not raffles:
        update.message.reply_text('Não há sorteios disponíveis no momento.')
        return

    # Criar mensagem com a lista de sorteios
    message = "🎁 *SORTEIOS DISPONÍVEIS* 🎁\n\n"

    for raffle in raffles:
        message += f"*Sorteio {raffle['id']}* - {raffle['name']}\n"
        message += f"📅 Data: {raffle['date']} às {raffle['time']}\n"
        message += f"🏆 Prêmio: {raffle['prize']}\n"
        message += f"👥 Limite: {raffle['limit_participants']} participantes\n"
        message += f"Para participar, envie: /sorteio {raffle['id']}\n\n"

    update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

def sorteio(update: Update, context: CallbackContext) -> None:
    """Permite ao usuário participar de um sorteio"""
    if not active:
        return

    # Verificar se a mensagem é do grupo
    chat_id = update.effective_chat.id
    if chat_id != GROUP_ID and chat_id > 0:  # mensagem privada ou outro grupo
        update.message.reply_text('Este comando só funciona no grupo principal.')
        return

    # Verificar se o número do sorteio foi informado
    if not context.args or not context.args[0].isdigit():
        update.message.reply_text('Uso incorreto. Exemplo: /sorteio 1')
        return

    raffle_id = int(context.args[0])
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    # Obter informações do sorteio
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'database.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    raffle = conn.execute(
        "SELECT * FROM raffles WHERE id = ? AND status = 'pending'",
        (raffle_id,)
    ).fetchone()

    if not raffle:
        update.message.reply_text('Sorteio não encontrado ou já finalizado.')
        conn.close()
        return

    # Contar participantes atuais
    count = conn.execute(
        "SELECT COUNT(*) FROM participants WHERE raffle_id = ?",
        (raffle_id,)
    ).fetchone()[0]

    # Verificar se já está cheio
    if count >= raffle['limit_participants']:
        update.message.reply_text(
            f'Desculpe, o sorteio {raffle_id} já atingiu o limite de {raffle["limit_participants"]} participantes.'
        )
        conn.close()
        return

    # Verificar se o usuário já está participando
    existing = conn.execute(
        "SELECT * FROM participants WHERE raffle_id = ? AND user_id = ?",
        (raffle_id, user_id)
    ).fetchone()

    if existing:
        update.message.reply_text(f'Você já está participando do sorteio {raffle_id}!')
        conn.close()
        return

    # Adicionar participante
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO participants (raffle_id, user_id, username) VALUES (?, ?, ?)",
        (raffle_id, user_id, username)
    )
    conn.commit()

    # Verificar se o sorteio encheu
    new_count = conn.execute(
        "SELECT COUNT(*) FROM participants WHERE raffle_id = ?",
        (raffle_id,)
    ).fetchone()[0]

    conn.close()

    # Mensagem de confirmação
    update.message.reply_text(
        f'Parabéns! Você está inscrito no sorteio {raffle_id} - {raffle["name"]}\n'
        f'Data: {raffle["date"]} às {raffle["time"]}\n'
        f'Prêmio: {raffle["prize"]}'
    )

    # Notificar se encheu
    if new_count >= raffle['limit_participants']:
        context.bot.send_message(
            chat_id=GROUP_ID,
            text=f'🔴 ATENÇÃO! O sorteio {raffle_id} atingiu {raffle["limit_participants"]} participantes e está completo!\n'
                 f'Aguardando o início do sorteio.'
        )

def start_raffle(raffle_id):
    """Inicia um sorteio (chamado pelo painel admin)"""
    if not active:
        return "Bot desativado"

    # Obter informações do sorteio
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'database.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    raffle = conn.execute("SELECT * FROM raffles WHERE id = ?", (raffle_id,)).fetchone()

    if not raffle:
        conn.close()
        return "Sorteio não encontrado"

    # Obter participantes
    participants = conn.execute(
        "SELECT * FROM participants WHERE raffle_id = ?",
        (raffle_id,)
    ).fetchall()

    if not participants:
        conn.close()
        return "Não há participantes no sorteio"

    # Atualizar status do sorteio
    conn.execute("UPDATE raffles SET status = 'running' WHERE id = ?", (raffle_id,))
    conn.commit()
    conn.close()

    # Iniciar contagem regressiva e sorteio em uma thread separada
    threading.Thread(
        target=raffle_countdown,
        args=(raffle_id, raffle['name'], raffle['winners'], raffle['prize'], participants)
    ).start()

    return "Sorteio iniciado"

def raffle_countdown(raffle_id, raffle_name, num_winners, prize, participants):
    """Processo de contagem regressiva e sorteio"""
    # Usar diretamente a API do Telegram
    api_base = f"https://api.telegram.org/bot{TOKEN}"

    # Anunciar início da contagem
    message = f'🎲 ATENÇÃO! O sorteio {raffle_id} - {raffle_name} começará em 5 segundos!'
    requests.post(
        f"{api_base}/sendMessage",
        json={
            'chat_id': GROUP_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
    )

    # Contagem regressiva
    for i in range(5, 0, -1):
        requests.post(
            f"{api_base}/sendMessage",
            json={
                'chat_id': GROUP_ID,
                'text': f'⏳ {i}...'
            }
        )
        time.sleep(1)

    # Sortear ganhadores
    winners = random.sample(participants, min(num_winners, len(participants)))
    winners_names = [w['username'] for w in winners]

    # Anunciar ganhadores
    winner_text = ', '.join(winners_names)
    result_message = (
        f'🎉 *RESULTADO DO SORTEIO {raffle_id}* 🎉\n\n'
        f'*Ganhadores:* {winner_text}\n'
        f'*Prêmio:* {prize}\n\n'
        f'Parabéns aos ganhadores! 🏆'
    )

    requests.post(
        f"{api_base}/sendMessage",
        json={
            'chat_id': GROUP_ID,
            'text': result_message,
            'parse_mode': 'Markdown'
        }
    )

    # Atualizar status no banco de dados
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'database.db')
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE raffles SET status = 'completed' WHERE id = ?", (raffle_id,))
    conn.commit()
    conn.close()

def check_links(update: Update, context: CallbackContext) -> None:
    """Remove mensagens com links não autorizados"""
    if not active or not group_open:
        return

    # Verificar se a mensagem é do grupo
    chat_id = update.effective_chat.id
    if chat_id != GROUP_ID:
        return

    message = update.message

    # Verificar se há links
    if message.entities:
        for entity in message.entities:
            if entity.type in ['url', 'text_link']:
                # Remover mensagem
                message.delete()
                # Enviar aviso
                context.bot.send_message(
                    chat_id=GROUP_ID,
                    text=f'⚠️ {message.from_user.first_name}, não é permitido enviar links no grupo quando está aberto.'
                )
                return

def send_promo_post(post_id, content):
    """Envia um post promocional ao grupo"""
    if not active:
        return "Bot desativado"

    try:
        # Enviar mensagem diretamente via API
        api_base = f"https://api.telegram.org/bot{TOKEN}"
        response = requests.post(
            f"{api_base}/sendMessage",
            json={
                'chat_id': GROUP_ID,
                'text': content,
                'parse_mode': 'Markdown'
            }
        )

        if response.status_code == 200:
            # Atualizar status no banco de dados
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'database.db')
            conn = sqlite3.connect(db_path)
            conn.execute("UPDATE posts SET status = 'sent' WHERE id = ?", (post_id,))
            conn.commit()
            conn.close()

            return "Post enviado com sucesso"
        else:
            return f"Erro ao enviar post: {response.text}"
    except Exception as e:
        return f"Erro ao enviar post: {str(e)}"

def toggle_group_status(open_status):
    """Altera o status do grupo (aberto/fechado)"""
    global group_open
    group_open = open_status

    # Usar API diretamente
    api_base = f"https://api.telegram.org/bot{TOKEN}"
    status_text = "aberto" if open_status else "fechado"

    requests.post(
        f"{api_base}/sendMessage",
        json={
            'chat_id': GROUP_ID,
            'text': f'⚠️ Atenção! O grupo agora está {status_text} para mensagens.'
        }
    )

def setup_webhook(url=None):
    """Configura o webhook para o bot"""
    if url is None:
        url = 'https://jaxonfinxx.pythonanywhere.com/webhook'

    api_url = f'https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}'

    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            logger.info(f"Webhook configurado com sucesso para {url}")
            return f"Webhook configurado com sucesso para {url}"
        else:
            error_msg = f"Erro ao configurar webhook: {response.text}"
            logger.error(error_msg)
            return error_msg
    except Exception as e:
        error_msg = f"Erro na configuração do webhook: {str(e)}"
        logger.error(error_msg)
        return error_msg

def setup_handlers():
    """Configurar os handlers para o processamento de mensagens"""
    # Criar o dispatcher
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    # Registrar handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("sorteios", sorteios))
    dispatcher.add_handler(CommandHandler("sorteio", sorteio))
    dispatcher.add_handler(MessageHandler(Filters.entity(['url', 'text_link']), check_links))

    return dispatcher

def main():
    """Iniciar o bot"""
    # Inicializar o banco de dados
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'database.db')
    if not os.path.exists(os.path.dirname(db_path)):
        os.makedirs(os.path.dirname(db_path))
    data_manager.init_db(db_path)

    # Configurar o webhook
    result = setup_webhook()
    logger.info(result)

    # Não é necessário iniciar o polling em modo webhook

if __name__ == '__main__':
    main()