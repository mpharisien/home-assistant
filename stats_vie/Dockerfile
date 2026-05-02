FROM python:3.12-alpine
 
RUN apk add --no-cache gcc musl-dev
 
WORKDIR /app
COPY app/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
 
COPY app/ .
 
CMD ["python3", "app.py"]
