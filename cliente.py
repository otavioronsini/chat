import socket
import sys
import threading
import tty
import termios
import os

HOST = "127.0.0.1"
PORT = 9999
RESET = "\033[0m"

nome = ""
prompt = ""
buffer = ""
lock = threading.Lock()
conexao = None
rodando = True

def limpar_tela():
    os.system('cls' if os.name == 'nt' else 'clear')

def redesenhar():
    sys.stdout.write("\r\033[K" + prompt + buffer)
    sys.stdout.flush()

def mostrar_mensagem(texto):
    with lock:
        sys.stdout.write("\r\033[K")
        sys.stdout.write(texto + "\n")
        sys.stdout.flush()
        redesenhar()

def receber():
    global prompt
    parcial = ""
    while rodando:
        try:
            dados = conexao.recv(4096).decode("utf-8")
        except Exception:
            break
        if not dados:
            break
        parcial += dados
        while "\n" in parcial:
            linha, parcial = parcial.split("\n", 1)
            
            if linha.startswith("CMD|CLEAR"):
                with lock:
                    limpar_tela()
                    redesenhar()
            elif linha.startswith("COR|"):
                prompt = f"{linha[4:]}{nome}{RESET} "
                with lock:
                    redesenhar()
            elif linha:
                mostrar_mensagem(linha)

def ler_linha():
    global buffer
    buffer = ""
    with lock: redesenhar()

    while True:
        c = sys.stdin.read(1)
        if c == "\n" and not buffer: continue
        if c in ("\n", "\r"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            texto = buffer
            buffer = ""
            return texto
        elif c in ("\x7f", "\b"):
            buffer = buffer[:-1]
            with lock: redesenhar()
        elif c == "\x03": raise KeyboardInterrupt
        elif c == "\x04": raise EOFError
        else:
            buffer += c
            with lock: redesenhar()

nome = input("Seu nome: ").strip() or "Anônimo"
prompt = f"{nome} "

limpar_tela()
print("Comandos:")
print("  /tema [assunto], [dificuldade], [qtd]  Inicia o jogo (exclusivo para o host)")
print("  /bot <texto>                           Pergunta para a IA no chat")
print("  /msg <nome> <texto>                    Mensagem privada")
print("  /sair                                  Sai do chat\n")

conexao = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conexao.connect((HOST, PORT))
conexao.send(f"ENTRAR|{nome}\n".encode("utf-8"))

fd = sys.stdin.fileno()
antigo = termios.tcgetattr(fd)
tty.setcbreak(fd)

try:
    threading.Thread(target=receber, daemon=True).start()
    while True:
        try: texto = ler_linha()
        except (EOFError, KeyboardInterrupt): break

        if not texto: continue
        if texto == "/sair": break

        if texto.startswith("/bot "):
            conexao.send(f"BOT|{texto[5:]}\n".encode("utf-8"))
        elif texto.startswith("/msg "):
            partes = texto[5:].split(" ", 1)
            if len(partes) >= 2:
                conexao.send(f"PRIV|{partes[0]}|{partes[1]}\n".encode("utf-8"))
        else:
            conexao.send(f"MSG|{texto}\n".encode("utf-8"))
finally:
    rodando = False
    termios.tcsetattr(fd, termios.TCSADRAIN, antigo)
    try: conexao.close()
    except: pass