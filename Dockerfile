# FROM python:3.7

# WORKDIR /app
# COPY . /app

# RUN pip install --upgrade pip
# RUN pip install tensorflow==1.15.0
# RUN pip install -r requirements.txt

# EXPOSE 5000

# CMD ["python", "app.py"]
FROM python:3.7

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip

# Install all dependencies (include tensorflow here)
RUN pip install -r requirements.txt

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]