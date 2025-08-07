FROM python:3.10-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
ENV FLASK_SECRET_KEY=your-secure-secret-key-here
EXPOSE 5000
CMD ["python", "app.py"]
