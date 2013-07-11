# Fuck everything about Python 2 and Unicode.
def u(text):
    if text is None:
        return None
    elif isinstance(text, str):
        return text.decode('utf-8')
    elif isinstance(text, unicode):
        return text
    else:
        try:
            return unicode(text)
        except:
            die("Unicode encoding error! Please report to the project maintainer. Some information: {0}", str(type(text)) + str(text))