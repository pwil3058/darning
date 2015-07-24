VERSION:=$(subst ',,$(subst VERSION = ',,$(shell grep "VERSION = " darning/version.py)))
RELEASE=1

RPMBDIR=~/rpmbuild
PREFIX=/usr

SRCS:=$(git ls-tree --full-tree -r --name-only HEAD)
SRCDIST:=darning-$(VERSION).tar.gz
RPMDIST:=darning-$(subst -,_,$(VERSION))-$(RELEASE).noarch.rpm
RPMSRC:=$(RPMBDIR)/SOURCES/$(SRCDIST)
CLI_SRCS=darn $(wildcard darning/*.py) $(wildcard darning/cli/*.py)
CLI_TEST_SCRIPTS=$(wildcard test-cli/*.test)
CLI_TESTS=$(patsubst test-cli/%.test,test-cli/.%.ok, $(CLI_TEST_SCRIPTS))
CLI_TEST_SCRIPTS_NG=$(sort $(wildcard test-cli-ng/*.test))
CLI_TESTS_NG=$(patsubst test-cli-ng/%.test,test-cli-ng/.%.ok, $(CLI_TEST_SCRIPTS_NG))

help:
	@echo "Choices are:"
	@echo "	make sdist"
	@echo "	make rpm"
	@echo "	make all_dist"
	@echo "	make install"
	@echo "	make clean"

all_dist: $(SRCDIST)  $(WINDIST) $(RPMDIST)

darning.spec: setup.py Makefile setup.cfg darning/version.py
	python setup.py bdist_rpm --build-requires python --spec-only --dist-dir .
	echo "%{_prefix}" >> darning.spec
	sed -i \
		-e 's/^\(python setup.py install.*\)/\1\ndesktop-file-install darning.desktop --dir $$RPM_BUILD_ROOT%{_datadir}\/applications/' \
		-e 's/-f INSTALLED_FILES//' \
		darning.spec

sdist: $(SRCDIST)

$(SRCDIST): $(SRCS)
	python setup.py sdist --dist-dir .
	rm MANIFEST

rpm: $(RPMDIST)

$(RPMSRC): $(SRCDIST)
	cp $(SRCDIST) $(RPMSRC)

$(RPMDIST): $(RPMSRC) darning.spec
	rpmbuild -bb darning.spec
	cp $(RPMBDIR)/RPMS/noarch/$(RPMDIST) .

install:
	python setup.py install --prefix=$(PREFIX)
	desktop-file-install darning.desktop --dir $(PREFIX)/share/applications
	rm MANIFEST

check: $(CLI_TESTS)

test-cli/.%.ok: test-cli/%.test $(CLI_SRCS)
	@LANG=C; LC_ALL=C; PATH="$(PWD):$(PATH)";	\
	export LANG LC_ALL PATH;					\
	cd $(@D);									\
	./run.py $(<F)
	@touch $@

check-ng: $(CLI_TESTS_NG)

test-cli-ng/.%.ok: test-cli-ng/%.test $(CLI_SRCS)
	@LANG=C; LC_ALL=C; PATH="$(PWD):$(PATH)";	\
	export LANG LC_ALL PATH;					\
	cd $(@D);									\
	../test-cli/run.py $(<F)
	@touch $@

clean:
	-rm *.rpm *.spec *.exe *.tar.gz MANIFEST
	-rm -r build
	-rm $(CLI_TESTS) $(CLI_TESTS_NG)
