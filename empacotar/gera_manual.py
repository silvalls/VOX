"""Gera o Manual do Usuário do VOX em PDF (identidade visual + linguagem acessível)."""

from pathlib import Path
from fpdf import FPDF

RAIZ = Path(__file__).resolve().parent.parent
LOGO = RAIZ / "degravador" / "webui" / "logo.png"
SAIDA = Path(__file__).resolve().parent / "Manual do Usuario - VOX.pdf"

ARIAL = Path(r"C:\Windows\Fonts\arial.ttf")
ARIALBD = Path(r"C:\Windows\Fonts\arialbd.ttf")
ARIALIT = Path(r"C:\Windows\Fonts\ariali.ttf")

ROXO = (123, 63, 214)
DOURADO = (200, 130, 30)
CINZA = (90, 90, 100)


class Manual(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_y(8)
        self.set_font("Arial", "", 8)
        self.set_text_color(*CINZA)
        self.cell(0, 5, "VOX — Manual do Usuário", align="L")
        self.set_text_color(0, 0, 0)
        self.set_y(24)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-14)
        self.set_font("Arial", "", 8)
        self.set_text_color(*CINZA)
        self.cell(0, 5, str(self.page_no()), align="C")
        self.set_text_color(0, 0, 0)


pdf = Manual(orientation="P", unit="mm", format="A4")
pdf.set_margins(22, 24, 22)
pdf.set_auto_page_break(auto=True, margin=18)
pdf.add_font("Arial", "", str(ARIAL))
pdf.add_font("Arial", "B", str(ARIALBD))
if ARIALIT.exists():
    pdf.add_font("Arial", "I", str(ARIALIT))


def h1(txt):
    pdf.ln(3)
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(*ROXO)
    pdf.multi_cell(0, 8, txt, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*DOURADO)
    pdf.set_line_width(0.6)
    y = pdf.get_y() + 1
    pdf.line(pdf.l_margin, y, pdf.l_margin + 40, y)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)


def h2(txt):
    pdf.ln(1)
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(60, 40, 110)
    pdf.multi_cell(0, 6.5, txt, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)


def p(txt):
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(0, 6, txt, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)


def item(txt):
    pdf.set_font("Arial", "", 11)
    x = pdf.get_x()
    pdf.set_text_color(*ROXO)
    pdf.cell(6, 6, "•")
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 6, txt, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.5)


def nota(txt):
    pdf.set_fill_color(243, 238, 255)
    pdf.set_font("Arial", "", 10)
    pdf.multi_cell(0, 5.6, txt, new_x="LMARGIN", new_y="NEXT", fill=True, border=0)
    pdf.ln(2)


# ============================ CAPA ============================
pdf.add_page()
pdf.ln(35)
if LOGO.exists():
    pdf.image(str(LOGO), x=(210 - 60) / 2, w=60)
pdf.ln(6)
pdf.set_font("Arial", "B", 40)
pdf.set_text_color(*ROXO)
pdf.cell(0, 18, "VOX", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(12)
pdf.set_font("Arial", "B", 20)
pdf.set_text_color(0, 0, 0)
pdf.cell(0, 10, "Manual do Usuário", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Arial", "", 12)
pdf.set_text_color(*CINZA)
pdf.cell(0, 7, "Degravação local, fiel e auditável — áudio e vídeo em pt-BR", align="C",
         new_x="LMARGIN", new_y="NEXT")
pdf.ln(30)
pdf.set_font("Arial", "", 10)
pdf.cell(0, 6, "Versão 1.1", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(0, 0, 0)

# ============================ 1 ============================
pdf.add_page()
h1("1. O que é o VOX")
p("O VOX transforma gravações de áudio e vídeo em texto (degravação), identificando "
  "quem falou o quê e quando. Ele foi feito com três compromissos:")
item("Fidelidade: o VOX transcreve exatamente o que foi dito. Nenhuma inteligência "
     "artificial 'melhora' ou reescreve a fala. Correções são feitas por você, na conferência.")
item("Privacidade: todo o processamento acontece no seu computador. Nenhum áudio ou "
     "texto sai da máquina — funciona sem internet.")
item("Auditabilidade: cada documento traz o código de verificação (hash SHA-256) do "
     "arquivo original e preserva a transcrição bruta, permitindo conferência.")

h1("2. Instalação")
h2("O que a máquina precisa ter")
p("Obrigatório: Windows 10 ou 11 (64 bits) e cerca de 13 GB livres em disco. Só isso — "
  "o VOX não precisa de internet, nem de conta, nem de senha de administrador (ele "
  "instala na pasta do próprio usuário).")
h2("Placa de vídeo: o que muda na prática")
p("O VOX funciona em QUALQUER máquina que atenda ao acima. A placa de vídeo não é "
  "requisito — é velocidade. É de longe o fator que mais pesa no tempo de espera:")
item("RECOMENDADO — placa NVIDIA com 4 GB de memória de vídeo (VRAM) ou mais. É a "
     "configuração para a qual o VOX foi ajustado e a que entrega o melhor equilíbrio "
     "entre velocidade e qualidade. Com ela, uma gravação de 1 hora costuma ficar "
     "pronta em poucos minutos.")
item("MELHOR AINDA — placas NVIDIA com mais memória (8 GB, 12 GB ou mais) processam o "
     "mesmo material em menos tempo. Não é necessário: acima de 4 GB o ganho é de "
     "velocidade, não de qualidade da degravação.")
item("SEM PLACA NVIDIA (ou com placa de outra marca) — o VOX usa o processador (CPU). "
     "Funciona normalmente e o resultado é o MESMO; apenas demora bem mais. Uma "
     "gravação longa pode levar horas em vez de minutos. Nesse caso, deixe o "
     "computador trabalhando e vá fazer outra coisa.")
nota("A qualidade da transcrição não depende da placa de vídeo: com ou sem ela, o VOX usa "
     "o mesmo modelo e entrega o mesmo texto. O que muda é só quanto tempo você espera. "
     "Se tiver uma placa NVIDIA, mantenha o driver atualizado — um driver antigo demais "
     "faz o VOX cair para o processador sem você perceber, e é justamente isso que a "
     "faixa colorida da tela inicial avisa (seção 3).")
h2("Passo a passo")
item("Copie TODOS os arquivos (o .exe e os .bin) para a mesma pasta na máquina de destino.")
item("Dê dois cliques no \"Instalador VOX ....exe\".")
item("Se o Windows exibir um aviso azul (SmartScreen), clique em \"Mais informações\" e "
     "depois em \"Executar assim mesmo\". (O aviso aparece porque o instalador é interno, "
     "não assinado — é seguro.)")
item("Siga o assistente. Ao final, o VOX estará no Menu Iniciar e na Área de Trabalho.")

# ============================ 3 ============================
h1("3. Como fazer uma degravação")
h2("A faixa da placa de vídeo")
p("Ao abrir, o VOX verifica sozinho a placa de vídeo e o driver instalados, e mostra uma "
  "faixa no alto da tela:")
item("Verde — a placa está pronta e a degravação vai usar toda a velocidade dela.")
item("Amarela — funciona, mas existe um driver NVIDIA mais novo. Atualizar é opcional.")
item("Vermelha — o driver é antigo demais e a placa NÃO será usada: o trabalho cairá no "
     "processador e pode levar horas em vez de minutos. Clique no botão da faixa para ir "
     "à página de download do driver, atualize e reabra o VOX.")
item("Cinza — não há placa NVIDIA nesta máquina. O VOX funciona normalmente pelo "
     "processador, apenas mais devagar.")
nota("A verificação é feita na própria máquina e não impede o uso do programa. Se houver "
     "internet, o VOX ainda compara com a última versão publicada pela NVIDIA; sem "
     "internet, ele apenas confere se o driver atende ao mínimo — e nada é enviado.")
h2("Passo a passo")
item("Abra o VOX.")
item("Clique em \"Escolher…\" e selecione o áudio ou vídeo. São aceitos MP4, MKV, MOV, "
     "AVI, MP3, WAV, OGG, M4A, AAC, FLAC e outros.")
item("Confira a \"pasta de destino\" (o VOX cria ali uma pasta com o nome do arquivo).")
item("Se souber quantas pessoas falam, informe no campo opcional — melhora a separação "
     "de locutores. Se não souber, deixe em branco.")
item("Escolha o \"Idioma da fala\". O padrão é Português (Brasil); há também Espanhol, "
     "Inglês, Francês, Alemão e Italiano. Prefira informar o idioma a usar \"Detectar "
     "automaticamente\": a detecção olha apenas o começo do áudio e pode errar se houver "
     "ruído ou uma saudação em outra língua — e erra para a gravação inteira. Seja qual "
     "for a escolha, o idioma usado fica registrado no PDF.")
item("Marque \"Gerar também legendas (SRT/VTT)\" se for legendar um vídeo (ver seção 7).")
item("Clique em \"Transcrever\". Acompanhe a barra de progresso; se precisar, use \"Cancelar\".")
p("Ao terminar, a conferência abre automaticamente e a pasta de resultados recebe dois "
  "arquivos: o PDF da degravação e o arquivo de conferência (.html).")

h1("4. Os arquivos gerados")
item("<nome>.pdf — a degravação oficial (formato ABNT). No início traz o arquivo de "
     "origem, a data e a legenda de interlocutores; no final (o \"fecho\"), o modelo "
     "utilizado, o responsável pela conferência e o hash SHA-256 do original.")
item("<nome>.conferencia.html — a tela para você ouvir e conferir/corrigir (seção 5).")
p("Depois da conferência, são gerados ainda o PDF corrigido (pós-conferência) e um "
  "relatório comparativo das alterações.")

# ============================ 5 ============================
pdf.add_page()
h1("5. Conferência e correção")
p("Abra o arquivo \"<nome>.conferencia.html\" (dois cliques). Esta é a etapa em que você "
  "ouve o áudio e confere/corrige o texto.")
h2("Nome do conferencista")
p("Ao abrir, informe seu nome. Ele constará no PDF corrigido, registrando quem fez a "
  "conferência.")
h2("Painel de cima — Conferência (não editável)")
p("É a transcrição original, que não deve ser alterada (é a prova). Recursos:")
item("Clique em qualquer palavra para o áudio pular exatamente naquele ponto.")
item("A palavra que está tocando fica destacada em amarelo.")
item("Trechos em que a máquina teve baixa confiança ficam realçados em rosa — confira-os "
     "com atenção. Marcações como [inaudível] e [vozes sobrepostas] indicam pontos difíceis.")
h2("Controles do áudio (teclado)")
item("Barra de espaço: tocar / pausar.")
item("Setas ESQUERDA / DIREITA: voltar / avançar 10 segundos.")
item("Setas CIMA / BAIXO: aumentar / diminuir a velocidade de reprodução.")
item("Ctrl+F: buscar uma palavra no texto.")
h2("Nomear interlocutores")
p("O VOX apenas separa as vozes e as chama de SPEAKER_00, SPEAKER_01, etc. — ele nunca "
  "inventa nomes. VOCÊ atribui o nome real de cada voz, se souber (ex.: SPEAKER_00 -> "
  "\"Depoente\"). Se deixar em branco, o rótulo técnico é mantido.")
item("Renomear: digite o nome no painel \"Interlocutores\"; ele se aplica em todo o "
     "documento na hora.")
item("Mesclar: se a mesma pessoa recebeu dois rótulos, use \"mesclar com…\" para "
     "juntá-los em um único interlocutor, no documento inteiro.")
item("Criar: o botão \"Novo interlocutor\" acrescenta uma voz que a máquina não separou.")
h2("Painel de baixo — Correção")
p("Edite o texto aqui enquanto ouve, sem tocar no painel de cima. Seu trabalho é salvo "
  "automaticamente (rascunho): se fechar sem querer e reabrir, ele é restaurado.")
h2("Corrigir quem falou o quê")
p("A separação automática de vozes erra nos dois sentidos, e você conserta os dois na "
  "própria conferência. Cada trecho do painel de baixo tem uma caixa com o nome do "
  "interlocutor e dois botões, que aparecem ao passar o mouse:")
item("Trocar de interlocutor: basta escolher outro nome na caixa do trecho. Escolhendo "
     "\"novo interlocutor\", o VOX cria a voz na hora e já atribui o trecho a ela.")
item("Botão \"separar\" — quando duas pessoas caíram na mesma fala: clique no texto, no "
     "ponto exato em que a segunda pessoa começa a falar, e clique em \"separar\" (ou "
     "tecle Shift+Enter). O trecho vira dois, e você escolhe o interlocutor de cada "
     "parte. O VOX acerta o tempo do corte pelo áudio.")
item("Botão \"juntar\" — quando a fala de uma pessoa só foi picotada em vários trechos: "
     "clique em \"juntar\" para aglutinar o trecho ao de cima, formando uma fala única.")
item("Errou? O botão \"desfazer\" no topo volta atrás em cada separação, aglutinação ou "
     "troca de interlocutor.")
nota("O painel de cima nunca muda: ele preserva a transcrição e a divisão de vozes como a "
     "máquina entregou. Tudo o que você separar, juntar ou reatribuir vale para o PDF "
     "corrigido — e sai listado, um a um, no relatório de conferência.")
h2("Salvar")
p("Clique em \"Salvar correção (gera PDF)\". O VOX gera, na mesma pasta:")
item("<nome>.corrigido.pdf — a degravação corrigida, marcada como \"pós-conferência\", "
     "com o seu nome.")
item("<nome>.relatorio-conferencia.pdf — um comparativo entre o original e o corrigido, "
     "com o percentual de alteração.")
nota("A transcrição original é sempre preservada. O relatório documenta exatamente o que "
     "foi alterado por você — transparência total.")

# ============================ 6 ============================
h1("6. Validador de integridade (hash)")
p("Todo PDF de degravação traz o \"Hash SHA-256\" do arquivo de áudio/vídeo original — "
  "uma espécie de impressão digital. Para provar, no futuro, que um arquivo não foi "
  "alterado:")
item("Na tela inicial do VOX, clique em \"Validar integridade de um arquivo (hash)\".")
item("Escolha o arquivo original; o VOX calcula o hash dele.")
item("Cole o hash que consta no PDF e clique em \"Comparar\".")
item("Se aparecer \"CONFEREM\", o arquivo está íntegro. Se \"DIFEREM\", ele foi alterado.")

# ============================ 7 ============================
h1("7. Legendas (SRT / VTT)")
p("Quando você marca \"Gerar também legendas\", o VOX cria arquivos .srt e .vtt na pasta "
  "de resultados. IMPORTANTE: eles NÃO são um vídeo com a legenda embutida — são arquivos "
  "de legenda sincronizada que o player exibe por cima do vídeo.")
h2("Como usar num player")
item("VLC / PotPlayer / Media Player: abra o vídeo e arraste o arquivo .srt para a janela "
     "do player. A legenda aparece sincronizada.")
item("Na maioria dos players, se o .srt tiver o MESMO nome do vídeo e estiver na MESMA "
     "pasta, a legenda é carregada automaticamente ao abrir o vídeo.")
item("No VLC, também é possível: menu Legendas -> Adicionar arquivo de legenda.")
item("Em navegadores/edição de vídeo, o .vtt é o formato equivalente para a web.")

# ============================ 8 ============================
pdf.add_page()
h1("8. Boas práticas e limitações")
item("A degravação automática é a primeira passada. A conferência humana dos trechos "
     "realçados (baixa confiança) faz parte do processo — o VOX foi feito para tornar "
     "essa conferência rápida e direcionada, não para eliminá-la.")
item("Áudio muito ruidoso, distante do microfone ou com muitas vozes ao mesmo tempo "
     "aumenta os erros. Esses pontos vêm marcados para você revisar.")
item("Nomes próprios e siglas raras podem sair com grafia aproximada — corrija-os na "
     "conferência.")
item("Áudios longos (horas) levam mais tempo; a estimativa aparece na barra de progresso.")
item("Fidelidade: o VOX nunca troca o que foi dito por conta própria. Privacidade: nada "
     "sai do seu computador. Auditabilidade: o original é sempre preservado.")

h1("9. Perguntas rápidas")
h2("Preciso de internet?")
p("Não. Após instalado, o VOX funciona totalmente offline.")
h2("Preciso de conta ou senha de algum serviço?")
p("Não. Tudo é local; nenhum cadastro é necessário.")
h2("Onde ficam meus resultados?")
p("Na pasta de destino que você escolheu, dentro de uma subpasta com o nome do arquivo.")
h2("Posso reabrir uma conferência depois?")
p("Sim. Basta abrir novamente o arquivo \"<nome>.conferencia.html\". Se havia um rascunho "
  "de correção, ele é restaurado.")

pdf.output(str(SAIDA))
print("Manual gerado:", SAIDA)
