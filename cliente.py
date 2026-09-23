import socket
import sys
import threading
import tty
import termios

HOST = "127.0.0.1"
PORT = 9999
RESET = "\033[0m"

nome = ""
prompt = ""
buffer = ""
lock = threading.Lock()
conexao = None
rodando = True


def redesenhar():
    """Reescreve prompt + buffer na linha atual."""
    sys.stdout.write("\r\033[K" + prompt + buffer)
    sys.stdout.flush()


def mostrar_mensagem(texto):
    """Apaga a linha, imprime a mensagem, redesenha o prompt."""
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
            if linha.startswith("COR|"):
                prompt = f"{linha[4:]}{nome}{RESET} "
                with lock:
                    redesenhar()
            elif linha:
                mostrar_mensagem(linha)


def ler_linha():
    global buffer
    buffer = ""
    with lock:
        redesenhar()

    while True:
        c = sys.stdin.read(1)

        if c == "\n" and not buffer:
            continue

        if c in ("\n", "\r"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            texto = buffer
            buffer = ""
            return texto
        elif c in ("\x7f", "\b"):
            buffer = buffer[:-1]
            with lock:
                redesenhar()
        elif c == "\x03":
            raise KeyboardInterrupt
        elif c == "\x04":
            raise EOFError
        else:
            buffer += c
            with lock:
                redesenhar()


nome = input("Seu nome: ").strip() or "Anônimo"
prompt = f"{nome} "

print()
print("Comandos:")
print("  /bot <texto>          pergunta para a IA (resposta em broadcast)")
print("  /msg <nome> <texto>   mensagem privada para outro usuário")
print("  /ajuda                mostra ajuda")
print("  /sair                 sai do chat")
print()

conexao = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conexao.connect((HOST, PORT))
conexao.send(f"ENTRAR|{nome}\n".encode("utf-8"))

fd = sys.stdin.fileno()
antigo = termios.tcgetattr(fd)
tty.setcbreak(fd)

try:
    threading.Thread(target=receber, daemon=True).start()

    while True:
        try:
            texto = ler_linha()
        except (EOFError, KeyboardInterrupt):
            break

        if not texto:
            continue

        if texto == "/sair":
            break

        if texto == "/ajuda":
            with lock:
                sys.stdout.write("\r\033[K")
                print("  /bot <texto>          pergunta para a IA (resposta em broadcast)")
                print("  /msg <nome> <texto>   mensagem privada para outro usuário")
                print("  /ajuda                mostra ajuda")
                print("  /sair                 sai do chat")
                print()
                redesenhar()
            continue

        if texto.startswith("/bot "):
            pergunta = texto[5:]
            if not pergunta:
                with lock:
                    sys.stdout.write("\r\033[K")
                    print("Uso: /bot <texto>")
                    print()
                    redesenhar()
                continue
            conexao.send(f"BOT|{pergunta}\n".encode("utf-8"))
            continue

        if texto.startswith("/msg "):
            partes = texto[5:].split(" ", 1)
            if len(partes) < 2:
                with lock:
                    sys.stdout.write("\r\033[K")
                    print("Uso: /msg <nome> <texto>")
                    print()
                    redesenhar()
                continue
            destinatario, mensagem = partes
            conexao.send(f"PRIV|{destinatario}|{mensagem}\n".encode("utf-8"))
            continue

        conexao.send(f"MSG|{texto}\n".encode("utf-8"))

finally:
    rodando = False
    termios.tcsetattr(fd, termios.TCSADRAIN, antigo)
    try:
        conexao.close()
    except Exception:
        pass
    
