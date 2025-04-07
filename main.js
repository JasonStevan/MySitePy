// Funções principais do painel administrativo

document.addEventListener('DOMContentLoaded', function() {
    // Inicialização
    console.log('Painel administrativo carregado');

    // Configurar tooltips
    setupTooltips();

    // Configurar confirmações
    setupConfirmations();

    // Animar estatísticas
    animateStats();
});

// Tooltips para botões
function setupTooltips() {
    const tooltipElements = document.querySelectorAll('[data-tooltip]');

    tooltipElements.forEach(element => {
        element.setAttribute('title', element.getAttribute('data-tooltip'));
    });
}

// Confirmações para ações importantes
function setupConfirmations() {
    const confirmBtns = document.querySelectorAll('.btn-confirm');

    confirmBtns.forEach(btn => {
        btn.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm') || 'Tem certeza que deseja continuar?';

            if (!confirm(message)) {
                e.preventDefault();
                return false;
            }
        });
    });
}

// Animação para os números de estatísticas
function animateStats() {
    const statElements = document.querySelectorAll('.stat-value');

    statElements.forEach(element => {
        const target = parseInt(element.textContent);
        let count = 0;
        const duration = 1000; // 1 segundo
        const increment = target / (duration / 30); // 30fps

        element.textContent = '0';

        const timer = setInterval(() => {
            count += increment;
            if (count >= target) {
                clearInterval(timer);
                element.textContent = target;
            } else {
                element.textContent = Math.floor(count);
            }
        }, 30);
    });
}

// Funções para manipulação de conteúdo
function toggleGroupStatus(open) {
    // Enviar solicitação para alternar status do grupo
    fetch('/api/toggle_group', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ open: open })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Status do grupo alterado com sucesso', 'success');
            // Recarregar página após um curto delay
            setTimeout(() => location.reload(), 1500);
        } else {
            showNotification('Erro ao alterar status do grupo', 'error');
        }
    })
    .catch(error => {
        showNotification('Erro de comunicação com o servidor', 'error');
        console.error('Erro:', error);
    });
}

// Função para exibir notificações na interface
function showNotification(message, type = 'info') {
    const notificationArea = document.getElementById('notification-area');

    if (!notificationArea) {
        // Criar área de notificação se não existir
        const newArea = document.createElement('div');
        newArea.id = 'notification-area';
        newArea.style.position = 'fixed';
        newArea.style.top = '20px';
        newArea.style.right = '20px';
        newArea.style.zIndex = '9999';
        document.body.appendChild(newArea);
    }

    // Criar elemento de notificação
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = message;

    // Estilizar notificação
    notification.style.backgroundColor = type === 'success' ? '#4CAF50' :
                                         type === 'error' ? '#f44336' : '#2196F3';
    notification.style.color = 'white';
    notification.style.padding = '12px 20px';
    notification.style.marginBottom = '10px';
    notification.style.borderRadius = '4px';
    notification.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
    notification.style.transition = 'all 0.3s ease';
    notification.style.opacity = '0';

    // Adicionar ao DOM
    document.getElementById('notification-area').appendChild(notification);

    // Animar entrada
    setTimeout(() => {
        notification.style.opacity = '1';
    }, 10);

    // Remover após alguns segundos
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, 5000);
}

// Manipulação de sorteios
function startRaffle(raffleId) {
    if (confirm('Tem certeza que deseja iniciar este sorteio?')) {
        document.getElementById('start-raffle-form-' + raffleId).submit();
    }
}

// Manipulação de posts
function sendPost(postId) {
    if (confirm('Tem certeza que deseja enviar este post agora?')) {
        document.getElementById('send-post-form-' + postId).submit();
    }
}

function deleteItem(formId, itemType) {
    if (confirm(`Tem certeza que deseja excluir este ${itemType}?`)) {
        document.getElementById(formId).submit();
    }
}