VERSION=$(shell python3 darning/version.py)
RELEASE=1
PROCESSOR=$(shell uname -p)
OS="linux"

PREFIX=/usr

BAB_SRCS = $(wildcard darning/bab/*.py)
GIT_SRCS = $(wildcard darning/git/*.py)
GIT_GUI_SRCS = $(wildcard darning/git/gui/*.py)
GTX_SRCS = $(wildcard darning/gtx/*.py)
HG_SRCS = $(wildcard darning/hg/*.py)
HG_GUI_SRCS = $(wildcard darning/hg/gui/*.py)
PD_SRCS = $(wildcard darning/patch_diff/*.py)
PD_GUI_SRCS = $(wildcard darning/patch_diff/gui/*.py)
PM_SRCS = $(wildcard darning/pm/*.py)
PM_GUI_SRCS = $(wildcard darning/pm/gui/*.py)
SCM_SRCS = $(wildcard darning/scm/*.py)
SCM_GUI_SRCS = $(wildcard darning/scm/gui/*.py)
SM_SRCS = $(BAB_SRCS) $(GIT_SRCS) $(HG_SRCS) $(PD_SRCS) $(PM_SRCS) $(SCM_SRCS)
SM_GUI_SRCS = ${GTX_SRCS} $(GIT_GUI_SRCS) $(HG_GUI_SRCS) $(PD_GUI_SRCS) $(PM_GUI_SRCS) $(SCM_GUI_SRCS)
SRCS:=$(git ls-tree --full-tree -r --name-only HEAD) $(SM_SRCS) $(SM_GUI_SRCS)
SRCDIST:=dist/darning-$(VERSION).tar.gz
SRCDIST:=dist/darning-$(VERSION).$(OS)-$(PROCESSOR).tar.gz
CLI_SRCS=darn $(wildcard darning/*.py) $(wildcard darning/cli/*.py) $(SM_SRCS)
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

test-cli/.%.ok: test-cli/%.test diff_test_tool darn_test_tree test-cli/run.py
	@LANG=C; LC_ALL=C; PATH="$(PWD):$(PATH)";	\
	export LANG LC_ALL PATH;					\
	cd $(@D);									\
	../test-cli/run.py $(<F)
	@touch $@

reset_check:
	-rm $(CLI_TESTS)

clean:
	-rm *.rpm *.spec *.exe *.tar.gz MANIFEST
	-rm -r build
	-rm -r dist
	-rm $(CLI_TESTS)
