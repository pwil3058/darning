VERSION=$(shell python3 darning/version.py)
RELEASE=1
PROCESSOR=$(shel uname -p)
OS="linux"

PREFIX=/usr

SRCS:=$(git ls-tree --full-tree -r --name-only HEAD)
SRCDIST:=dist/darning-$(VERSION).tar.gz
SRCDIST:=dist/darning-$(VERSION).$(OS)-$(PROCESSOR).tar.gz
CLI_SRCS=darn $(wildcard darning/*.py) $(wildcard darning/cli/*.py)
CLI_TEST_SCRIPTS=$(sort $(wildcard test-cli/*.test))
CLI_TESTS=$(patsubst test-cli/%.test,test-cli/.%.ok, $(CLI_TEST_SCRIPTS))

help:
	@echo "Choices are:"
	@echo "	make sdist"
	@echo "	make bdist"
	@echo "	make all_dist"
	@echo "	make install"
	@echo "	make clean"

all_dist: $(SRCDIST) $(BDIST)

sdist: $(SRCDIST)

$(SRCDIST): $(SRCS)
	python3 setup.py sdist

bdist: $(BDIST)

$(BDDIST): $(SRCS)
	python3 setup.py bdist

install:
	python3 setup.py install --prefix=$(PREFIX)
	desktop-file-install darning.desktop --dir $(PREFIX)/share/applications
	rm MANIFEST

check: $(CLI_TESTS)

test-cli/.%.ok: test-cli/%.test $(CLI_SRCS)
	@LANG=C; LC_ALL=C; PATH="$(PWD):$(PATH)";	\
	export LANG LC_ALL PATH;					\
	cd $(@D);									\
	../test-cli/run.py $(<F)
	@touch $@

clean:
	-rm *.rpm *.spec *.exe *.tar.gz MANIFEST
	-rm -r build
	-rm -r dist
	-rm $(CLI_TESTS_LEGACY) $(CLI_TESTS)
