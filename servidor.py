import socket
import threading
import os
from groq import Groq

# A chave vem da variável de ambiente GROQ_API_KEY.
cliente_ia = Groq(api_key=os.environ["GROQ_API_KEY"])

MODELO = "openai/gpt-oss-120b"

clientes = []

cores = [
    "\033[91m", "\033[92m", "\033[93m",
    "\033[94m", "\033[95m", "\033[96m",
]
RESET = "\033[0m"
COR_BOT = "\033[97m"


def perguntar_para_ia(pergunta):
    try:
        completion = cliente_ia.chat.completions.create(
            model=MODELO,
            messages=[
                {
                    "role": "system",
                    "content": "Você é o Bot, um assistente num chat. "
                               "Responda curto, engraçado e sarcástico em português do brasil.",
                },
                {"role": "user", "content": pergunta},
            ],
            temperature=1,
            max_completion_tokens=2048,
            top_p=1,
            reasoning_effort="medium",
            stream=False,
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"(erro ao consultar a IA: {type(e).__name__}: {e})"


# ─────────────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────────────
def log(evento, detalhe=""):
    print(f"{evento:8} {detalhe}".rstrip())


def enviar_para(cliente, mensagem):
    try:
        cliente["socket"].send((mensagem + "\n").encode("utf-8"))
    except Exception:
        pass


def enviar_para_todos(mensagem, exceto=None):
    for c in clientes:
        if c is not exceto:
            enviar_para(c, mensagem)


# ─────────────────────────────────────────────────────
# BOT
# ─────────────────────────────────────────────────────
def responder_bot(pergunta):
    resposta = perguntar_para_ia(pergunta)
    formatado = f"{COR_BOT}Bot{RESET} {resposta}"
    enviar_para_todos(formatado)
    log("BOT", f"resposta enviada (broadcast): {resposta[:60]}")

def atender(cliente):
    while True:
        try:
            dados = cliente["socket"].recv(4096).decode("utf-8")
        except Exception:
            break
        if not dados:
            break

        for linha in dados.split("\n"):
            if not linha:
                continue

            log("RECV", f"{cliente['nome']}: {linha[:60]}")

            # mensagem publica
            if linha.startswith("MSG|"):
                texto = linha[4:]
                if not texto:
                    continue
                formatado = f"{cliente['cor']}{cliente['nome']}{RESET} {texto}"
                enviar_para_todos(formatado, exceto=cliente)
                log("SEND", f"{cliente['nome']} -> todos")

            # pergunta pra ia
            elif linha.startswith("BOT|"):
                pergunta = linha[4:]
                if not pergunta:
                    continue
                aviso = (f"{cliente['cor']}{cliente['nome']}{RESET} "
                         f"-> Bot: {pergunta}")
                enviar_para_todos(aviso, exceto=cliente)
                threading.Thread(
                    target=responder_bot,
                    args=(pergunta,),
                    daemon=True,
                ).start()
                log("BOT", f"{cliente['nome']} perguntou: {pergunta[:40]}")

            # mensagem privada
            elif linha.startswith("PRIV|"):
                partes = linha[5:].split("|", 1)
                if len(partes) < 2:
                    continue
                destinatario, texto = partes

                achou = False
                for c in clientes:
                    if c["nome"] == destinatario:
                        enviar_para(c,
                                    f"{cliente['cor']}{cliente['nome']}{RESET} "
                                    f"(priv) {texto}")
                        achou = True
                        log("SEND", f"{cliente['nome']} -> {destinatario} (priv)")
                        break
                if not achou:
                    enviar_para(cliente,
                                f"Usuário '{destinatario}' não encontrado.")

    log("SAIR", cliente["nome"])
    enviar_para_todos(f"{cliente['cor']}{cliente['nome']}{RESET} saiu do chat")
    if cliente in clientes:
        clientes.remove(cliente)
    try:
        cliente["socket"].close()
    except Exception:
        pass


servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
servidor.bind(("0.0.0.0", 9999))
servidor.listen()

print("Servidor de chat rodando na porta 9999...\n")

while True:
    conexao, endereco = servidor.accept()
    log("CONNECT", f"{endereco[0]}:{endereco[1]}")

    try:
        dados = conexao.recv(1024).decode("utf-8").strip()
    except:
        conexao.close()
        continue

    partes = dados.split("|")
    if len(partes) < 2 or partes[0] != "ENTRAR":
        log("ERRO", "cliente não mandou ENTRAR")
        conexao.close()
        continue

    nome = partes[1].strip() or "Anônimo"
    cor = cores[len(clientes) % len(cores)]

    cliente = {"socket": conexao, "nome": nome, "cor": cor, "endereco": endereco}
    clientes.append(cliente)
    log("ENTRAR", nome)

    enviar_para(cliente, f"COR|{cor}")
    enviar_para_todos(f"{cor}{nome}{RESET} entrou no chat", exceto=cliente)

    threading.Thread(target=atender, args=(cliente,), daemon=True).start()
