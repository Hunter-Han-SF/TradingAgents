FROM docker.m.daocloud.io/library/python:3.11-slim-bullseye

RUN echo "deb http://mirrors.aliyun.com/debian/ bullseye main non-free contrib" > /etc/apt/sources.list && \
echo "deb-src http://mirrors.aliyun.com/debian/ bullseye main non-free contrib" >> /etc/apt/sources.list && \
echo "deb http://mirrors.aliyun.com/debian-security/ bullseye-security main" >> /etc/apt/sources.list && \
echo "deb-src http://mirrors.aliyun.com/debian-security/ bullseye-security main" >> /etc/apt/sources.list && \
echo "deb http://mirrors.aliyun.com/debian/ bullseye-updates main non-free contrib" >> /etc/apt/sources.list && \
echo "deb-src http://mirrors.aliyun.com/debian/ bullseye-updates main non-free contrib" >> /etc/apt/sources.list && \
echo "deb http://mirrors.aliyun.com/debian/ bullseye-backports main non-free contrib" >> /etc/apt/sources.list && \
echo "deb-src http://mirrors.aliyun.com/debian/ bullseye-backports main non-free contrib" >> /etc/apt/sources.list && \
echo  "[global]\n\
trusted-host=mirrors.aliyun.com\n\
index-url=http://mirrors.aliyun.com/pypi/simple" > /etc/pip.conf && \
ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone

ENV LANG=zh_CN.UTF-8
ENV LC_CTYPE=zh_CN.UTF-8
ENV LC_ALL=C
ENV PYTHONPATH=/opt/trading-agents

WORKDIR /opt/trading-agents

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY . /opt/trading-agents

RUN cd /opt/trading-agents && pip install .

CMD ["sleep" , "infinity"]