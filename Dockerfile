# syntax=docker/dockerfile:1

FROM python:3.10-slim-buster

RUN \
 # Install additional dependencies
  apt update && \
  apt install -y ffmpeg && \
  rm -rf /var/cache/apt/lists ;

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY *.py ./
COPY streamonitor ./streamonitor 

EXPOSE 6969
CMD [ "python3", "Downloader.py"]

