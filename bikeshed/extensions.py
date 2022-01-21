from . import config, constants

def load(doc):
    code = config.retrieveBoilerplateFile(doc, "bs-extensions", allowLocal=constants.executeCode)
    exec(code, globals())
