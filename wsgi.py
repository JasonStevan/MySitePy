import os
import sys

# Adicionar diretório atual ao caminho
path = '/home/jaxonfinxx/mysite'
if path not in sys.path:
    sys.path.append(path)

# Importar o aplicativo Flask
from app import app as application

# Criar arquivo de log
with open('/home/jaxonfinxx/mysite/wsgi_startup.log', 'a') as f:
    f.write("WSGI inicializado\n")

# Configurar logging para o aplicativo
if __name__ == '__main__':
    application.run()