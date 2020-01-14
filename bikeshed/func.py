# -*- coding: utf-8 -*-


class Functor(object):
    # Pointed and Co-Pointed by default;
    # override these yourself if you need to.
    def __init__(self, val):
        self.__val__ = val
    def extract(self):
        return self.__val__
    def map(self, fn):
        return self.__class__(fn(self.__val__))
