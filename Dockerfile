FROM python:3.12-slim
WORKDIR /app

# Instalar as dependencias antes de copiar o codigo: o requirements.txt muda
# raramente, entao o pip install fica em cache e so o COPY do codigo re-executa.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY data/ data/
COPY prompts/ prompts/

# Logs sem buffer, senao o print/log so aparece quando o container morre.
ENV PYTHONUNBUFFERED=1

# Usuario nao-root: a imagem python:slim roda como root por padrao.
RUN useradd --create-home --uid 1001 solar
USER solar

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
