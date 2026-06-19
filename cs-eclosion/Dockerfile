FROM python:3.12-alpine

WORKDIR /app

RUN pip install --no-cache-dir flask

COPY app/ /app/
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
