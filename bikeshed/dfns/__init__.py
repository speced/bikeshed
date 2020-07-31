
def annotateDfns(doc):
	from . import attributeInfo
	attributeInfo.addAttributeInfoSpans(doc)
	attributeInfo.fillAttributeInfoSpans(doc)