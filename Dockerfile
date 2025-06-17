# syntax=docker/dockerfile:1

FROM python:3.12-alpine3.19

# Install dependencies
RUN apk add --no-cache ffmpeg

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY *.py ./
COPY streamonitor ./streamonitor 
COPY web ./web

EXPOSE 6969
CMD [ "python3", "Downloader.py"]

