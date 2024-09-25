from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import uuid
import textract
from docx import Document
import google.generativeai as genai
import markdown

app = Flask(__name__)

# Configuração do banco de dados SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db1.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Modelo do banco de dados para armazenar currículos e avaliações
class AvaliacaoCurriculo(db.Model):
    id = db.Column(db.String, primary_key=True)
    arquivo_nome = db.Column(db.String(150), nullable=False)
    arquivo_conteudo = db.Column(db.Text, nullable=False)
    tipo_vaga = db.Column(db.String(100), nullable=False)
    profissao = db.Column(db.String(100), nullable=False)
    descricao_empresa = db.Column(db.Text, nullable=False)
    avaliacao = db.Column(db.Text, nullable=False)
    melhorias = db.Column(db.Text, nullable=False)

with app.app_context():
  db.create_all()


# Configuração do Gemini
genai.configure(api_key=os.environ["API_KEY"])

import PyPDF2  # Adicionar ao topo

# Função para processar arquivos PDF
def processar_pdf(file):
    reader = PyPDF2.PdfReader(file)
    texto_pdf = ""
    for page in reader.pages:
        texto_pdf += page.extract_text()
    return texto_pdf

# Função para processar arquivos Word (.docx)
def processar_docx(file):
    document = Document(file)
    return '\n'.join([para.text for para in document.paragraphs])

# Função para processar outros arquivos, como .doc (usando textract)
def processar_arquivo_generico(file):
    return textract.process(file).decode('utf-8')

# Função para gerar a avaliação do currículo
def avaliar_curriculo_ai(curriculo_texto, tipo_vaga, profissao, descricao_empresa):
    # Avaliação geral do currículo
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=(
            "Você é uma IA especialista em currículos. Avalie o currículo abaixo, destacando pontos fortes e fracos "
            "e adequando-o ao tipo de vaga '{tipo_vaga}', à profissão '{profissao}' e à descrição da empresa '{descricao_empresa}'."
        )
    )

    # Gera a avaliação usando o modelo Gemini
    avaliacao = model.generate_content(
        f"Currículo: {curriculo_texto}\nTipo de Vaga: {tipo_vaga}\nProfissão: {profissao}\nDescrição da Empresa: {descricao_empresa}"
    ).text

    # Sugestão de melhorias
    melhorias = sugerir_melhorias_ai(curriculo_texto, tipo_vaga, profissao, descricao_empresa)

    return avaliacao, melhorias

# Função para gerar sugestões de melhorias no currículo
def sugerir_melhorias_ai(curriculo_texto, tipo_vaga, profissao, descricao_empresa):
    # Configura o modelo Gemini para sugerir melhorias no currículo com base em parâmetros fornecidos
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=(
            "Você é uma IA especialista em melhorar currículos. Com base no currículo abaixo e nos seguintes parâmetros, "
            "sugira melhorias específicas para adequar o currículo à vaga desejada:\n"
            "Tipo de Vaga: {tipo_vaga}\nProfissão: {profissao}\nDescrição da Empresa: {descricao_empresa}."
        )
    )

    # Gera as sugestões de melhorias usando o modelo Gemini
    response = model.generate_content(
        f"Currículo: {curriculo_texto}\nTipo de Vaga: {tipo_vaga}\nProfissão: {profissao}\nDescrição da Empresa: {descricao_empresa}"
    )
    
    return response.text

# Página inicial
@app.route('/')
def index():
    avaliacoes = AvaliacaoCurriculo.query.all()
    return render_template('index.html', avaliacoes=avaliacoes)

# Rota para envio de currículo e geração de avaliação
@app.route('/upload', methods=['POST'])
def upload_curriculo():
    if 'file' not in request.files:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400

    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"erro": "Nenhum arquivo selecionado."}), 400

    if file:
        # Processa o arquivo dependendo do tipo (docx, doc)
        file_extension = file.filename.split('.')[-1].lower()
        
        if file_extension == 'docx':
            curriculo_texto = processar_docx(file)
        elif file_extension == 'doc':
            curriculo_texto = processar_arquivo_generico(file)
        elif file_extension == 'pdf':
            curriculo_texto = processar_pdf(file)  # Novo suporte para PDF
        else:
            return jsonify({"erro": "Formato de arquivo não suportado."}), 400

        # Captura informações adicionais do formulário
        tipo_vaga = request.form['tipo_vaga']
        profissao = request.form['profissao']
        descricao_empresa = request.form['descricao_empresa']

        # Avalia o currículo usando Gemini
        avaliacao, melhorias = avaliar_curriculo_ai(curriculo_texto, tipo_vaga, profissao, descricao_empresa)

        # Salva no banco de dados
        avaliacao_id = str(uuid.uuid4())
        nova_avaliacao = AvaliacaoCurriculo(
            id=avaliacao_id,
            arquivo_nome=file.filename,
            arquivo_conteudo=curriculo_texto,
            tipo_vaga=tipo_vaga,
            profissao=profissao,
            descricao_empresa=descricao_empresa,
            avaliacao=markdown.markdown(avaliacao),
            melhorias=markdown.markdown(melhorias)
        )
        db.session.add(nova_avaliacao)
        db.session.commit()

        # Redireciona para a página de avaliação
        return redirect(url_for('avaliacao_detalhes', avaliacao_id=avaliacao_id))

# Página de visualização da avaliação
@app.route('/avaliacao/<avaliacao_id>')
def avaliacao_detalhes(avaliacao_id):
    avaliacao = AvaliacaoCurriculo.query.get(avaliacao_id)
    if avaliacao:
        return render_template('avaliacao.html', avaliacao=avaliacao)
    else:
        return "Avaliação não encontrada", 404

if __name__ == '__main__':
    app.run(debug=False , host="0.0.0.0", port=9085)
