FROM python:3.10-slim
WORKDIR /app
COPY req_bot.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --prefer-binary -r req_bot.txt
COPY . .
