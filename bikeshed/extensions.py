from . import constants, retrieve


def load(doc):
    code = retrieve.retrieveBoilerplateFile(doc, "bs-extensions", allowLocal=constants.executeCode)
    exec(code, globals())
