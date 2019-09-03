Contributing to widlparser
==========================

All contributions are welcome!


Testing
-------

To ensure that there are no unexpected changes, compare the output of `test.py`:

    	./test.py | diff -u test-expected.txt -

If all changes are expected, include them in your pull request:

       	./test.py > test-expected.txt
       	git add test-expected.txt
