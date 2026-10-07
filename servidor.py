import socket
import threading
import os
import time
import json
from google import genai
from google.genai import types

# Configuração Gemini
client = genai.Client(api_key="")
MODELO = "gemini-3.8-flash"

clientes = []
cores = ["\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[95m", "\033[96m"]
RESET = "\033[0m"
COR_SISTEMA = "\033[97m"

estado_jogo = "LOBBY"
lock_jogo = threading.Lock()
respostas_rodada = {}
pontuacoes = {}
inicio_pergunta = 0
PERGUNTAS = []

def gerar_quiz_ia(tema, dificuldade, quantidade):
    prompt = f"""Você é uma API de quiz.
    Retorne EXCLUSIVAMENTE um objeto JSON neste formato exato:
    {{"perguntas": [{{"texto": "Pergunta?", "opcoes": {{"A": "op1", "B": "op2", "C": "op3", "D": "op4"}}, "correta": "A"}}]}}
    
    Tema: {tema}
    Dificuldade: {dificuldade}
    Quantidade: {quantidade}"""
    
    # Mecanismo de Retry com Backoff
    tentativas = 3
    for tentativa in range(tentativas):
        try:
            resposta = client.models.generate_content(
                model=MODELO,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            dados = json.loads(resposta.text)
            return dados.get("perguntas", [])
        except Exception as e:
            print(f"Tentativa {tentativa + 1} falhou: {e}")
            if tentativa < tentativas - 1:
                time.sleep(2 * (tentativa + 1))
            else:
                print(f"Erro definitivo ao gerar quiz com Gemini após {tentativas} tentativas.")
                return None

def enviar_para(cliente, mensagem):
    try: cliente["socket"].send((mensagem + "\n").encode("utf-8"))
    except: pass

def enviar_para_todos(mensagem, exceto=None):
    for c in clientes:
        if c is not exceto: enviar_para(c, mensagem)

def iniciar_quiz_dinamico(cliente_host, tema, dificuldade, quantidade):
    global PERGUNTAS, estado_jogo
    
    with lock_jogo:
        if estado_jogo != "LOBBY": return
        estado_jogo = "GERANDO"

    enviar_para_todos(f"{COR_SISTEMA}[KAHOOT]{RESET} A IA está processando o tema '{tema}' ({dificuldade})...")
    
    perguntas_geradas = gerar_quiz_ia(tema, dificuldade, quantidade)
    
    if not perguntas_geradas or not isinstance(perguntas_geradas, list) or len(perguntas_geradas) == 0:
        enviar_para_todos(f"{COR_SISTEMA}[ERRO]{RESET} Falha ao gerar as perguntas. Tente novamente.")
        with lock_jogo: estado_jogo = "LOBBY"
        return

    PERGUNTAS = perguntas_geradas
    loop_kahoot()

def loop_kahoot():
    global estado_jogo, respostas_rodada, inicio_pergunta
    
    with lock_jogo:
        estado_jogo = "JOGANDO"
        pontuacoes.clear()
        for c in clientes:
            pontuacoes[c["nome"]] = 0
        
    enviar_para_todos("CMD|CLEAR")
    enviar_para_todos(f"{COR_SISTEMA}[KAHOOT]{RESET} O jogo começará em 5 segundos!")
    time.sleep(5)

    for i, q in enumerate(PERGUNTAS):
        with lock_jogo: respostas_rodada.clear()
            
        enviar_para_todos("CMD|CLEAR")
        msg = f"{COR_SISTEMA}[KAHOOT]{RESET} Pergunta {i+1}/{len(PERGUNTAS)}: {q.get('texto', 'Erro na pergunta')}\n"
        opcoes = q.get('opcoes', {})
        for letra, opcao in opcoes.items():
            msg += f"  {letra}) {opcao}\n"
        msg += f"\nVocê tem 15 segundos! Digite A, B, C ou D."
        
        enviar_para_todos(msg)
        inicio_pergunta = time.time()
        time.sleep(15)

        enviar_para_todos("CMD|CLEAR")
        correta = str(q.get('correta', '')).strip().upper()
        enviar_para_todos(f"{COR_SISTEMA}[KAHOOT]{RESET} Tempo esgotado! A resposta correta era: {correta}")
        
        with lock_jogo:
            for nome, (resp, tempo_resp) in respostas_rodada.items():
                if resp == correta:
                    delta = tempo_resp - inicio_pergunta
                    pontos = max(10, int(100 - (delta * 6))) 
                    pontuacoes[nome] = pontuacoes.get(nome, 0) + pontos
        time.sleep(5)

    enviar_para_todos("CMD|CLEAR")
    placar_msg = f"{COR_SISTEMA}[KAHOOT]{RESET} --- PLACAR FINAL ---\n"
    for nome, pts in sorted(pontuacoes.items(), key=lambda x: x[1], reverse=True):
        placar_msg += f" - {nome}: {pts} pontos\n"
    enviar_para_todos(placar_msg)
    
    with lock_jogo: estado_jogo = "LOBBY"

def atender(cliente):
    while True:
        try: dados = cliente["socket"].recv(4096).decode("utf-8")
        except: break
        if not dados: break

        for linha in dados.split("\n"):
            if not linha: continue
            
            if estado_jogo == "JOGANDO":
                if linha.startswith("MSG|"):
                    resp = linha[4:].strip().upper()
                    if resp in ["A", "B", "C", "D"]:
                        with lock_jogo:
                            if cliente["nome"] not in respostas_rodada:
                                respostas_rodada[cliente["nome"]] = (resp, time.time())
                                enviar_para(cliente, f"{COR_SISTEMA}[KAHOOT]{RESET} Resposta '{resp}' registrada!")
                            else:
                                enviar_para(cliente, f"{COR_SISTEMA}[KAHOOT]{RESET} Você já respondeu.")
                    else:
                        enviar_para(cliente, f"{COR_SISTEMA}[KAHOOT]{RESET} Jogo em andamento. Digite apenas A, B, C ou D.")
                continue 

            if linha.startswith("MSG|"):
                texto = linha[4:]
                if texto.startswith("/tema "):
                    if not cliente.get("host"):
                        enviar_para(cliente, f"{COR_SISTEMA}[ERRO]{RESET} Apenas o dono da sala (Host) pode escolher o tema.")
                        continue
                    if estado_jogo != "LOBBY":
                        enviar_para(cliente, f"{COR_SISTEMA}[ERRO]{RESET} Um jogo já está em andamento.")
                        continue
                    
                    parametros = texto[6:].split(",")
                    if len(parametros) != 3:
                        enviar_para(cliente, f"{COR_SISTEMA}[ERRO]{RESET} Formato inválido. Use: /tema [tema], [dificuldade], [quantidade]")
                        continue
                        
                    tema, dificuldade, qtd = [p.replace("[", "").replace("]", "").strip() for p in parametros]
                    threading.Thread(target=iniciar_quiz_dinamico, args=(cliente, tema, dificuldade, qtd), daemon=True).start()
                    continue
                
                enviar_para_todos(f"{cliente['cor']}{cliente['nome']}{RESET} {texto}", exceto=cliente)

            elif linha.startswith("PRIV|"):
                partes = linha[5:].split("|", 1)
                if len(partes) >= 2:
                    destinatario, msg = partes
                    for c in clientes:
                        if c["nome"] == destinatario:
                            enviar_para(c, f"{cliente['cor']}{cliente['nome']}{RESET} (priv) {msg}")
                            break

    if cliente in clientes: clientes.remove(cliente)
    
    if cliente.get("host") and clientes:
        clientes[0]["host"] = True
        enviar_para(clientes[0], f"{COR_SISTEMA}[SISTEMA]{RESET} O host anterior saiu. Você agora é o dono da sala!")

    enviar_para_todos(f"{cliente['cor']}{cliente['nome']}{RESET} saiu do chat")
    try: cliente["socket"].close()
    except: pass

servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
servidor.bind(("0.0.0.0", 9999))
servidor.listen()

print("Servidor rodando na porta 9999...\n")
while True:
    conexao, endereco = servidor.accept()
    try:
        dados = conexao.recv(1024).decode("utf-8").strip()
        partes = dados.split("|")
        if partes[0] == "ENTRAR":
            nome = partes[1].strip() or "Anônimo"
            cor = cores[len(clientes) % len(cores)]
            is_host = len(clientes) == 0
            
            cliente = {"socket": conexao, "nome": nome, "cor": cor, "host": is_host}
            clientes.append(cliente)
            enviar_para(cliente, f"COR|{cor}")
            
            if is_host:
                enviar_para(cliente, f"{COR_SISTEMA}[SISTEMA]{RESET} Você é o dono da sala! Digite /tema [assunto], [dificuldade], [quantidade] para gerar o quiz.")
            
            enviar_para_todos(f"{cor}{nome}{RESET} entrou", exceto=cliente)
            threading.Thread(target=atender, args=(cliente,), daemon=True).start()
    except:
        conexao.close()