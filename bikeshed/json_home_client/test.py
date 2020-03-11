#!/usr/bin/env python
# coding=utf-8

from json_home_client import Client


if __name__ == "__main__":      # called from the command line
    github = Client('https://api.github.com/', version='vnd.github.beta')
    print(repr(github))
    print(repr(github.get('user_url', user='plinss').data))

    shepherd = Client('https://api.csswg.org/shepherd/', version='vnd.csswg.shepherd.v1')
    print(repr(shepherd))

    print(repr(shepherd.get('specifications', spec='compositing-1', anchors=False).data))

    print(repr(shepherd.get('test_suites', spec='css-shapes-1').data))
