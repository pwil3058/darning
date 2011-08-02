VERSION:=$(subst ',,$(subst VERSION = ',,$(shell grep "VERSION = " setup.py)))
RELEASE=1

RPMBDIR=~/rpmbuild
PREFIX=/usr

SRCS:=$(shell hg status -macdn)
SRCDIST:=darning-$(VERSION).tar.gz
RPMDIST:=darning-$(VERSION)-$(RELEASE).noarch.rpm
RPMSRC:=$(RPMBDIR)/SOURCES/$(SRCDIST)

help:
	@echo "Choices are:"
	@echo "	make sdist"
	@echo "	make rpm"
	@echo "	make all_dist"
	@echo "	make install"
	@echo "	make clean"

all_dist: $(SRCDIST)  $(WINDIST) $(RPMDIST)

darning.spec: setup.py Makefile setup.cfg
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

clean:
	-rm *.rpm *.spec *.exe *.tar.gz MANIFEST
	-rm -r build
