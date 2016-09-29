FROM python:2.7-wheezy

RUN apt-get install libxslt1-dev libxml2-dev && \
    pip install pygments && \
    pip install lxml --upgrade

WORKDIR /data

COPY . /usr/bikeshed

RUN pip install --editable /usr/bikeshed && bikeshed update

VOLUME /data
ENTRYPOINT ["/usr/local/bin/bikeshed"]
