# -*- coding: utf-8 -*-


class Nil(object):
    '''Super-None, falsey and returns itself from every method/attribute/etc'''

    def __repr__(self):
        return "Nil()"

    def __str__(self):
        return "Nil"

    def __bool__(self):
        return False

    def __call__(self, *args, **kwargs):
        return self

    def __getitem__(self, key):
        return self

    def __setitem__(self, key, val):
        return self

    def __delitem__(self, key, val):
        return self

    def __getattr__(self, name):
        return self

    def __setattr__(self, name, value):
        return self

    def __delattr__(self, name, value):
        return self

    def __eq__(self, other):
        if isinstance(other, Nil) or other is None:
            return True
        return False

    def __iter__(self):
        return iter([])