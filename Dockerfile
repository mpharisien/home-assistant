FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY app/ /app/
COPY run.sh /
RUN chmod a+x /run.sh

EXPOSE 8099
CMD [ "/run.sh" ]
