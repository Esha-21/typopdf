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

# Install Inkscape (VERY IMPORTANT)
RUN apt-get update && apt-get install -y inkscape

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]