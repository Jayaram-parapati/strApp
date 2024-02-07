#!/bin/bash
echo "Starting backend ..."
until cd /app/
do
    echo "Waiting for server volume..."
done
echo "I think, all files are probably copied..."
fnames=`ls ./*.py`
for eachfile in $fnames
do
    echo $eachfile
done
echo "starting guni guni guni gunicorn ..."
# gunicorn main:app --bind 0.0.0.0:8000 --workers 4 --threads 4
gunicorn -k uvicorn.workers.UvicornWorker abcd:app --bind 0.0.0.0:8080