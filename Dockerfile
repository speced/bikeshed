FROM python:2.7-wheezy

RUN apt-get install libxslt1-dev libxml2-dev

RUN pip install pygments
RUN pip install lxml --upgrade

COPY . /usr/bikeshed

RUN pip install --editable /usr/bikeshed
